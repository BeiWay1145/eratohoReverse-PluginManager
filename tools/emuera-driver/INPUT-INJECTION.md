# Emuera 键盘注入：可行方案与机理

> 本文件记录 **实测验证过** 的 Emuera 输入注入方案。所有结论均有隔离实验支撑，
> 并**明确标注了两处被证伪的早期假设**——它们看起来合理，实际是错的。

---

## 一、可行方案

**`SendInput` + 不加 `-Debug` + 游戏窗口持有前台**，三条**同时必要**。

| 条件 | 说明 |
|---|---|
| **不加 `-Debug`** | 加了必失败（见下"机理"） |
| **`GetForegroundWindow() == 游戏主窗口`** | 这才是真正的开关 |
| **目标是"游戏窗口"而非调试窗口** | 加 `-Debug` 时两者同时存在 |

### 实测隔离矩阵

| 模式 | 前台=游戏窗 | 最小化 | 结果 |
|---|---|---|---|
| `-Debug` + 抢前台 + 最小化 | False | True | **失败** |
| `-Debug` + fg 明确指向游戏窗 | False | True | **失败** |
| 无Debug + 抢前台 + **最小化** | **True** | **True** | **成功** ✅ |
| 无Debug + 抢前台 + 不最小化 | True | False | 成功 |
| 无Debug + 最小化 + 不抢前台 | False | True | **失败** |
| 无Debug + 可见但非前台 | False | False | **失败** |
| 无Debug + 前景让给别的程序 | False | True | **失败** |
| 无Debug + 移到屏幕外(SWP_NOACTIVATE) | False | False | **失败** |

---

## 二、真实机理（含被证伪的假设）

### ✅ 正确解释

`-Debug` 会**额外创建一个顶层窗口** `Emuera - デバッグウインドウ`，
**它抢走并占住前台**。即便把 `SetForegroundWindow` 明确指向游戏窗口也抢不回来，
按键于是投给了调试窗口。

> **危害在"抢前台"，不在"焦点为 0"。**

### ❌ 被证伪的两条早期假设（勿再采信）

| 早期说法 | 实测真相 |
|---|---|
| "主窗口**没有任何子 HWND**，`EnumChildWindows` 返回 0" | **实测 5～8 个子控件**。原因：在 `EnumWindows` 结果里取 `found[0]`，而 `-Debug` 下 `found[0]` 拿到的是**调试窗口**——量错了窗口。 |
| "`GetFocus()` 恒为 0 是失败主因" | `GetFocus()` 在**两种模式下都是 0**，从来不是变量。 |

### 关于 `PostMessage`

`PostMessage(WM_KEYDOWN/WM_CHAR)` **无效**——WinForms 键盘走消息泵 + 焦点状态，
不经过窗口过程。（但**不能**再用"无子 HWND"当理由，见上。）

### 关于 `macro.txt`

**不是独立注入通道**。它是 **F1–F12 绑定**，冒号右边是按下该 F 键后**填入输入框的文本**，
本身不会自动执行，仍需真实按键触发。

---

## 三、最小化与注入不冲突

**最小化窗口只要同时持有前台，`SendInput` 照样生效**
（`IsIconic()==True`、rect 在 `(-32000,-32000)`、`fg=True` → 成功）。

| 方案 | 可行性 |
|---|---|
| 最小化 + 保前台 | ✅ **唯一同时满足"不挡用户"与"能注入"** |
| 移到屏幕外 | ❌ `SWP_NOACTIVATE` 拿不到前台 |
| 不做前台处理 | ❌ 失败 |
| 可见但非前台 | ❌ 失败 |

**代价**：任务栏按钮处于选中态，用户当前应用会被短暂切走。这是必要代价。

**实现注意**：抢前台后要**再压一次最小化并复验前台**——因为 `BringWindowToTop`
有几率把窗口还原。且 `force_foreground` **不能**无条件调用 `SW_RESTORE`，否则会把窗口取消最小化、违反约束。

---

## 四、验收证据

`<游戏目录>/emuera.log`（**UTF-16LE**，BOM `FF FE`）原始序列：

```
ZZDRV_AT_TITLE_INPUT      <- ERB 到达输入点
0                         <- ← 注入的按键，被游戏真实读到（决定性证据）
ZZDRV_TITLE_CHOICE_[0]    <- 标题画面收到 RESULT=0
ZZDRV_EVENTFIRST_FIRED    <- @EVENTFIRST 触发 ⇒ 确实进入了"新游戏"
```

中间那个孤立的 `0` 是决定性证据：它是注入的按键**被游戏真实读取**的痕迹。

---

## 五、脚本用法

```bash
python _input_solution.py                 # 完整自检（插探针 → 启动即最小化 → 注入 0+Enter → 校验 → 还原）
python _input_solution.py --demo          # 人类可读演示（不改 ERB，用 sav/global.sav mtime 判定）
python _input_solution.py --no-minimize   # 关闭最小化（对照用）
```

---

## 六、注意事项

- **探针锚点与游戏版本绑定**：`CALL INPUTINT(0, 1, 2)` 与 `@EVENTFIRST` 是当前汉化版的位置，
  换版本需复核。
- **`SAVETEXT` 在本版本不可用**（静默失败），落盘证据请用 `PRINTL` + `OUTPUTLOG`。
- **探针被强杀会留残留**：`finally` 不执行时 `@SYSTEM_TITLE`/`@EVENTFIRST` 会留下
  `PRINTL`/`OUTPUTLOG`，污染后续分析。用 `emuera_residue` 工具检查/清理。
- **并发禁忌**：同一游戏目录**同一时刻只允许一个进程驱动**。多个进程同时启动游戏会互相抢前台，
  造成难以定位的假阴性。
- 若需要**长时间后台注入且完全不打扰用户**，需接受"任务栏选中态"；
  替代路线是 `AttachThreadInput` 或进程内 hook（**未验证**）。
