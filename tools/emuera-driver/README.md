# emuera-driver：让 agent 能"运行并读取" Emuera

## 为什么需要它

Emuera 是 **GUI 程序**，没有 stdout、没有可读的文本控件（画面用 GDI+ 直接绘制）。
截图 + OCR 又慢又不可靠。所以需要一个真正的运行时 I/O 通道。

本工具提供该通道，方式如下（全部实机验证，非推测）。

---

## 一、核心机制

### 1. 输出通道：`OUTPUTLOG`

Emuera 的 `OUTPUTLOG` 命令会把**引擎日志**写到 `<游戏目录>/emuera.log`：

- 编码 **UTF-16LE**
- 内容包含：编译警告/错误（`警告Lv1` / `警告Lv2` + `文件:行目` + 原文行）、
  运行时异常、**完整函数调用栈**
- 实测：966 个 ERB 一次导出 1020 行 / 83 KB

这比 OCR 强得多——它给出的是**引擎自己的结构化诊断**，不是像素猜测。

### 2. 启动锚点：`@SYSTEM_TITLE`

Emuera 的事件函数里，只有 `@SYSTEM_TITLE` 在**每次启动时必然执行**。
（`@EVENTFIRST` / `BOOT` 只在选「NEW GAME」后触发。）

工具的做法：临时在 `@SYSTEM_TITLE` 后插入一行 `CALL PLUGIN_HOOK("BOOT")`，
跑完游戏**自动还原**，不改动用户文件。

### 3. 探针验证钩子链路

注入一个临时插件，在每个事件里 `PRINTL ZZDRV_FIRED_<事件>` + `OUTPUTLOG`，
跑完后在日志里检索标记。**标记出现 = `PLUGIN_HOOK` → `TRYCALLFORM` 分发真的到达了插件。**

---

## 二、踩过的坑（重要）

| 坑 | 现象 | 结论 |
|---|---|---|
| `SAVETEXT` 不可用 | 插件静默无输出，**无任何报错** | 本版本报 `この機能は現バージョンでは使えません`。**别用它落盘证据**，用 `PRINTL` + `OUTPUTLOG` |
| 按键注入无效 | `SendInput`/`PostMessage` 都发不进游戏 | 驱动**不做按键注入**，只做「启动 + 抓日志」 |
| 调试窗抢焦点 | `SetForegroundWindow` 失败 | 若需交互，先把调试窗 `SW_MINIMIZE` |
| 编码 | `emuera.log` 是 UTF-16LE；`emuera.config` 是 UTF-8 BOM | 别按 Shift-JIS 处理 |

---

## 三、工具

| 工具 | 作用 |
|------|------|
| `emuera_run` | 启动游戏跑 N 秒，返回引擎诊断 + 探针事件 |
| `emuera_log` | 读取解析 `emuera.log`（可按文件名过滤、按等级过滤） |
| `emuera_probe` | 注入探针验证钩子链路，自动还原 |
| `emuera_doctor` | 环境自检（可执行文件/配置/插件/日志） |

---

## 四、接入 MCP

```json
{
  "serverName": "emuera-driver",
  "transport": "stdio",
  "command": "python",
  "args": ["<本目录绝对路径>/emuera_driver_mcp.py"],
  "enabled": true
}
```

---

## 五、与 era-mcp 的分工

| | era-mcp | emuera-driver |
|---|---|---|
| 读什么 | ERB / CSV 源码 | 运行时引擎日志 |
| 答什么 | 「代码写得对不对」 | 「运行时到底发生了什么」 |
| 时机 | 改完代码立刻查 | 需要确认启动/钩子行为时 |

两者互补，建议都装。
