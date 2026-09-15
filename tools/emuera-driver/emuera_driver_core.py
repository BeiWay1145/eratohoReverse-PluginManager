#!/usr/bin/env python3
"""Emuera 驱动核心：启动游戏、注入探针、抓取引擎日志、解析诊断。

设计依据（全部实测确认，非推测）：

1. **启动即执行的锚点**：Emuera 的事件函数里只有 @SYSTEM_TITLE 在启动时必跑。
   本工具通过「临时插入一行 CALL PLUGIN_HOOK("BOOT")」把探针挂上去，
   运行完自动还原，不改动用户文件。

2. **输出通道 = OUTPUTLOG**：
   Emuera 的 OUTPUTLOG 命令把「引擎日志」写到 <游戏目录>/emuera.log，
   编码 **UTF-16LE**，内容包含：
     - 编译警告/错误（警告Lv1/警告Lv2 + 文件:行目 + 原文行）
     - 运行时异常 + **函数调用栈**（← 这是验证钩子链路的关键证据）
   实测一次性导出 1033 行、83 KB，覆盖全部 966 个 ERB。

3. **SAVETEXT 在当前版本不可用**（"この機能は現バージョンでは使えません"），
   所以探针不要用 SAVETEXT 落盘，改用 PRINTL + OUTPUTLOG。
"""
import os
import re
import shutil
import subprocess
import sys
import time

BOM = b"\xef\xbb\xbf"

SYSTEM_TITLE_REL = os.path.join("ERB", "SYSTEM", "SYSTEM_TITLE.ERB")
PROBE_REL_DIR = os.path.join("ERB", "PLUGIN", "zzdriver_probe")
MARK = ";ZZDRV_PROBE_MARK"


def _read(p):
    raw = open(p, "rb").read()
    return raw.decode("utf-8-sig"), raw.startswith(BOM)


def _write(p, text, bom):
    data = (BOM if bom else b"") + text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
    open(p, "wb").write(data)


def find_exe(game):
    for f in sorted(os.listdir(game)):
        if f.lower().startswith("emuera") and f.lower().endswith(".exe"):
            return os.path.join(game, f)
    return None


def inject_probe(game, events=("BOOT",)):
    """临时插入探针插件 + 启动锚点，返回还原所需的上下文。"""
    ctx = {"game": game, "had_title_hook": False}

    # 1) 探针插件：每个事件打印唯一标记，供日志检索
    pdir = os.path.join(game, PROBE_REL_DIR)
    os.makedirs(pdir, exist_ok=True)
    body = [";ZZDRV 临时探针（自动生成，用完即删）"]
    for ev in events:
        body += [
            "@PLUGIN_zzdriver_probe_%s" % ev,
            'PRINTL ZZDRV_FIRED_%s' % ev,
            "OUTPUTLOG",
            "RETURN 0",
            "",
        ]
    _write(os.path.join(pdir, "PLUGIN_ZZDRIVER_PROBE.ERB"), "\n".join(body), True)
    ctx["probe_dir"] = pdir

    # 2) 注册到注册表 + 打开开关旁路
    pm = os.path.join(game, "ERB", "PLUGIN", "PLUGIN_MANAGER.ERB")
    if os.path.isfile(pm):
        ctx["pm_path"] = pm
        t, bom = _read(pm)
        ctx["pm_text"] = t
        ctx["pm_bom"] = bom
        # 找一个空槽位
        slot = None
        for i in range(32):
            if not re.search(r"PLUGIN_ID:%d\s*=" % i, t):
                slot = i
                break
        ctx["slot"] = slot
        if slot is not None:
            t = re.sub(r"(PLUGIN_DESC:\d+\s*= [^\r\n]*\r\n)",
                       lambda m: m.group(1) + "PLUGIN_ID:%d   = zzdriver_probe\r\n"
                                              "PLUGIN_NAME:%d = ZZDRV\r\n"
                                              "PLUGIN_DESC:%d = temp\r\n" % (slot, slot, slot),
                       t, count=1)
            # 旁路开关，保证探针一定被调用
            ctx["gate"] = "\tSIF GLOBAL:(100 + LOCAL_I) == 0\r\n\t\tCONTINUE\r\n"
            t = t.replace(ctx["gate"], "\t;ZZDRV_GATE_BYPASS\r\n")
            _write(pm, t, bom)

    # 3) 启动锚点
    sp = os.path.join(game, SYSTEM_TITLE_REL)
    if os.path.isfile(sp):
        ctx["sp_path"] = sp
        t2, bom2 = _read(sp)
        ctx["sp_text"] = t2
        ctx["sp_bom"] = bom2
        if MARK not in t2:
            ins = "@SYSTEM_TITLE\r\n\t%s\r\n\tCALL PLUGIN_HOOK(\"BOOT\")\r\n" % MARK
            t2 = t2.replace("@SYSTEM_TITLE\r\n", ins, 1)
            _write(sp, t2, bom2)
            ctx["had_title_hook"] = True
    return ctx


def restore(ctx):
    """还原所有改动。"""
    if ctx.get("pm_path") and "pm_text" in ctx:
        _write(ctx["pm_path"], ctx["pm_text"], ctx["pm_bom"])
    if ctx.get("sp_path") and ctx.get("had_title_hook") and "sp_text" in ctx:
        _write(ctx["sp_path"], ctx["sp_text"], ctx["sp_bom"])
    d = ctx.get("probe_dir")
    if d and os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)


def run(game, seconds=25, marker=None, max_wait=None):
    """启动游戏并等待。

    marker 非空时会**轮询等待标记出现**（而不是死等固定秒数）——Emuera 冷启动
    耗时波动较大（实测同一份游戏 25s 有时够、有时不够），固定 sleep 会导致
    「钩子已触发但日志还没写出来」的假阴性。出现标记即提前结束。
    """
    exe = find_exe(game)
    if not exe:
        return False, "找不到 Emuera*.exe"
    log = os.path.join(game, "emuera.log")
    if os.path.isfile(log):
        os.remove(log)

    proc = subprocess.Popen([exe, "-Debug"], cwd=game)

    if marker:
        deadline = time.time() + (max_wait or seconds)
        while time.time() < deadline:
            time.sleep(1.0)
            if proc.poll() is not None:
                break
            txt = read_log(game)
            if txt and marker in txt:
                break
        time.sleep(1.5)  # 让日志落盘完整
    else:
        time.sleep(seconds)
    try:
        proc.kill()
        proc.wait(timeout=10)
    except Exception:
        pass
    # 兜底清进程
    try:
        subprocess.run(["taskkill", "/F", "/IM", os.path.basename(exe)],
                       capture_output=True, timeout=15)
    except Exception:
        pass
    return True, "已运行 %ds" % seconds


PROBE_MARKERS = ("ZZDRV_FIRED_", "ZZDRV_PROBE_MARK", "ZZDRV_GATE_BYPASS", "zzdriver_probe")


def find_residue(game):
    """扫描游戏目录里是否有探针残留（防止 runner 中途被打断留下脏文件）。

    本项目实际踩过：探针进程被强杀时 finally 没跑到，@SYSTEM_TITLE / @EVENTFIRST
    里留下了 PRINTL / OUTPUTLOG 残留，污染了后续所有静态分析。
    """
    hits = []
    for dp, _d, fs in os.walk(os.path.join(game, "ERB")):
        for fn in fs:
            if not fn.lower().endswith((".erb", ".erh")):
                continue
            p = os.path.join(dp, fn)
            try:
                t = open(p, "rb").read().decode("utf-8-sig", errors="replace")
            except Exception:
                continue
            found = [m for m in PROBE_MARKERS if m in t]
            if found:
                hits.append({"file": os.path.relpath(p, game).replace("\\", "/"), "markers": found})
    d = os.path.join(game, PROBE_REL_DIR)
    if os.path.isdir(d):
        hits.append({"file": PROBE_REL_DIR.replace("\\", "/"), "markers": ["<probe dir still exists>"]})
    return hits


def clean_residue(game):
    """清除探针残留，返回清理项列表。"""
    cleaned = []
    for dp, _d, fs in os.walk(os.path.join(game, "ERB")):
        for fn in fs:
            if not fn.lower().endswith((".erb", ".erh")):
                continue
            p = os.path.join(dp, fn)
            try:
                raw = open(p, "rb").read()
                bom = raw.startswith(BOM)
                t = raw.decode("utf-8-sig")
            except Exception:
                continue
            lines = t.split("\r\n")
            keep, removed = [], 0
            for l in lines:
                if any(m in l for m in PROBE_MARKERS) or l.strip() == "OUTPUTLOG":
                    removed += 1
                    continue
                keep.append(l)
            if removed:
                _write(p, "\r\n".join(keep), bom)
                cleaned.append(os.path.relpath(p, game).replace("\\", "/"))
    d = os.path.join(game, PROBE_REL_DIR)
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)
        cleaned.append(PROBE_REL_DIR.replace("\\", "/"))
    return cleaned


def read_log(game):
    """读 emuera.log（UTF-16LE）。"""
    p = os.path.join(game, "emuera.log")
    if not os.path.isfile(p):
        return None
    raw = open(p, "rb").read()
    for enc in ("utf-16-le", "utf-16", "utf-8-sig", "utf-8", "cp932"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_diagnostics(text):
    """把引擎日志解析成结构化诊断 + 运行时调用栈。"""
    diags = []
    stacks = []
    for i, line in enumerate(text.splitlines()):
        m = re.match(r"警告Lv(\d+):([^:]+):(\d+)行目:(.*)$", line.strip())
        if m:
            diags.append({
                "level": int(m.group(1)),
                "file": m.group(2).replace("\\", "/"),
                "line": int(m.group(3)),
                "message": m.group(4).strip(),
            })
        if "エラーが発生しました" in line or "エラー内容" in line:
            stacks.append(line.strip())
        if line.strip().startswith("↑") or line.strip().startswith("現在の関数"):
            stacks.append(line.strip())
    return diags, stacks


def find_marker(text, marker="ZZDRV_FIRED_"):
    """在日志里找探针标记，返回命中的事件名列表。"""
    hits = []
    for line in text.splitlines():
        if marker in line:
            m = re.search(re.escape(marker) + r"(\S+)", line)
            if m:
                hits.append(m.group(1))
    return hits
