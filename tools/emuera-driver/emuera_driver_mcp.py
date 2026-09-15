#!/usr/bin/env python3
"""emuera-driver MCP 服务器：让 agent 能真正"运行并读取" Emuera 游戏。

与 era-mcp（静态语法分析）互补：
  - era-mcp        ：读 ERB/CSV，答"代码写得对不对"
  - emuera-driver  ：启动游戏、抓引擎日志，答"运行时到底发生了什么"

工具：
  emuera_run        启动游戏跑一段时间，返回引擎诊断 + 探针事件
  emuera_log        读取并解析 emuera.log（编译警告 + 运行时调用栈）
  emuera_probe      注入探针验证插件钩子链路，自动还原
  emuera_doctor     环境自检（可执行文件/配置/插件是否就位）

依赖：仅标准库 + emuera_driver_core。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emuera_driver_core as C  # noqa: E402

# 强制 UTF-8 输出，避免 Windows 控制台代码页（GBK）把 JSON 写坏
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="strict")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SERVER_NAME = "emuera-driver"
SERVER_VERSION = "1.0.0"
PROTOCOL = "2024-11-05"


TOOLS = [
    {
        "name": "emuera_run",
        "description": (
            "启动 Emuera 游戏并运行指定秒数，然后读取引擎日志。"
            "返回：编译/运行时诊断（按文件与等级分组）、探针事件、日志行数。"
            "用于确认改动后游戏能否正常启动、有无新警告。"
            "注意：游戏是 GUI 程序，本工具只做「启动+抓日志」，不注入按键。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "game": {"type": "string", "description": "游戏根目录（含 ERB/ 与 Emuera*.exe）"},
                "seconds": {"type": "integer", "description": "运行秒数，默认 25"},
                "with_probe": {"type": "boolean", "description": "是否注入探针并验证钩子链路，默认 true"},
                "events": {
                    "type": "array", "items": {"type": "string"},
                    "description": "探针要挂的事件名，默认 ['BOOT']"
                },
            },
            "required": ["game"],
        },
    },
    {
        "name": "emuera_log",
        "description": (
            "读取并解析 <游戏>/emuera.log（Emuera 用 OUTPUTLOG 命令导出的引擎日志，UTF-16LE）。"
            "返回结构化诊断列表（等级/文件/行号/消息）与运行时调用栈。"
            "不做任何改动，纯读取。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "game": {"type": "string"},
                "file_filter": {"type": "string", "description": "只看文件名含该子串的诊断，如 'PLUGIN'"},
                "min_level": {"type": "integer", "description": "最低等级（1 或 2），默认 1"},
                "limit": {"type": "integer", "description": "最多返回条数，默认 200"},
            },
            "required": ["game"],
        },
    },
    {
        "name": "emuera_probe",
        "description": (
            "注入一个临时探针插件（在每个指定事件里 PRINTL 唯一标记 + OUTPUTLOG），"
            "并在 @SYSTEM_TITLE 挂上启动钩子，跑一次游戏后从引擎日志里检索标记，"
            "据此证明 PLUGIN_HOOK → TRYCALLFORM 分发是否真的到达了插件。"
            "运行结束自动完整还原（探针文件、注册表、开关、锚点）。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "game": {"type": "string"},
                "events": {
                    "type": "array", "items": {"type": "string"},
                    "description": "要验证的事件名，默认 ['BOOT']"
                },
                "seconds": {"type": "integer", "description": "运行秒数，默认 25"},
            },
            "required": ["game"],
        },
    },
    {
        "name": "emuera_doctor",
        "description": "环境自检：可执行文件、emuera.config 关键项、插件系统是否就位、emuera.log 是否存在。",
        "inputSchema": {
            "type": "object",
            "properties": {"game": {"type": "string"}},
            "required": ["game"],
        },
    },
]


def _doctor(game):
    rep = {"game": game, "checks": []}
    exe = C.find_exe(game)
    rep["checks"].append({"item": "Emuera 可执行文件", "ok": bool(exe),
                          "detail": os.path.basename(exe) if exe else "未找到"})
    erb = os.path.join(game, "ERB")
    rep["checks"].append({"item": "ERB 目录", "ok": os.path.isdir(erb), "detail": erb})
    pm = os.path.join(erb, "PLUGIN", "PLUGIN_MANAGER.ERB")
    rep["checks"].append({"item": "插件系统", "ok": os.path.isfile(pm),
                          "detail": "已安装" if os.path.isfile(pm) else "未安装"})
    cfg = os.path.join(game, "emuera.config")
    if os.path.isfile(cfg):
        try:
            t = open(cfg, "rb").read().decode("utf-8-sig", errors="replace")
            dbg = "デバッグコマンドを使用する:YES" in t
            rep["checks"].append({"item": "调试命令", "ok": dbg,
                                  "detail": "已启用" if dbg else "未启用（@OUTPUT 等调试命令不可用）"})
        except Exception as e:
            rep["checks"].append({"item": "emuera.config", "ok": False, "detail": str(e)})
    else:
        rep["checks"].append({"item": "emuera.config", "ok": False, "detail": "未找到"})
    rep["checks"].append({"item": "emuera.log", "ok": os.path.isfile(os.path.join(game, "emuera.log")),
                          "detail": "存在" if os.path.isfile(os.path.join(game, "emuera.log")) else "尚未生成"})
    return rep


def _aggregate(diags):
    by_file = {}
    by_level = {}
    for d in diags:
        by_file[d["file"]] = by_file.get(d["file"], 0) + 1
        by_level[d["level"]] = by_level.get(d["level"], 0) + 1
    top = sorted(by_file.items(), key=lambda kv: -kv[1])[:15]
    return {
        "total": len(diags),
        "by_level": by_level,
        "top_files": [{"file": f, "count": n} for f, n in top],
    }


def handle(name, args):
    game = args.get("game")
    if not game:
        return {"error": "缺少参数 game"}
    if not os.path.isdir(os.path.join(game, "ERB")):
        return {"error": "不是游戏目录（无 ERB/）：%s" % game}

    if name == "emuera_doctor":
        return _doctor(game)

    if name == "emuera_log":
        t = C.read_log(game)
        if t is None:
            return {"error": "找不到 emuera.log。先跑一次 emuera_run（探针里含 OUTPUTLOG）或游戏内执行 @OUTPUT。"}
        diags, stacks = C.parse_diagnostics(t)
        ff = args.get("file_filter")
        if ff:
            diags = [d for d in diags if ff.lower() in d["file"].lower()]
        mn = int(args.get("min_level", 1))
        diags = [d for d in diags if d["level"] >= mn]
        lim = int(args.get("limit", 200))
        return {
            "logLines": len(t.splitlines()),
            "diagnosticCount": len(diags),
            "diagnostics": diags[:lim],
            "truncated": len(diags) > lim,
            "runtimeStacks": stacks[-20:],
        }

    if name in ("emuera_run", "emuera_probe"):
        with_probe = name == "emuera_probe" or bool(args.get("with_probe", True))
        events = args.get("events") or ["BOOT"]
        secs = int(args.get("seconds", 25))

        ctx = None
        try:
            if with_probe:
                ctx = C.inject_probe(game, events=tuple(events))
                ok, note = C.run(game, seconds=secs,
                                 marker="ZZDRV_FIRED_",
                                 max_wait=max(secs, 60))
            else:
                ok, note = C.run(game, seconds=secs)
        finally:
            if ctx:
                C.restore(ctx)

        t = C.read_log(game)
        if t is None:
            return {"ok": False, "note": note, "error": "运行后仍无 emuera.log"}
        diags, stacks = C.parse_diagnostics(t)
        fired = C.find_marker(t)
        return {
            "ok": True,
            "note": note,
            "probeInjected": bool(ctx),
            "probeEventsRequested": events,
            "probeEventsFired": sorted(set(fired)),
            "hookDispatchVerified": len(fired) > 0,
            "logLines": len(t.splitlines()),
            "summary": _aggregate(diags),
            "runtimeStacks": stacks[-20:],
        }

    return {"error": "未知工具：%s" % name}


def send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        method = req.get("method")
        rid = req.get("id")

        if method == "initialize":
            send({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": PROTOCOL,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            }})
        elif method == "notifications/initialized":
            pass
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            p = req.get("params") or {}
            try:
                result = handle(p.get("name"), p.get("arguments") or {})
            except Exception as e:
                result = {"error": "%s: %s" % (type(e).__name__, e)}
            send({"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
                "isError": "error" in result,
            }})
        elif rid is not None:
            send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "method not found"}})


if __name__ == "__main__":
    main()
