#!/usr/bin/env python3
"""安装器回归测试：对多种「破坏版」游戏样本验证模糊匹配与失败报告。

用法：
    python tests/test_installer.py --game "<纯净游戏目录>"

会复制多份样本、施加不同破坏、跑安装器、断言预期行为。
不修改原游戏目录。
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BOM = b"\xef\xbb\xbf"
INSTALLER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "installer", "install.py")

H = {
    "sys": "ERB/SYSTEM/SYSTEM.ERB",
    "shop": "ERB/SYSTEM/SHOP/SHOP.ERB",
    "evt": "ERB/TRAIN/EVENTCOMEND.ERB",
    "chara": "ERB/SYSTEM/CHARAMAKING/CHARA_MAKER.ERB",
    "conf": "ERB/SYSTEM/SHOP/CONFIGURE.ERB",
}


def read(p):
    raw = open(p, "rb").read()
    return raw.decode("utf-8-sig").replace("\r\n", "\n"), raw.startswith(BOM)


def write(p, text, bom):
    open(p, "wb").write((BOM if bom else b"") + text.replace("\n", "\r\n").encode("utf-8"))


def _decode(raw):
    """子进程在 Windows 上按控制台代码页输出，逐级尝试解码。"""
    for enc in ("utf-8", "cp936", "cp932", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def run_installer(game):
    # 强制子进程用 UTF-8 输出，避免代码页差异
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run([sys.executable, INSTALLER, "--game", game],
                       capture_output=True, env=env)
    return r.returncode, _decode(r.stdout)


def mutate(root, rel, old, new):
    p = os.path.join(root, rel)
    text, bom = read(p)
    if old not in text:
        return False
    write(p, text.replace(old, new, 1), bom)
    return True


CASES = []


def case(name, expect_rc, expect_substr, mutations):
    CASES.append((name, expect_rc, expect_substr, mutations))


# 1) 干净本体：应全部装成功
case("干净本体", 0, "安装 5", {})

# 2) 文本被改（汉化润色）：结构锚点仍应命中
case("按钮文案被改", 0, "安装 5", {H["shop"]: [("口上表示设定", "口上显示设置")]})

# 3) BOOT 主锚点被破坏：兜底锚点应接管
case("BOOT主锚点被破坏", 0, "安装 5", {H["sys"]: [("SAVEGLOBAL\nLOADGLOBAL\n", "SAVEGLOBAL\n;新注释\nLOADGLOBAL\n")]})

# 4) CHARAMAKE 锚点消失：应报 MISS 且返回码非 0
case("CHARAMAKE锚点消失", 1, "失败 1", {H["chara"]: [("\tCALL INPUTINT(0, 1)\n", "\tCALL INPUTINT(0, 1, 3)\n")]})

# 5) CONFIGURE 的 CASE 形式变化：应自适应
case("CASE形式变化", 0, "安装 5", {H["conf"]: [("\t\tCASE 7 TO 9\n", "\t\tCASE 6 TO 9\n")]})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True, help="纯净游戏目录（不会被修改）")
    args = ap.parse_args()

    src = args.game
    if not os.path.isdir(os.path.join(src, "ERB")):
        sys.exit("不是游戏目录：%s" % src)

    tmp = tempfile.mkdtemp(prefix="plugintest-")
    passed = failed = 0
    try:
        for i, (name, expect_rc, expect_sub, mutations) in enumerate(CASES, 1):
            dst = os.path.join(tmp, "case%d" % i)
            shutil.copytree(src, dst)
            ok_mut = True
            for rel, pairs in mutations.items():
                for old, new in pairs:
                    if not mutate(dst, rel, old, new):
                        ok_mut = False
            if not ok_mut:
                print("  [SKIP] %s（样本该版本不匹配，跳过）" % name)
                continue

            rc, out = run_installer(dst)
            hit = expect_sub in out
            good = (rc == expect_rc) and hit
            print("  [%s] %s  (rc=%d 期望%d, 输出含%r=%s)" % (
                "PASS" if good else "FAIL", name, rc, expect_rc, expect_sub, hit))
            if good:
                passed += 1
            else:
                failed += 1
                print("        --- 输出尾部 ---")
                for l in out.splitlines()[-6:]:
                    print("        " + l)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n通过 %d / 失败 %d" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())