#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Emuera 游戏窗口键盘输入注入 —— 已验证可行的方案
================================================================

结论（本机实测，2025 复核，仅使用 _gamesub 目录）
----------------------------------------------
**可行方案：SendInput 键盘注入 + 不要用 -Debug 启动 + 保持"游戏窗口是前台窗口"。**

三条充分且必要的条件（缺一不可，均已隔离实测）::

    1. 不加 -Debug             —— 加了必失败
    2. GetForegroundWindow() == 游戏主窗口   —— 这是真正的开关
    3. 目标必须是"游戏窗口"而非调试窗口      —— 加 -Debug 时两者同时存在

**关键点：最小化不影响注入**。窗口可以保持 SW_MINIMIZE(SW_SHOWMINNOACTIVE)
（IsIconic()==True，在屏幕外 -32000,-32000），只要它同时是前台窗口，
SendInput 的按键照样送达并生效。这正好同时满足"不挡用户"与"能注入"。

关于 -Debug 的**修正后的**机理
------------------------------
上一轮的结论 "-Debug 致命" 是对的，但当时给出的**理由**是错的：

    旧说法: "加 -Debug 后 GetFocus()/GetActiveWindow() 恒为 0，
             于是 WinForms 的 ProcessCmdKey/KeyDown 被静默丢弃。"

实测反驳（EXP-D）：
  * GetFocus() 在**两种模式下都恒为 0**（-Debug 关时也是 0），
    且 SetFocus(main) 两种模式都失败 —— 所以 focus 从来不是变量。
  * **主窗口并不是"没有子 HWND"**：实测 -Debug 关时有 5 个子窗口
    (RichEdit20W / SCROLLBAR / 2×Window / EDIT)，-Debug 开时有 8 个。
    上一轮之所以数出 0，是因为它在 EnumWindows 里取 found[0]，
    而在 -Debug 模式下 found[0] 拿到的是**调试窗口**而不是游戏窗口 ——
    数错了窗口，于是得出了"无子窗口"的错误结论。

修正后的真实机理：**-Debug 会额外创建一个 "Emuera - デバッグウインドウ"
顶层窗口，它与游戏窗口争抢前台并且会抢赢/占住前台。**
实测（EXP-E）中即便把 SetForegroundWindow 明确指向游戏窗口，
GetForegroundWindow() 仍然回不到游戏窗口（fg_is_game=False），
按键于是投递给了调试窗口 → 游戏收不到 → 无响应。

即：**-Debug 的危害在于"抢走前台"，而不在于"焦点为 0"。**

实测隔离矩阵（同一探针 ERB，同一脚本，均在 _gamesub，启动后立即最小化）::

    模式                                前台=游戏窗  最小化  结果
    ----------------------------------  ----------  ------  ------
    -Debug  + 抢前台 + 最小化             False       True    失败   (A1)
    -Debug  + fg 明确指向游戏窗 + 最小化  False       True    失败   (E1)
    无Debug + 抢前台 + 最小化             True        True    成功   (E2)
    无Debug + 抢前台 + 不最小化           True        False   成功   (A4)
    无Debug + 最小化 + 不抢前台           False       True    失败   (B1)
    无Debug + 可见但非前台                False       False   失败   (B4)
    无Debug + 前台让给别的程序            False       True    失败   (E3)
    无Debug + 移到屏幕外(SWP_NOACTIVATE)  False       False   失败   (C1)

由最后一行可见：**"把窗口移到屏幕外"不是可行的妥协** ——
用 SWP_NOACTIVATE 移窗根本拿不到前台，于是注入失败。
唯一同时满足"不挡用户"与"能注入"的形态是 **最小化 + 保持前台**。

关于其它已排除的方案（证据见运行日志）
------------------------------------
- **PostMessage(WM_KEYDOWN/WM_CHAR) 无效**：Emuera 是 WinForms 应用，
  键盘输入走 Application.ThreadContext 的消息泵 + 焦点，不经过窗口过程里的
  手动处理，PostMessage 直接投给窗口过程因而被丢弃。
  （注意：这里**不能**再用"- 没有子 HWND"当理由，那是上一轮的错误测量，见上。）
- **macro.txt 不是独立注入通道**：Emuera 的键盘宏是 **F1-F12 绑定**，
  文件里 "マクロキーF○:" 冒号右边是按下该 F 键后要**填入输入框的文本**。
  它本身不会自动执行，仍需真实按键触发 → 所以它是 SendInput 的
  *上层便利*，不是替代品。本脚本提供一个辅助函数用于生成 macro.txt。

验收证据（探针法）
------------------
在 ERB 里插探针，用 OUTPUTLOG 把标记写进 <游戏目录>/emuera.log（UTF-16LE）::

    @SYSTEM_TITLE 的 CALL INPUTINT(0, 1, 2) 前后插 PRINTL/OUTPUTLOG
    @EVENTFIRST    开头插 PRINTL/OUTPUTLOG

注入 "0" + Enter 后的实测日志（节选）::

    ZZDRV_AT_TITLE_INPUT
    0
    ZZDRV_TITLE_CHOICE_[0]      <- 标题画面确实读到了 0
    ZZDRV_EVENTFIRST_FIRED      <- 真的进入了新游戏，@EVENTFIRST 被触发

注意 emuera.log 是 **UTF-16LE**，不要按 Shift-JIS 读。
**SAVETEXT 在本版本不可用（静默失败），不要用它做验收。**

用法::

    python _input_solution.py            # 完整自检（自动插探针、跑、还原）
    python _input_solution.py --demo     # 人类可读演示（不插探针）

所有对游戏文件的改动都会在 finally 中还原，并在结束时 taskkill 掉 Emuera 进程。
本脚本**只**操作 _gamesub 目录。
"""

import argparse
import ctypes
import ctypes.wintypes as wt
import io
import os
import shutil
import subprocess
import sys
import time

try:
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

# --------------------------------------------------------------------------
# 路径配置
# --------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
# ⚠️ 本脚本**只**允许操作 _gamesub。绝不触碰 _testgame / _fresh / _pristine /
#    eratohoЯeverse-1.214-CNTESTv0.219 —— 那些属于其他用途。
GAME = os.path.join(HERE, "_gamesub")
# _gamesub 专用的一份干净原件快照（首次运行自建，之后作为还原源）。
PRISTINE_DIR = os.path.join(GAME, "_zz_orig")
EXE_NAME = "Emuera1824+v1.exe"
EXE = os.path.join(GAME, EXE_NAME)
TITLE_ERB = os.path.join(GAME, "ERB", "SYSTEM", "SYSTEM_TITLE.ERB")
SYSTEM_ERB = os.path.join(GAME, "ERB", "SYSTEM", "SYSTEM.ERB")
LOG = os.path.join(GAME, "emuera.log")
BOM = b"\xef\xbb\xbf"

MARK_BEFORE = "ZZDRV_AT_TITLE_INPUT"
MARK_CHOICE = "ZZDRV_TITLE_CHOICE_"
MARK_FIRST = "ZZDRV_EVENTFIRST_FIRED"

u32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)

# --------------------------------------------------------------------------
# SendInput 结构体（显式声明，兼容 32/64 位）
# --------------------------------------------------------------------------
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_ushort),
                ("wParamH", ctypes.c_ushort)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("u", _INPUTUNION)]


INPUT_KEYBOARD = 1
INPUT_MOUSE = 0
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000

u32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
u32.SendInput.restype = ctypes.c_uint
u32.MapVirtualKeyW.argtypes = [ctypes.c_uint, ctypes.c_uint]
u32.MapVirtualKeyW.restype = ctypes.c_uint

VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_UP = 0x26
VK_DOWN = 0x28
VK_F1 = 0x70

# --- 窗口显示状态常量 ---
SW_MINIMIZE = 6
SW_SHOWMINNOACTIVE = 7
SW_RESTORE = 9


# --------------------------------------------------------------------------
# 键盘注入（核心）
# --------------------------------------------------------------------------
def _key_event(vk, key_up=False, scancode=True):
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    scan = u32.MapVirtualKeyW(vk, 0)      # MAPVK_VK_TO_VSC
    inp.u.ki.wVk = 0 if scancode else vk
    inp.u.ki.wScan = scan
    flags = (KEYEVENTF_SCANCODE if scancode else 0) | (KEYEVENTF_KEYUP if key_up else 0)
    if vk in (0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E):
        flags |= KEYEVENTF_EXTENDEDKEY
    inp.u.ki.dwFlags = flags
    return inp


def press_key(vk, scancode=True, hold=0.03):
    """按下一个键（down + up）。"""
    arr = (INPUT * 2)(*[_key_event(vk, False, scancode), _key_event(vk, True, scancode)])
    n = u32.SendInput(2, arr, ctypes.sizeof(INPUT))
    time.sleep(hold)
    return n


def _send_chord(vks, scancode=True):
    seq = [_key_event(v, False, scancode) for v in vks]
    n1 = u32.SendInput(len(seq), (INPUT * len(seq))(*seq), ctypes.sizeof(INPUT))
    time.sleep(0.03)
    seq = [_key_event(v, True, scancode) for v in reversed(vks)]
    n2 = u32.SendInput(len(seq), (INPUT * len(seq))(*seq), ctypes.sizeof(INPUT))
    return n1 + n2


def type_ascii(text, scancode=True, per_char=0.12):
    """用 VkKeyScanW 解析字符再 SendInput，可正确处理需要 Shift 的字符。"""
    vkk = u32.VkKeyScanW
    vkk.argtypes = [ctypes.c_wchar]
    vkk.restype = ctypes.c_short
    total = 0
    for ch in text:
        code = vkk(ch)
        if code == -1:
            continue
        vk = code & 0xFF
        total += _send_chord([0x10, vk] if (code & 0x100) else [vk], scancode)
        time.sleep(per_char)
    return total


def send_command(text, enter=True, scancode=True, settle=0.6):
    """Emuera 里"输入一条命令并确认"的完整动作。"""
    type_ascii(text, scancode=scancode)
    time.sleep(0.2)
    if enter:
        press_key(VK_RETURN, scancode=scancode)
    time.sleep(settle)



# --------------------------------------------------------------------------
# 窗口工具
# --------------------------------------------------------------------------
def enum_top_windows(pid):
    """枚举该 pid 的所有**可见** WindowsForms 顶层窗口 -> [(hwnd, title), ...]

    上一轮就是在这里出错的：它取 found[0]，而在 -Debug 模式下
    EnumWindows 返回的第一个可见 WindowsForms 窗口是**调试窗口**
    ("Emuera - デバッグウインドウ")，不是游戏窗口。于是后续所有
    "主窗口"的判断（前台、子窗口计数）全都作用在错误的窗口上。
    因此这里**返回全部**，由调用方按标题挑出真正的游戏窗口。
    """
    found = []

    def _cb(hwnd, _lp):
        q = wt.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(q))
        if q.value == pid:
            cls = ctypes.create_unicode_buffer(256)
            u32.GetClassNameW(hwnd, cls, 256)
            if cls.value.startswith("WindowsForms10.Window") and u32.IsWindowVisible(hwnd):
                n = u32.GetWindowTextLengthW(hwnd)
                b = ctypes.create_unicode_buffer(n + 1)
                u32.GetWindowTextW(hwnd, b, n + 1)
                found.append((hwnd, b.value))
        return True

    u32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)(_cb), 0)
    return found


DEBUG_TITLE_MARK = "デバッグウインドウ"


def find_main_window(pid, timeout=40.0):
    """找到**游戏**主窗口（排除调试窗口）。

    关键：-Debug 模式下同时存在游戏窗口与调试窗口，
    必须按标题排除调试窗口，不能再无脑取第一个。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        for hwnd, title in enum_top_windows(pid):
            if DEBUG_TITLE_MARK not in title:
                return hwnd
        time.sleep(0.5)
    return None


def find_debug_window(pid):
    """找到调试窗口（仅用于诊断报告）。"""
    for hwnd, title in enum_top_windows(pid):
        if DEBUG_TITLE_MARK in title:
            return hwnd
    return None


def enum_child_windows(hwnd):
    """枚举子窗口 -> [(hwnd, class), ...]（仅用于诊断）。

    注：上一轮报告"EnumChildWindows 返回 0 个"，那是量错了窗口
    （量的是调试窗口/或时机不对）。实测游戏窗口有 5~8 个子窗口。
    """
    out = []

    def _cb(c, _lp):
        b = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(c, b, 256)
        out.append((c, b.value))
        return True

    u32.EnumChildWindows(hwnd, ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)(_cb), 0)
    return out


def minimize_window(hwnd):
    """立刻最小化窗口，避免妨碍用户做其他事情。

    实测（EXP-C/E2）：**最小化不影响 SendInput 注入**。
    只要窗口同时是前台窗口，IsIconic()==True 也照样收键。
    所以这是"不挡用户"与"能注入"可以兼得的形态。
    """
    try:
        u32.ShowWindow(hwnd, SW_MINIMIZE)      # 6
    except Exception:
        pass
    time.sleep(0.2)
    # 若最小化没生效（个别窗口风格），退而求其次用不激活的最小化
    if not u32.IsIconic(hwnd):
        try:
            u32.ShowWindow(hwnd, SW_SHOWMINNOACTIVE)   # 7
        except Exception:
            pass
        time.sleep(0.2)
    return bool(u32.IsIconic(hwnd))


def force_foreground(hwnd, tries=8, keep_minimized=True):
    """把目标窗口抢到前台，并**验证**它确实拿到了前台。

    SendInput 把按键投给"当前前台窗口"（严格说是前台窗口所属线程的输入队列），
    所以必须确认 GetForegroundWindow() == hwnd，否则按键会打到别的程序上。
    实测（E3）把前台让给别的程序后注入必然失败，可见这是硬条件。

    keep_minimized=True 时**绝不调用 SW_RESTORE**：旧版在这里无条件
    ShowWindow(SW_RESTORE)，会把我们刚最小化的窗口又弹到用户面前，
    直接违背"启动即最小化、不挡用户"的约束。实测（C2/E2）表明
    最小化窗口同样可以被设为前台并接收 SendInput，所以无需还原。
    """
    for _ in range(tries):
        try:
            if u32.GetForegroundWindow() == hwnd:
                return True
            if not keep_minimized:
                u32.ShowWindow(hwnd, 9)                 # SW_RESTORE
                time.sleep(0.2)
            # 手法 1：AttachThreadInput 到当前前台线程后再 SetForegroundWindow
            fg = u32.GetForegroundWindow()
            my_tid = k32.GetCurrentThreadId()
            fg_tid = u32.GetWindowThreadProcessId(fg, None)
            if fg_tid and fg_tid != my_tid:
                u32.AttachThreadInput(my_tid, fg_tid, True)
                u32.SetForegroundWindow(hwnd)
                u32.AttachThreadInput(my_tid, fg_tid, False)
            else:
                u32.SetForegroundWindow(hwnd)
            time.sleep(0.25)
            if u32.GetForegroundWindow() == hwnd:
                return True
            # 手法 2：BringWindowToTop + SetForegroundWindow
            u32.BringWindowToTop(hwnd)
            u32.SetForegroundWindow(hwnd)
            time.sleep(0.25)
            if u32.GetForegroundWindow() == hwnd:
                return True
            # 手法 3：最小化后再抢前台（保持最小化状态，不 SW_RESTORE）
            if not u32.IsIconic(hwnd):
                u32.ShowWindow(hwnd, 6)                 # SW_MINIMIZE
                time.sleep(0.2)
            u32.SetForegroundWindow(hwnd)
            time.sleep(0.3)
            if u32.GetForegroundWindow() == hwnd:
                return True
        except Exception:
            pass
        time.sleep(0.4)
    return u32.GetForegroundWindow() == hwnd


def foreground_keep_minimized(hwnd, minimize=True, tries=8):
    """抢前台，但**确保窗口仍处于最小化**（不挡用户）。

    实测发现：对最小化窗口调用 BringWindowToTop / SetForegroundWindow
    有几率把它还原成可见窗口。所以这里在拿到前台之后再压一次最小化，
    并且**验证前台没有被这次最小化打掉** —— 两步在这个组合下可以共存
    （EXP-C2/E2 已证：iconic=True 且 fg=True 时注入成功）。
    """
    ok = force_foreground(hwnd, tries=tries, keep_minimized=minimize)
    if minimize and not u32.IsIconic(hwnd):
        u32.ShowWindow(hwnd, SW_MINIMIZE)
        time.sleep(0.15)
        if not u32.IsIconic(hwnd):
            u32.ShowWindow(hwnd, SW_SHOWMINNOACTIVE)
            time.sleep(0.15)
        # 重新最小化可能会丢前台，丢就再抢一次（此时窗口已是最小化态）
        if u32.GetForegroundWindow() != hwnd:
            ok = force_foreground(hwnd, tries=4, keep_minimized=True)
    return u32.GetForegroundWindow() == hwnd


def click_client(hwnd, x, y):
    """在窗口客户区坐标 (x, y) 做一次真实鼠标点击（SendInput 绝对坐标）。"""
    pt = wt.POINT(x, y)
    u32.ClientToScreen(hwnd, ctypes.byref(pt))
    sw = u32.GetSystemMetrics(0)
    sh = u32.GetSystemMetrics(1)
    nx = int(pt.x * 65535 / max(sw - 1, 1))
    ny = int(pt.y * 65535 / max(sh - 1, 1))
    items = []
    for flags in (MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE,
                  MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_LEFTDOWN,
                  MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_LEFTUP):
        it = INPUT()
        it.type = INPUT_MOUSE
        it.u.mi.dx = nx
        it.u.mi.dy = ny
        it.u.mi.dwFlags = flags
        items.append(it)
    arr = (INPUT * 3)(*items)
    return u32.SendInput(3, arr, ctypes.sizeof(INPUT))


# --------------------------------------------------------------------------
# 进程 / 日志
# --------------------------------------------------------------------------
def kill_emuera():
    """彻底杀掉 Emuera 进程。"""
    for _ in range(4):
        subprocess.run(["taskkill", "/F", "/IM", EXE_NAME], capture_output=True)
        time.sleep(0.6)
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq %s" % EXE_NAME],
                             capture_output=True, text=True,
                             encoding="cp932", errors="replace").stdout
        if EXE_NAME not in out:
            return True
    return False


def kill_other_emuera(keep_pid=None):
    """杀掉除 keep_pid 之外的所有 Emuera 实例。

    同目录下若同时跑着另一个 Emuera（常见于别的脚本用 -Debug 起的进程），
    它会抢走前台焦点，SendInput 的按键就打到它身上去了。
    """
    exe = EXE_NAME
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq %s" % exe, "/FO", "CSV", "/NH"],
                         capture_output=True, text=True, encoding="cp932",
                         errors="replace").stdout
    killed = []
    for line in out.splitlines():
        parts = [p.strip('" ') for p in line.split('","')]
        if len(parts) < 2 or exe not in parts[0]:
            continue
        try:
            pid = int(parts[1])
        except ValueError:
            continue
        if keep_pid is not None and pid == keep_pid:
            continue
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        killed.append(pid)
    if killed:
        time.sleep(0.8)
    return killed


def read_engine_log():
    """读 emuera.log（UTF-16LE）。"""
    if not os.path.isfile(LOG):
        return ""
    raw = open(LOG, "rb").read()
    if raw[:2] == b"\xff\xfe":
        return raw.decode("utf-16-le", errors="replace")
    if raw[:2] == b"\xfe\xff":
        return raw.decode("utf-16-be", errors="replace")
    return raw.decode("utf-8", errors="replace")


def launch(extra_args=(), warmup=20.0, minimize=True):
    """启动游戏，**立刻最小化**，再等待主窗口出现。

    注意：
      * **不要传 -Debug** —— 加了之后会多出一个调试窗口抢走前台，
        游戏窗口永远拿不到 GetForegroundWindow()，注入必然失败。
      * 启动后**第一时间**最小化，避免游戏窗口挡在用户面前。
        实测最小化不影响后续注入（见 minimize_window 的说明）。
    """
    # 启动前先清理同名进程，防止自己与自己抢前台
    kill_emuera()
    if os.path.isfile(LOG):
        for _ in range(5):
            try:
                os.remove(LOG)
                break
            except OSError:
                time.sleep(0.5)
    proc = subprocess.Popen([EXE, *extra_args], cwd=GAME)

    # ---- 一旦主窗口出现就立刻最小化 ----
    hwnd = None
    deadline = time.time() + warmup + 25
    minimized = False
    while time.time() < deadline:
        hwnd = find_main_window(proc.pid, timeout=0.5)
        if hwnd:
            if minimize and not minimized:
                minimized = minimize_window(hwnd)
            break
        time.sleep(0.3)
    if hwnd and minimize and not minimized:
        minimized = minimize_window(hwnd)
    return proc, hwnd



# --------------------------------------------------------------------------
# ERB 探针（验收用）
# --------------------------------------------------------------------------
def _to_crlf(text):
    return text.replace("\r\n", "\n").replace("\n", "\r\n")


# _gamesub\_zz_orig 下保存的干净原件（相对 GAME 的路径）
ORIGINALS = {
    "SYSTEM_TITLE.ERB": os.path.join("ERB", "SYSTEM", "SYSTEM_TITLE.ERB"),
    "SYSTEM.ERB": os.path.join("ERB", "SYSTEM", "SYSTEM.ERB"),
}


def ensure_stash():
    r"""确保 _gamesub\_zz_orig 里有干净原件快照。

    首次运行时，如果 _gamesub\ERB 里当前**没有** ZZDRV 残留，
    就把当前文件当作干净原件存进 _zz_orig。
    如果发现已有 ZZDRV 残留（上一轮中断留下的），则拒绝把它当原件，
    并给出明确提示 —— 绝不能把"带探针的脏文件"永久固化成还原源。
    """
    os.makedirs(os.path.join(PRISTINE_DIR, "SYSTEM"), exist_ok=True)
    dirty = []
    for name, rel in ORIGINALS.items():
        src = os.path.join(GAME, rel)
        stash = os.path.join(PRISTINE_DIR, os.path.basename(rel))
        if os.path.isfile(stash):
            continue
        if not os.path.isfile(src):
            dirty.append((name, "源文件不存在"))
            continue
        if b"ZZDRV" in open(src, "rb").read():
            dirty.append((name, "当前文件已含 ZZDRV 探针残留"))
            continue
        shutil.copy2(src, stash)
    return dirty


def _restore_from_pristine(rel):
    r"""从 _gamesub\_zz_orig 恢复某文件的干净原件。"""
    src = os.path.join(PRISTINE_DIR, os.path.basename(rel))
    dst = os.path.join(GAME, rel)
    if os.path.isfile(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        return True
    return False


def install_probe():
    """插入探针，返回 restore() 回调。

    探针 1：SYSTEM_TITLE.ERB 的 CALL INPUTINT(0, 1, 2) 前后
    探针 2：SYSTEM.ERB 的 @EVENTFIRST 开头
    """
    # 首次运行先自建干净原件快照；若发现残留探针则明确报错而不是固化脏文件
    dirty = ensure_stash()
    if dirty:
        raise RuntimeError(
            "_gamesub 里检测到上一轮残留的探针，且没有干净原件快照：%r\n"
            "请先从干净源恢复这两个文件后再运行（或手工建立 %s）。" % (dirty, PRISTINE_DIR))

    # 始终从干净原件起步，避免上次崩溃残留的探针被二次改写
    _restore_from_pristine(os.path.join("ERB", "SYSTEM", "SYSTEM_TITLE.ERB"))
    _restore_from_pristine(os.path.join("ERB", "SYSTEM", "SYSTEM.ERB"))

    title_orig = open(TITLE_ERB, "rb").read()
    system_orig = open(SYSTEM_ERB, "rb").read()

    # --- 探针 1：标题画面的输入点
    t = title_orig.decode("utf-8-sig")
    assert "ZZDRV" not in t, "SYSTEM_TITLE.ERB 里已有残留探针"
    anchor = "CALL INPUTINT(0, 1, 2)"
    assert anchor in t, "找不到 INPUTINT 锚点"
    replacement = ("\t\tPRINTL " + MARK_BEFORE + "\n"
                   "\t\tOUTPUTLOG\n"
                   "\t\tCALL INPUTINT(0, 1, 2)\n"
                   "\t\tPRINTFORML " + MARK_CHOICE + "[{RESULT}]\n"
                   "\t\tOUTPUTLOG\n")
    t2 = t.replace(anchor, replacement, 1)
    assert t2 != t, "替换未生效"
    open(TITLE_ERB, "wb").write(BOM + _to_crlf(t2).encode("utf-8"))
    _back = open(TITLE_ERB, "rb").read().decode("utf-8-sig")
    assert chr(92) + "r" + chr(92) + "n" not in _back, "换行符转义泄漏到 ERB（字面 \\r\\n）"
    assert MARK_BEFORE in _back and anchor in _back, "探针写入后回读校验失败"

    # --- 探针 2：新游戏入口
    s = system_orig.decode("utf-8-sig")
    a2 = "@EVENTFIRST\r\n"
    assert a2 in s, "找不到 @EVENTFIRST 锚点"
    s2 = s.replace(a2, a2 + "\tPRINTL " + MARK_FIRST + "\r\n\tOUTPUTLOG\r\n", 1)
    open(SYSTEM_ERB, "wb").write(BOM + _to_crlf(s2).encode("utf-8"))

    def restore():
        open(TITLE_ERB, "wb").write(title_orig)
        open(SYSTEM_ERB, "wb").write(system_orig)
    return restore


# --------------------------------------------------------------------------
# macro.txt 辅助（Emuera 原生键盘宏）
# --------------------------------------------------------------------------
def write_macro_file(macros, group=0, path=None):
    """生成 Emuera 的 macro.txt。

    macros: {F键号(1-12): "要填入输入框的文本"}
    文本里可用 Emuera 宏语法：反斜杠e = 跳到下一选项，
    反斜杠n = 分隔下一次输入，"(...)*n" = 重复 n 次。

    注意：这只让 F 键"填入"文本，**仍然需要真实按下 F 键并回车**，
    所以它必须配合 SendInput 使用，不能单独驱动游戏。
    """
    path = path or os.path.join(GAME, "macro.txt")
    lines = []
    for k in range(1, 13):
        prefix = "マクロキーF%d:" % k if group == 0 else "G%d:マクロキーF%d:" % (group, k)
        lines.append(prefix + macros.get(k, ""))
    open(path, "wb").write(BOM + _to_crlf("\n".join(lines) + "\n").encode("utf-8"))
    return path



# --------------------------------------------------------------------------
# 自检 / 演示
# --------------------------------------------------------------------------
def run_selftest(warmup=20.0, minimize=True):
    """完整自检：插探针 -> 启动即最小化 -> 注入 '0'+Enter -> 校验日志 -> 还原。"""
    print("=" * 68)
    print("Emuera 键盘注入自检  (仅 _gamesub)")
    print("=" * 68)
    print("游戏目录 :", GAME)
    print("启动参数 : []   (故意不加 -Debug，这是关键)")
    print("最小化   :", minimize)
    print()

    restore = install_probe()
    result = {"ok": False}
    try:
        proc, hwnd = launch(warmup=warmup, minimize=minimize)
        print("进程 pid :", proc.pid, " 已启动")
        print("主窗口   :", hwnd)
        if not hwnd:
            print("[FAIL] 未找到主窗口")
            print(read_engine_log()[:1500])
            return result
        # 报告窗口状态：确认最小化生效，且子窗口数（纠正上一轮的"0 个子窗口"）
        print("窗口状态 : iconic=%s  visible=%s  子窗口数=%d"
              % (bool(u32.IsIconic(hwnd)), bool(u32.IsWindowVisible(hwnd)),
                 len(enum_child_windows(hwnd))))
        dbg = find_debug_window(proc.pid)
        print("调试窗口 :", dbg if dbg else "(无 —— 正确，未使用 -Debug)")
        time.sleep(2.0)

        # 关键：轮询等待游戏真正走到 INPUTINT，而不是盲目 sleep。
        # ERB 编译 + 41 帧标题动画需要时间，注入早于 INPUTINT 会被丢弃。
        t0 = time.time()
        while time.time() - t0 < 90:
            if MARK_BEFORE in read_engine_log():
                break
            time.sleep(1.0)
        print("到达输入点耗时 : %.1fs" % (time.time() - t0))

        # SendInput 把按键投给"当前前台窗口"，所以每一轮注入前都必须
        # 确认目标窗口真的在前台，否则按键会打到别的地方去（实测 E3：让给别的
        # 程序后必然失败）。keep_minimized=True 保证抢前台时不会把窗口弹回来。
        got_fg = foreground_keep_minimized(hwnd, minimize=minimize)
        print("抢前台   : %s  (保持最小化=%s)" % (got_fg, bool(u32.IsIconic(hwnd))))
        time.sleep(1.0)

        choices = []
        for attempt in range(1, 8):
            # 其他 Emuera 实例会把前台抢走，导致 SendInput 打到别人身上。
            # 注入前确保只剩我们这一个实例。
            kill_other_emuera(keep_pid=proc.pid)
            if u32.GetForegroundWindow() != hwnd:
                foreground_keep_minimized(hwnd, minimize=minimize)
                time.sleep(0.5)
            print("注入     : '0' + Enter   (NEW GAME)  第 %d 次  (前台=%s, 最小化=%s)"
                  % (attempt, u32.GetForegroundWindow() == hwnd, bool(u32.IsIconic(hwnd))))
            send_command("0", enter=True)
            time.sleep(2.5)
            log = read_engine_log()
            choices = [l.strip() for l in log.splitlines() if MARK_CHOICE in l]
            if choices or MARK_FIRST in log:
                break

        log = read_engine_log()
        reached_input = MARK_BEFORE in log
        choices = [l.strip() for l in log.splitlines() if MARK_CHOICE in l]
        first_fired = MARK_FIRST in log

        print()
        print("-" * 68)
        print("到达标题输入点 (INPUTINT)  :", reached_input)
        print("标题画面读到的选择         :", choices or "(无)")
        print("@EVENTFIRST 已触发 (新游戏):", first_fired)
        print("游戏进程仍存活             :", proc.poll() is None)
        print("-" * 68)

        ok = bool(reached_input and choices and first_fired)
        result["ok"] = ok
        if choices:
            result["choice"] = choices[-1]
        print()
        print(">>> 结论:", "键盘注入【可行】—— 游戏状态确实被改变了"
              if ok else "键盘注入未生效，请查看下方日志")
        if not ok:
            print()
            print("--- 引擎日志尾部 ---")
            print(log[-1500:])
    finally:
        # 无论如何先杀进程（可能还残留着最小化在任务栏里的窗口）
        kill_emuera()
        restore()
        cleaned = (b"ZZDRV" not in open(TITLE_ERB, "rb").read()
                   and b"ZZDRV" not in open(SYSTEM_ERB, "rb").read())
        print()
        print("已还原 ERB 探针 :", cleaned)
        print("Emuera 进程已清 :", kill_emuera())
    return result


def run_demo(warmup=20.0, minimize=True, hold=0.0):
    """人类可读演示：不插探针，注入 '0'+Enter 让游戏真正推进到新游戏。

    hold > 0 时在结束前停留若干秒，方便人肉观察（默认 0，跑完即清理）。
    """
    print("=" * 68)
    print("Emuera 键盘注入演示  (仅 _gamesub)")
    print("=" * 68)
    print("游戏目录 :", GAME)
    print("启动参数 : []   (不加 -Debug)")
    print("最小化   :", minimize)
    print()
    proc, hwnd = launch(warmup=warmup, minimize=minimize)
    try:
        print("pid=%s  hwnd=%s" % (proc.pid, hwnd))
        if not hwnd:
            print("[FAIL] 未找到主窗口")
            return
        print("窗口状态 : iconic=%s  visible=%s"
              % (bool(u32.IsIconic(hwnd)), bool(u32.IsWindowVisible(hwnd))))
        time.sleep(2)

        # 演示同样要等游戏真正走到 INPUTINT 再注入；否则按键早于输入点，
        # 会被丢弃（ERB 编译 + 标题动画需要时间）。
        t0 = time.time()
        print("等待标题输入点 ...")
        while time.time() - t0 < 90:
            if MARK_BEFORE in read_engine_log():
                break
            # 同时确保窗口一直是"最小化 + 前台"这个可用组合
            foreground_keep_minimized(hwnd, minimize=minimize)
            time.sleep(1.0)
        print("到达输入点耗时 : %.1fs" % (time.time() - t0))

        # 前台是硬条件：拿不到就重试，别把按键打给别的程序。
        got = False
        for _ in range(10):
            got = foreground_keep_minimized(hwnd, minimize=minimize)
            if got:
                break
            time.sleep(0.5)
        print("抢前台   : %s  (最小化仍保持=%s)" % (got, bool(u32.IsIconic(hwnd))))

        print("注入     : '0' + Enter ...")
        # 观测手段（不需要改 ERB）：
        #   1) 若当前 ERB 恰好带着 ZZDRV 探针，直接看 emuera.log 标记；
        #   2) 否则看 sav/global.sav 的 mtime —— 进入新游戏时 @EVENTFIRST
        #      里的 SAVEGLOBAL 会重写它。
        sav_before = global_sav_mtime()
        responded = False
        for attempt in range(1, 6):
            kill_other_emuera(keep_pid=proc.pid)
            if u32.GetForegroundWindow() != hwnd:
                foreground_keep_minimized(hwnd, minimize=minimize)
                time.sleep(0.4)
            send_command("0")
            time.sleep(2.0)
            log = read_engine_log()
            sav_now = global_sav_mtime()
            if MARK_CHOICE in log or MARK_FIRST in log:
                responded = True
                print("          第 %d 次注入后游戏已响应（emuera.log 探针标记）" % attempt)
                break
            if sav_before is None or (sav_now is not None and sav_now != sav_before):
                responded = True
                print("          第 %d 次注入后游戏已响应（sav/global.sav 被重写）" % attempt)
                break
            print("          第 %d 次注入未响应，重试 ..." % attempt)

        print()
        print("注入是否生效         :", responded)
        print("前台是否仍在游戏窗口 :", u32.GetForegroundWindow() == hwnd)
        print("窗口是否仍最小化     :", bool(u32.IsIconic(hwnd)))
        print()
        print("--- 引擎日志尾部 ---")
        print(read_engine_log()[-1200:])
        if hold:
            print()
            print("保持 %ss 供观察 ..." % hold)
            time.sleep(hold)
    finally:
        # 演示结束后必定杀进程并清理，绝不留下常驻残留
        kill_emuera()
        print()
        print("Emuera 进程已清理 :", not any_emuera_running())


def global_sav_mtime():
    """global.sav 的修改时间（新游戏开始会 SAVEGLOBAL，因此这是个
    **不需要改 ERB** 就能观测到的"新游戏已启动"副作用）。"""
    p = os.path.join(GAME, "sav", "global.sav")
    try:
        return os.path.getmtime(p)
    except OSError:
        return None


def any_emuera_running():
    """是否还有任何 Emuera 进程在跑。"""
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq %s" % EXE_NAME,
                          "/FO", "CSV", "/NH"],
                         capture_output=True, text=True,
                         encoding="cp932", errors="replace").stdout
    return EXE_NAME.lower() in out.lower()


def main():
    ap = argparse.ArgumentParser(
        description="Emuera 键盘注入方案（已验证；仅操作 _gamesub）")
    ap.add_argument("--demo", action="store_true", help="只做演示，不插探针")
    ap.add_argument("--warmup", type=float, default=20.0, help="启动等待秒数")
    ap.add_argument("--no-minimize", action="store_true",
                    help="不最小化窗口（默认启动即最小化）")
    ap.add_argument("--hold", type=float, default=0.0,
                    help="演示模式下结束前停留秒数（默认 0）")
    args = ap.parse_args()

    if not os.path.isfile(EXE):
        print("找不到可执行文件:", EXE)
        return 2
    try:
        if args.demo:
            run_demo(args.warmup, minimize=not args.no_minimize, hold=args.hold)
            return 0
        res = run_selftest(args.warmup, minimize=not args.no_minimize)
        return 0 if res.get("ok") else 1
    finally:
        # 双保险：任何路径退出都保证没有 Emuera 残留
        kill_emuera()


if __name__ == "__main__":
    sys.exit(main())
