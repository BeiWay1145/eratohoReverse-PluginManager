#!/usr/bin/env python3
"""eratohoЯeverse 插件系统安装脚本（加固版）。

把一个干净的游戏本体改造成支持插件的版本。

加固点：
  1. **版本探测** —— 从 CSV/GameBase.csv 读取 バージョン / ウィンドウタイトル，
     装入报告，便于确认"这份补丁是否适配当前游戏版本"。
  2. **结构锚点优先、字面锚点兜底** —— 每处钩子给出多个候选锚点，
     按优先级依次尝试，任一命中即可；文案变动不再直接导致失败。
  3. **幂等** —— 重复运行不会重复插入。
  4. **可回滚** —— --backup 时把改动前文件存到 <游戏>/.plugin_backup/<时间戳>/。

用法：
    python installer/install.py --game "<游戏目录>"
    python installer/install.py --game "<游戏目录>" --dry-run
    python installer/install.py --game "<游戏目录>" --backup
"""
import argparse
import datetime
import os
import re
import shutil
import sys

BOM = b"\xef\xbb\xbf"


def read_text(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    return raw.decode("utf-8-sig"), raw.startswith(BOM)


def write_text(path, text, bom=True):
    data = (BOM if bom else b"") + text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(data)


def detect_version(root):
    """从 CSV/GameBase.csv 读取版本信息；读不到返回 None（不阻断安装）。"""
    p = os.path.join(root, "CSV", "GameBase.csv")
    if not os.path.isfile(p):
        return None
    try:
        with open(p, "rb") as fh:
            raw = fh.read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp932", errors="replace")
    except OSError:
        return None

    info = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(";") or "," not in line:
            continue
        k, v = line.split(",", 1)
        info[k.strip()] = v.strip()
    return {
        "version": info.get("バージョン"),
        "title": info.get("ウィンドウタイトル"),
        "code": info.get("コード"),
    }


# 每个补丁：(相对路径, 描述, [(锚点正则, 替换模板), ...], 已安装判据)
# 候选锚点按顺序尝试，第一个命中者胜出 —— 结构锚点在前，兜底锚点在后。
PATCHES = [
    (
        "ERB/SYSTEM/SYSTEM.ERB",
        "BOOT 钩子（新游戏初始化）",
        [
            (r"(SAVEGLOBAL\r\nLOADGLOBAL\r\n)",
             "\\1;插件系统：BOOT 事件钩子（已开启的插件在此时执行）\r\nCALL PLUGIN_HOOK(\"BOOT\")\r\n"),
            (r"(?m)^(LOADGLOBAL\r\n)(?=;キャラクター役割変数を初期化)",
             ";插件系统：BOOT 事件钩子（已开启的插件在此时执行）\r\nCALL PLUGIN_HOOK(\"BOOT\")\r\n\\1"),
        ],
        'CALL PLUGIN_HOOK("BOOT")',
    ),
    (
        "ERB/SYSTEM/SHOP/SHOP.ERB",
        "SHOP 钩子（商店菜单）",
        [
            (r'(CALL HTMLPRINTL\(HTMLBUTTON\(\"\[888\][^\r\n]*\)\)\r\n)(?=DRAWLINE\r\n)',
             "\\1;插件系统：SHOP 事件钩子（已开启的插件在此时执行）\r\nCALL PLUGIN_HOOK(\"SHOP\")\r\n"),
            (r'(\[888\][^\r\n]*\"\r\n)(?=DRAWLINE\r\n)',
             "\\1;插件系统：SHOP 事件钩子（已开启的插件在此时执行）\r\nCALL PLUGIN_HOOK(\"SHOP\")\r\n"),
        ],
        'CALL PLUGIN_HOOK("SHOP")',
    ),
    (
        "ERB/TRAIN/EVENTCOMEND.ERB",
        "EVENTCOMEND 钩子（调教结束）",
        [
            (r"(@EVENTCOMEND\r\n)",
             "\\1;插件系统：EVENTCOMEND 事件钩子（已开启的插件在此时执行）\r\nCALL PLUGIN_HOOK(\"EVENTCOMEND\")\r\n"),
        ],
        'CALL PLUGIN_HOOK("EVENTCOMEND")',
    ),
    (
        "ERB/SYSTEM/CHARAMAKING/CHARA_MAKER.ERB",
        "CHARAMAKE 菜单钩子 + [2] 自定义角色制作分支",
        [
            (r"(?m)^(\tCALL INPUTINT\(0, 1\)\r\n)",
             "\t;插件系统：CHARAMAKE 菜单钩子（插件可在此附加 [2] 等选项）\r\n"
             '\tCALL PLUGIN_HOOK("CHARAMAKE_MENU")\r\n'
             "\tCALL INPUTINT(0, 1, 2)\r\n"
             "\tIF RESULT == 2\r\n"
             "\t\t;插件自定义角色制作（由已开启插件响应，未响应则回菜单）\r\n"
             '\t\tCALL PLUGIN_HOOK("CHARAMAKE_SELECT")\r\n'
             "\t\tGOTO MAKE_OR_LORD\r\n"
             "\tENDIF\r\n"),
        ],
        'CALL PLUGIN_HOOK("CHARAMAKE_MENU")',
    ),
]

CONF_PATH = "ERB/SYSTEM/SHOP/CONFIGURE.ERB"


def apply_patch(root, rel, desc, candidates, marker, dry):
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        return "SKIP", "%s 不存在（本版本可能未使用该钩子点）" % rel
    text, bom = read_text(path)
    if marker in text:
        return "ALREADY", "%s 已安装，跳过" % desc

    for idx, (pattern, repl) in enumerate(candidates):
        m = re.search(pattern, text)
        if not m:
            continue
        new_text = text[:m.start()] + m.expand(repl) + text[m.end():]
        if not dry:
            write_text(path, new_text, bom)
        return "OK", "%s -> %s（%s）" % (desc, rel, "结构锚点" if idx == 0 else "兜底锚点#%d" % idx)

    return "MISS", "%s：所有锚点均未命中，需手动处理 -> %s" % (desc, rel)


def apply_config(root, dry):
    path = os.path.join(root, CONF_PATH)
    if not os.path.isfile(path):
        return "SKIP", "%s 不存在" % CONF_PATH
    text, bom = read_text(path)
    if "PLUGIN_MANAGER" in text:
        return "ALREADY", "配置菜单入口已安装，跳过"

    m = re.search(r"(\tDO\r\n\t\tINPUT\r\n\t\tLOCAL:0 = !INRANGE\(RESULT, 0, )(\d+)(\))", text)
    if not m:
        return "MISS", "配置菜单输入范围未找到，需手动处理"
    hi = int(m.group(2))
    case_ok = True

    if not dry:
        text = text[:m.start(2)] + str(hi + 1) + text[m.end(2):]
        m2 = re.search(r"\tDO\r\n\t\tINPUT\r\n", text)
        menu = ('\t;插件系统：插件管理入口\r\n\tPRINTFORML %"[' +
                ("%2d" % (hi + 1)) + '] 插件管理", 50, LEFT%\r\n')
        text = text[:m2.start()] + menu + text[m2.start():]
        m3 = re.search(r"(\t\tCASE \d+ TO \d+\r\n\t\t\tCALLFORM CONFIG_%CONF_FUNC:\(LOCAL:0 - \d+\)%\r\n)", text)
        if m3:
            text = text[:m3.end(1)] + "\t\tCASE %d\r\n\t\t\tCALL PLUGIN_MANAGER\r\n" % (hi + 1) + text[m3.end(1):]
        else:
            case_ok = False
        write_text(path, text, bom)

    note = "菜单项 [%d] + 范围 0..%d" % (hi + 1, hi + 1)
    if not case_ok:
        note += "（!! CASE 分支未自动插入，需手动补）"
    return "OK", "配置菜单入口：" + note


def main():
    ap = argparse.ArgumentParser(description="eratohoЯeverse 插件系统安装（加固版）")
    ap.add_argument("--game", required=True, help="游戏根目录（含 ERB/ 的目录）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不写盘")
    ap.add_argument("--backup", action="store_true", help="改动前备份到 <游戏>/.plugin_backup/")
    args = ap.parse_args()

    root = args.game
    if not os.path.isdir(os.path.join(root, "ERB")):
        sys.exit("错误：%s 下没有 ERB/ 目录，这不是游戏根目录" % root)
    if not [f for f in os.listdir(root) if f.lower().startswith("emuera") and f.lower().endswith(".exe")]:
        print("警告：没找到 Emuera*.exe，仍继续（可能只是解包目录）")

    here = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(os.path.dirname(here), "ERB", "PLUGIN")
    if not os.path.isdir(src):
        sys.exit("错误：找不到插件源目录 %s" % src)

    print("=" * 64)
    print("游戏目录：%s" % root)
    ver = detect_version(root)
    if ver and ver["version"]:
        print("游戏版本：%s（バージョン=%s, コード=%s）" % (ver["title"] or "?", ver["version"], ver["code"] or "?"))
    else:
        print("游戏版本：未能从 CSV/GameBase.csv 读取（继续）")
    print("模式    ：%s%s" % ("DRY-RUN（不写盘）" if args.dry_run else "写入",
                              "，改动前备份" if args.backup else ""))
    print("=" * 64)

    if args.backup and not args.dry_run:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        bdir = os.path.join(root, ".plugin_backup", stamp)
        for rel, *_ in PATCHES + [(CONF_PATH,)]:
            p = os.path.join(root, rel)
            if os.path.isfile(p):
                d = os.path.join(bdir, rel)
                os.makedirs(os.path.dirname(d), exist_ok=True)
                shutil.copy2(p, d)
        print("[BACKUP  ] 已备份到 %s" % bdir)

    dst = os.path.join(root, "ERB", "PLUGIN")
    if not args.dry_run:
        for dirpath, _dirs, files in os.walk(src):
            rel = os.path.relpath(dirpath, src)
            target_dir = os.path.join(dst, rel) if rel != "." else dst
            os.makedirs(target_dir, exist_ok=True)
            for fn in files:
                shutil.copy2(os.path.join(dirpath, fn), os.path.join(target_dir, fn))
    print("[OK      ] 插件框架 -> ERB/PLUGIN/")

    counts = {"OK": 0, "ALREADY": 0, "MISS": 0, "SKIP": 0}
    for rel, desc, cands, marker in PATCHES:
        status, msg = apply_patch(root, rel, desc, cands, marker, args.dry_run)
        counts[status] = counts.get(status, 0) + 1
        print("[%-8s] %s" % (status, msg))

    status, msg = apply_config(root, args.dry_run)
    counts[status] = counts.get(status, 0) + 1
    print("[%-8s] %s" % (status, msg))

    print("=" * 64)
    print("结果：安装 %d / 已装 %d / 跳过 %d / 失败 %d" %
          (counts["OK"], counts["ALREADY"], counts["SKIP"], counts["MISS"]))
    if counts["MISS"]:
        print("!! 有 %d 处未能自动安装，请按 installer/HOOKS.md 手动处理" % counts["MISS"])
    if args.dry_run:
        print("（DRY-RUN，未写入任何文件）")
    else:
        print("进游戏：商店菜单 -> [178] 配置 -> [10] 插件管理")
    return 1 if counts["MISS"] else 0


if __name__ == "__main__":
    sys.exit(main())
