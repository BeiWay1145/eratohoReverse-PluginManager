#!/usr/bin/env python3
"""生成 release 包：把「已装好插件」的增量文件打包，供不想跑脚本的用户直接覆盖。

产物：release/plugin-<版本日期>.zip，内含：
    ERB/PLUGIN/**            插件框架
    ERB/SYSTEM/SYSTEM.ERB    已打钩子的主流程文件
    ...（共 5 个改造后的文件）
    README-安装.txt

注意：release 包**只含被改造的文件**（增量覆盖），不含整个游戏本体。
用法：
    python installer/make_release.py --game "<已安装插件的游戏目录>"
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

README = """eratohoЯeverse 插件管理器 —— 增量覆盖包

本包只包含「被插件系统改造过的文件」，用于已经装好游戏本体的用户。

安装：
  1. 备份你的游戏目录（重要）
  2. 把本包内的 ERB/ 整个覆盖到游戏目录的 ERB/ 上
  3. 进游戏：商店菜单 -> [178] 配置 -> [10] 插件管理

⚠️ 版本要求：本包针对特定游戏版本构建。
   如果你的游戏版本与构建版本不同，建议改用 installer/install.py，
   它会自适应你的文件结构并报告失败项。

卸载：覆盖回备份，或删除 ERB/PLUGIN/ 目录。
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True, help="已装好插件的游戏目录")
    ap.add_argument("--out", default=None,
                    help="输出目录（默认 <仓库>/release/）")
    args = ap.parse_args()

    root = args.game
    if not os.path.isdir(os.path.join(root, "ERB", "PLUGIN")):
        raise SystemExit("错误：%s 未安装插件系统（找不到 ERB/PLUGIN/）" % root)

    stamp = datetime.datetime.now().strftime("%Y%m%d")
    outdir = args.out or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "release")
    os.makedirs(outdir, exist_ok=True)
    zpath = os.path.join(outdir, "plugin-%s.zip" % stamp)

    n = 0
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        # 主流程改造文件
        for rel in TARGETS:
            p = os.path.join(root, rel)
            if os.path.isfile(p):
                z.write(p, rel)
                n += 1
        # 插件目录整树
        pdir = os.path.join(root, "ERB", "PLUGIN")
        for dp, _d, fs in os.walk(pdir):
            for fn in fs:
                full = os.path.join(dp, fn)
                z.write(full, os.path.relpath(full, root))
                n += 1
        z.writestr("README-安装.txt", README)

    size = os.path.getsize(zpath)
    print("已生成：%s" % zpath)
    print("  文件数：%d，大小：%.1f KB" % (n + 1, size / 1024.0))


if __name__ == "__main__":
    main()