#!/usr/bin/env python3
"""确保 .ERB/.ERH 文件为 UTF-8 BOM + CRLF（游戏本体的硬性编码要求）.

不少编辑器与自动化工具写回文件时会丢掉 BOM，导致 Emuera 解析异常。
用法：
    python tools/fix_bom.py <目录或文件> [...]
"""
import os
import sys

BOM = b"\xef\xbb\xbf"


def fix(path, apply):
    raw = open(path, "rb").read()
    changed = []
    if not raw.startswith(BOM):
        raw = BOM + raw
        changed.append("BOM")
    norm = raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    if norm != raw:
        raw = norm
        changed.append("CRLF")
    if changed and apply:
        open(path, "wb").write(raw)
    return changed


def main():
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    apply = "--dry-run" not in sys.argv
    if not args:
        sys.exit(__doc__)

    targets = []
    for a in args:
        if os.path.isdir(a):
            for dp, _d, fs in os.walk(a):
                targets += [os.path.join(dp, f) for f in fs
                            if f.lower().endswith((".erb", ".erh"))]
        else:
            targets.append(a)

    n = 0
    for p in sorted(targets):
        ch = fix(p, apply)
        if ch:
            n += 1
            print("  %-8s %s" % ("+".join(ch), p))
    print("%d 个文件%s" % (n, "已修正" if apply else "需要修正（dry-run）"))


if __name__ == "__main__":
    main()
