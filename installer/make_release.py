#!/usr/bin/env python3
"""生成 release 包：同时产出「完整整合包」与「增量覆盖包」。

两种产物
--------
1. 完整整合包 eratohoReverse-<版本>-PluginManager-<日期>-full.zip
   含整个游戏本体 + 插件系统，解压即玩。用户零门槛。
   已排除运行时数据（sav/、emuera.log、debug/ 等）。

2. 增量覆盖包 plugin-<日期>-overlay.zip
   只含被改造过的文件，供已自备游戏本体的用户覆盖。体积小。

用法
----
    python installer/make_release.py --game "<已装好插件的游戏目录>" [--full] [--overlay] [--out DIR]
    默认两个都出。

合规说明
--------
游戏本体版权归 Reverse Developers team（eratohoЯeverse）与汉化组所有；
Emuera 引擎版权归其作者。本工具只是打包，不改动其版权归属。
发布时必须在说明中显著署名，并声明本包仅增加了插件层。
"""
import argparse
import datetime
import os
import zipfile

TARGETS = [
    "ERB/SYSTEM/SYSTEM.ERB",
    "ERB/SYSTEM/SHOP/SHOP.ERB",
    "ERB/SYSTEM/SHOP/CONFIGURE.ERB",
    "ERB/SYSTEM/CHARAMAKING/CHARA_MAKER.ERB",
    "ERB/TRAIN/EVENTCOMEND.ERB",
]

FULL_EXCLUDE_DIRS = {"sav", "debug", ".plugin_backup", "__pycache__", "_zz_orig"}
FULL_EXCLUDE_FILES = {"emuera.log", "setting.json"}
FULL_EXCLUDE_EXT = {".log", ".bak", ".tmp", ".pyc"}


def read_version(game):
    """从 CSV/GameBase.csv 读版本，用于命名。"""
    p = os.path.join(game, "CSV", "GameBase.csv")
    info = {}
    if os.path.isfile(p):
        try:
            raw = open(p, "rb").read()
            try:
                t = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                t = raw.decode("cp932", errors="replace")
            for line in t.splitlines():
                line = line.strip()
                if line and not line.startswith(";") and "," in line:
                    k, v = line.split(",", 1)
                    info[k.strip()] = v.strip()
        except OSError:
            pass
    return info.get("バージョン") or "unknown", info.get("ウィンドウタイトル") or "eratohoЯeverse"


OVERLAY_README = """eratohoЯeverse 插件管理器 —— 增量覆盖包
========================================

本包只含被插件系统改造过的文件，供已经自备游戏本体的用户使用。

构建基线：{title}（版本号 {version}）
请确认你的游戏版本与此一致；不一致请改用 installer/install.py，
它会自适应你的文件结构并明确报告失败项。

安装
----
  1. 备份你的游戏目录（重要）
  2. 把本包内的 ERB/ 整个覆盖到游戏目录的 ERB/ 上
  3. 启动游戏 → 商店菜单 → [178] 配置 → [10] 插件管理

卸载
----
  覆盖回备份，或删除 ERB/PLUGIN/ 目录。

版权
----
游戏本体版权归 Reverse Developers team 与汉化组所有；本包仅含插件层改动。
"""

FULL_README = """eratohoЯeverse + 插件管理器 —— 整合包（解压即玩）
================================================

构建基线：{title}（版本号 {version}）
本包 = 游戏本体 + 插件系统。解压后双击 Emuera*.exe 即可游玩。

怎么用
------
  1. 解压到任意目录（路径尽量不含中文，避免个别环境异常）
  2. 双击 Emuera1824+v1.exe 启动
  3. 进入游戏后：商店菜单 → [178] 配置 → [10] 插件管理
     在那里可以独立开启/关闭每个插件（默认全部关闭）

已内置插件
----------
  [0] 角色制作增强（custom）
      在角色菜单增加 [2] 自定义角色制作：
      可自由设定姓名 / 性别（男·女·扶她）/ 性格 / 性质 / 经验，
      制作结果保存到存档槽位，可被 [1] 加载角色 正常读取。

插件是什么
----------
每个插件是 ERB/PLUGIN/<插件ID>/ 下的独立脚本，删除该目录即卸载。
开发指南见 ERB/PLUGIN/PLUGIN_DEV_GUIDE.md。

更多插件与更新
--------------
  https://github.com/BeiWay1145/eratohoReverse-PluginManager

————————————————————————————————
版权与署名（请务必阅读）
————————————————————————————————
· 游戏本体：eratohoЯeverse，版权归 Reverse Developers team 所有。
· 中文汉化：版权归汉化组所有。本包未对汉化内容做任何改动，
  仅在其之上增加了插件层。
· Emuera 引擎（Emuera1824+v1.exe）：版权归其原作者所有。
· 东方 Project 二次创作，版权归 上海アリス幻樂団 / ZUN 所有。
· 插件系统与插件：BeiWay1145。

本包仅增加了插件系统，其余内容均来自上述原作者与汉化组。
若您是权利人且不希望被包含，请联系删除。

分发条件（摘自原版 readme）
--------------------------
「サポートは各バリアントの作者が行う事が改編・再配布の条件となっています」
即：允许改编与再分发，条件是由本 variant 的作者（而非原引擎/东方原作者）
提供支持。请勿就本包向原引擎作者或上海アリス幻樂団咨询。

————————————————————————————————
注意：本游戏含过激性描写，18 岁以下禁止游玩。
"""


def build_full(game, outdir, stamp, version, title):
    zpath = os.path.join(outdir, "eratohoReverse-%s-PluginManager-%s-full.zip" % (version, stamp))
    n = 0
    total = 0
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for dp, dirs, fs in os.walk(game):
            dirs[:] = [d for d in dirs if d not in FULL_EXCLUDE_DIRS]
            for fn in fs:
                if fn in FULL_EXCLUDE_FILES:
                    continue
                if os.path.splitext(fn)[1].lower() in FULL_EXCLUDE_EXT:
                    continue
                full = os.path.join(dp, fn)
                arc = os.path.relpath(full, game).replace(os.sep, "/")
                z.write(full, arc)
                n += 1
                total += os.path.getsize(full)
            # zip 不保存空目录条目；显式补上，否则原作/汉化组的目录结构会缺失
            if not dirs and not fs and dp != game:
                z.writestr(os.path.relpath(dp, game).replace(os.sep, "/") + "/", b"")
                n += 1
        z.writestr("README-先读我.txt", FULL_README.format(version=version, title=title))
    return zpath, n + 1, total


def build_overlay(game, outdir, stamp, version, title):
    zpath = os.path.join(outdir, "plugin-%s-overlay.zip" % stamp)
    n = 0
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel in TARGETS:
            p = os.path.join(game, rel)
            if os.path.isfile(p):
                z.write(p, rel)
                n += 1
        pdir = os.path.join(game, "ERB", "PLUGIN")
        for dp, _d, fs in os.walk(pdir):
            for fn in fs:
                full = os.path.join(dp, fn)
                z.write(full, os.path.relpath(full, game).replace(os.sep, "/"))
                n += 1
        z.writestr("README-安装.txt", OVERLAY_README.format(version=version, title=title))
    return zpath, n + 1


def main():
    ap = argparse.ArgumentParser(description="生成 release 包（完整整合包 + 增量覆盖包）")
    ap.add_argument("--game", required=True, help="已装好插件的游戏目录")
    ap.add_argument("--out", default=None, help="输出目录（默认 <仓库>/release/）")
    ap.add_argument("--full", action="store_true", help="只出完整整合包")
    ap.add_argument("--overlay", action="store_true", help="只出增量覆盖包")
    args = ap.parse_args()

    game = args.game
    if not os.path.isdir(os.path.join(game, "ERB", "PLUGIN")):
        raise SystemExit("错误：%s 未安装插件系统（找不到 ERB/PLUGIN/）" % game)

    outdir = args.out or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "release")
    os.makedirs(outdir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d")
    version, title = read_version(game)
    print("构建基线：%s（バージョン=%s）" % (title, version))
    print("输出目录：%s" % outdir)
    print("-" * 62)

    do_full = args.full or not args.overlay
    do_overlay = args.overlay or not args.full

    if do_full:
        p, n, total = build_full(game, outdir, stamp, version, title)
        print("[完整整合包] %s" % os.path.basename(p))
        print("             文件数 %d，原始 %.1f MB，压缩后 %.1f MB" % (
            n, total / 1048576.0, os.path.getsize(p) / 1048576.0))
    if do_overlay:
        p, n = build_overlay(game, outdir, stamp, version, title)
        print("[增量覆盖包] %s" % os.path.basename(p))
        print("             文件数 %d，压缩后 %.1f KB" % (n, os.path.getsize(p) / 1024.0))


if __name__ == "__main__":
    main()