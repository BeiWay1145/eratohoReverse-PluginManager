#!/usr/bin/env python3
"""驱动 eratohoЯeverse 走到「新游戏」，验证插件钩子真实触发。

Emuera 是 GUI 程序：@EVENTFIRST（BOOT 钩子所在）只在标题画面选择
[0] NEW GAME 后执行。本脚本用 ctypes 直接向窗口 PostMessage 发送按键，
比 SendKeys 更可靠（不依赖前台焦点）。

验证方式：插件用 SAVETEXT 把证据写进文件，脚本检查该文件是否存在。

用法：
    python tests/drive_newgame.py --game "<游戏目录>" [--evidence 文件名]
"""
import argparse
import ctypes
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

u32 = ctypes.windll.user32

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
VK_RETURN = 0x0D


def find_window(pid):
    """按进程 ID 找顶层窗口。"""
    found = []
    EnumWindows = u32.EnumWindows
    cb = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def each(h, _l):
        wpid = ctypes.c_ulong()
        u32.GetWindowThreadProcessId(h, ctypes.byref(wpid))
        if wpid.value == pid and u32.IsWindowVisible(h):
            n = ctypes.create_unicode_buffer(512)
            u32.GetWindowTextW(h, n, 512)
            if n.value:
                found.append((h, n.value))
        return True

    EnumWindows(cb(each), 0)
    return found


def send_key(hwnd, vk, shift=False):
    """向窗口投递一次按键（含必要时用字符消息投递数字）。"""
    scan = u32.MapVirtualKeyW(vk, 0)
    lparam_down = 1 | (scan << 16)
    u32.PostMessageW(hwnd, WM_KEYDOWN, vk, lparam_down)
    time.sleep(0.05)
    u32.PostMessageW(hwnd, WM_KEYUP, vk, lparam_down | (1 << 30) | (1 << 31))
    time.sleep(0.12)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True)
    ap.add_argument("--evidence", default="SMOKETEST_BOOT_FIRED.txt")
    ap.add_argument("--wait", type=int, default=10, help="启动后等待秒数")
    args = ap.parse_args()

    game = args.game
    exe = None
    for f in os.listdir(game):
        if f.lower().startswith("emuera") and f.lower().endswith(".exe"):
            exe = os.path.join(game, f)
            break
    if not exe:
        sys.exit("找不到 Emuera*.exe")

    ev = os.path.join(game, args.evidence)
    gs = os.path.join(game, "sav", "global.sav")
    for p in (ev, gs):
        if os.path.isfile(p):
            os.remove(p)

    import subprocess
    proc = subprocess.Popen([exe], cwd=game)
    print("已启动 pid=%d" % proc.pid)
    time.sleep(args.wait)

    if proc.poll() is not None:
        print("游戏提前退出，exit=%s" % proc.returncode)
        return 1

    wins = find_window(proc.pid)
    print("找到窗口：%r" % (wins,))
    if not wins:
        print("!! 未找到窗口，无法驱动")
        proc.kill()
        return 1

    hwnd, title = wins[0]
    print("窗口标题：%s" % title)

    # 标题菜单：[0] NEW GAME -> 回车确认
    print("发送按键：0 ...")
    send_key(hwnd, 0x30)          # '0'
    time.sleep(1.0)
    print("发送按键：Enter ...")
    send_key(hwnd, VK_RETURN)
    time.sleep(2.0)
    send_key(hwnd, VK_RETURN)
    time.sleep(args.wait)

    alive = proc.poll() is None
    print("操作后存活：%s" % alive)

    proc.kill()
    proc.wait()
    time.sleep(1)

    has_ev = os.path.isfile(ev)
    print("-" * 50)
    print("证据文件存在：%s" % has_ev)
    print("global.sav 存在：%s" % os.path.isfile(gs))
    if has_ev:
        print("内容：%r" % open(ev, "rb").read()[:200])
    print("-" * 50)
    if has_ev:
        print("结果：PASS —— BOOT 钩子真实触发")
        return 0
    print("结果：FAIL —— 未观察到钩子证据")
    return 1


if __name__ == "__main__":
    sys.exit(main())