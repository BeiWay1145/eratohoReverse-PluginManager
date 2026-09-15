#!/usr/bin/env python3
"""eratohoЯeverse 插件系统安装脚本.

把一个干净的游戏本体改造成支持插件的版本：
  1. 复制 ERB/PLUGIN/ 到游戏目录
  2. 在 5 个主流程位置插入 PLUGIN_HOOK 钩子
  3. 在配置菜单插入 [10] 插件管理 入口

幂等：重复运行不会重复插入。加 --dry-run 只看计划不落盘。
"""
import argparse
import os
import re
import shutil
import sys

BOM = b"\xef\xbb\xbf"

# 每处补丁：(相对路径, 描述, 定位锚点, 替换内容, 是否已安装的判据)
# 语义为「用替换内容整体替换锚点」，因此锚点必须逐字匹配原始文件。
PATCHES = [
    (
        "ERB/SYSTEM/SYSTEM.ERB",
        "BOOT 钩子（新游戏初始化）",
        "SAVEGLOBAL\r\nLOADGLOBAL\r\n",
        "SAVEGLOBAL\r\nLOADGLOBAL\r\n"
        ";插件系统：BOOT 事件钩子（已开启的插件在此时执行）\r\nCALL PLUGIN_HOOK(\"BOOT\")\r\n",
        'CALL PLUGIN_HOOK("BOOT")',
    ),
    (
        "ERB/SYSTEM/SHOP/SHOP.ERB",
        "SHOP 钩子（商店菜单）",
        'CALL HTMLPRINTL(HTMLBUTTON("[888] - 口上表示设定", "888", "设置口上的显示/隐藏"))\r\nDRAWLINE\r\n',
        'CALL HTMLPRINTL(HTMLBUTTON("[888] - 口上表示设定", "888", "设置口上的显示/隐藏"))\r\n'
        ';插件系统：SHOP 事件钩子（已开启的插件在此时执行）\r\nCALL PLUGIN_HOOK("SHOP")\r\nDRAWLINE\r\n',
        'CALL PLUGIN_HOOK("SHOP")',
    ),
    (
        "ERB/TRAIN/EVENTCOMEND.ERB",
        "EVENTCOMEND 钩子（调教结束）",
        ";カウント変数\r\n",
        ';插件系统：EVENTCOMEND 事件钩子（已开启的插件在此时执行）\r\nCALL PLUGIN_HOOK("EVENTCOMEND")\r\n'
        ';カウント変数\r\n',
        'CALL PLUGIN_HOOK("EVENTCOMEND")',
    ),
    (
        "ERB/SYSTEM/CHARAMAKING/CHARA_MAKER.ERB",
        "CHARAMAKE 菜单钩子 + [2] 自定义角色制作分支",
        "\tCALL INPUTINT(0, 1)\r\n",
        '\t;插件系统：CHARAMAKE 菜单钩子（插件可在此附加 [2] 等选项）\r\n'
        '\tCALL PLUGIN_HOOK("CHARAMAKE_MENU")\r\n'
        "\tCALL INPUTINT(0, 1, 2)\r\n"
        "\tIF RESULT == 2\r\n"
        "\t\t;插件自定义角色制作（由已开启插件响应，未响应则回菜单）\r\n"
        '\t\tCALL PLUGIN_HOOK("CHARAMAKE_SELECT")\r\n'
        "\t\tGOTO MAKE_OR_LORD\r\n"
        "\tENDIF\r\n",
        'CALL PLUGIN_HOOK("CHARAMAKE_MENU")',
    ),
]

# 配置菜单入口（三段式：打印菜单项 / 放宽输入范围 / CASE 分支）
CONF_PATH = "ERB/SYSTEM/SHOP/CONFIGURE.ERB"


def read_text(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    bom = raw.startswith(BOM)
    return raw.decode("utf-8-sig"), bom


def write_text(path, text, bom=True):
    data = (BOM if bom else b"") + text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(data)


def find_game(root):
    """校验并返回游戏根目录."""
    if not os.path.isdir(os.path.join(root, "ERB")):
        sys.exit("错误：%s 下没有 ERB/ 目录，这不是游戏根目录" % root)
    exe = [f for f in os.listdir(root) if f.lower().startswith("emuera") and f.lower().endswith(".exe")]
    if not exe:
        print("警告：%s 下没找到 Emuera*.exe，仍继续（可能只是解包目录）" % root)
    return root


def apply_hook(root, rel, desc, anchor, insert, marker, dry):
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        return "SKIP", "%s 不存在（本版本可能没用这个钩子点）" % rel
    text, bom = read_text(path)
    if marker in text:
        return "ALREADY", "%s 已安装，跳过" % desc
    if anchor not in text:
        return "MISS", "定位锚点未找到，需手动处理：%s" % desc
    if not dry:
        write_text(path, text.replace(anchor, insert, 1), bom)
    return "OK", "%s -> %s" % (desc, rel)


def apply_config(root, dry):
    path = os.path.join(root, CONF_PATH)
    if not os.path.isfile(path):
        return "SKIP", "%s 不存在" % CONF_PATH
    text, bom = read_text(path)
    if "PLUGIN_MANAGER" in text:
        return "ALREADY", "配置菜单入口已安装，跳过"

    ok = []
    # 1) 定位真实的输入校验行（紧跟 DO / INPUT 之后，带缩进锚定，避免误匹配菜单打印行）
    m = re.search(r"(\tDO\r\n\t\tINPUT\r\n\t\tLOCAL:0 = !INRANGE\(RESULT, 0, )(\d+)(\))", text)
    if not m:
        return "MISS", "配置菜单输入范围未找到，需手动处理"
    hi = int(m.group(2))
    if not dry:
        # 先放宽范围（用精确区间替换，只动这一处）
        text = text[:m.start(2)] + str(hi + 1) + text[m.end(2):]
        # 再把菜单项插到该 DO 块之前
        m2 = re.search(r"\tDO\r\n\t\tINPUT\r\n", text)
        menu = '\t;插件系统：插件管理入口\r\n\tPRINTFORML %"[' + ("%2d" % (hi + 1)) + '] 插件管理", 50, LEFT%\r\n'
        text = text[:m2.start()] + menu + text[m2.start():]
    ok.append("菜单项 [%d] + 输入范围 0..%d" % (hi + 1, hi + 1))

    # 2) CASE 分支：插在 CASE 7 TO 9 块之后
    m = re.search(r"(\t\tCASE \d+ TO \d+\r\n\t\t\tCALLFORM CONFIG_%CONF_FUNC:\(LOCAL:0 - \d+\)%\r\n)", text)
    if m:
        if not dry:
            text = text[:m.end(1)] + "\t\tCASE %d\r\n\t\t\tCALL PLUGIN_MANAGER\r\n" % (hi + 1) + text[m.end(1):]
        ok.append("CASE %d -> PLUGIN_MANAGER" % (hi + 1))
    else:
        ok.append("!! CASE 分支未自动插入，需手动补")

    if not dry:
        write_text(path, text, bom)
    return "OK", "配置菜单入口：" + "；".join(ok)


def main():
    ap = argparse.ArgumentParser(description="eratohoЯeverse 插件系统安装")
    ap.add_argument("--game", required=True, help="游戏根目录（含 ERB/ 的目录）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不写盘")
    args = ap.parse_args()

    root = find_game(args.game)
    here = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(os.path.dirname(here), "ERB", "PLUGIN")
    if not os.path.isdir(src):
        sys.exit("错误：找不到插件源目录 %s" % src)

    print("游戏目录：%s" % root)
    print("插件源  ：%s" % src)
    print("模式    ：%s" % ("DRY-RUN（不写盘）" if args.dry_run else "写入"))
    print("-" * 62)

    # 1) 复制插件框架（幂等，注意保留 BOM）
    dst = os.path.join(root, "ERB", "PLUGIN")
    if not args.dry_run:
        os.makedirs(dst, exist_ok=True)
        for dirpath, _dirs, files in os.walk(src):
            rel = os.path.relpath(dirpath, src)
            target_dir = os.path.join(dst, rel) if rel != "." else dst
            os.makedirs(target_dir, exist_ok=True)
            for fn in files:
                shutil.copy2(os.path.join(dirpath, fn), os.path.join(target_dir, fn))
    print("[OK]     插件框架 -> ERB/PLUGIN/")

    # 2) 5 处钩子
    for rel, desc, anchor, insert, marker in PATCHES:
        status, msg = apply_hook(root, rel, desc, anchor, insert, marker, args.dry_run)
        print("[%-7s] %s" % (status, msg))

    # 3) 配置菜单
    status, msg = apply_config(root, args.dry_run)
    print("[%-7s] %s" % (status, msg))

    print("-" * 62)
    print("完成。进游戏：商店菜单 -> [178] 配置 -> [%d] 插件管理" % 10)
    if args.dry_run:
        print("（DRY-RUN，未写入任何文件）")


if __name__ == "__main__":
    main()