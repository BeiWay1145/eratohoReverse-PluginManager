# eratohoReverse 插件系统开发指南

> 适用仓库：`https://github.com/BeiWay1145/eratohoReverse`
> 适用分支：`master`（插件代码已并入）与 `plugin-dev`
> 本文档面向编写插件的开发者（人或 AI agent），以及需要维护插件管理器的人。
> 所有坑均为实机验证过的真实错误，标注了报错原文，可据此快速定位。

---

## 一、架构总览

```
ERB/PLUGIN/
├── PLUGIN_MANAGER.ERH    # 全局变量声明（#DIMS），Emuera 自动包含
├── PLUGIN_MANAGER.ERB    # 注册表 @PLUGIN_INIT + 管理界面 @PLUGIN_MANAGER + 分发 @PLUGIN_HOOK
├── PLUGIN_DEV_GUIDE.md   # 本文档
└── <插件ID>/             # 每个插件一个目录，删除目录 = 卸载插件
    └── PLUGIN_<ID>.ERB   # 插件本体（可含多个文件、多个函数）
```

**核心机制三件套：**

| 机制 | 实现 | 说明 |
|------|------|------|
| 注册表 | `@PLUGIN_INIT` 中给 `PLUGIN_ID/NAME/DESC` 数组赋值 | 从序号 0 连续登记，不可跳号 |
| 开关 | `GLOBAL:(100+序号)`，1=开 0=关 | 随 `LOADGLOBAL/SAVEGLOBAL` 跨存档共享，无需额外保存代码 |
| 分发 | 主流程 `CALL PLUGIN_HOOK("事件名")` → 对每个已开启插件 `TRYCALLFORM PLUGIN_<ID>_<事件名>` | 插件未实现该事件时自动跳过，不报错 |

**文件编码硬性要求：UTF-8 BOM + CRLF 换行**（与项目全部 ERB 一致）。用 `git diff` 提交后若看到整文件差异，多半是编码坏了。

---

## 二、现有钩子点与新增钩子点

### 2.1 现有钩子点（全部在 master）

| 事件名 | 位置 | 触发时机 |
|--------|------|----------|
| `BOOT` | `ERB/SYSTEM/SYSTEM.ERB:13`（`@EVENTFIRST` 内） | 新游戏初始化 |
| `SHOP` | `ERB/SYSTEM/SHOP/SHOP.ERB:76` | 商店菜单 |
| `EVENTCOMEND` | `ERB/TRAIN/EVENTCOMEND.ERB:34` | 一次调教结束 |
| `CHARAMAKE_MENU` | `ERB/SYSTEM/CHARAMAKING/CHARA_MAKER.ERB:20`（`$MAKE_OR_LORD` 内） | 角色菜单 `[0]制作角色 [1]加载角色` 显示时 |
| `CHARAMAKE_SELECT` | `ERB/SYSTEM/CHARAMAKING/CHARA_MAKER.ERB:40` | 玩家在角色菜单选 `[2]` 时 |

### 2.2 如何新增一个钩子点（改主流程，一次提交）

在主流程某个函数的合适位置加一行：

```eramicscript
;插件系统：<事件名> 事件钩子（已开启的插件在此时执行）
CALL PLUGIN_HOOK("<事件名>")
```

要点：
- 事件名用**大写英文**（惯例：`BOOT`/`SHOP`/`EVENTCOMEND`），由插件端拼进函数名 `@PLUGIN_<ID>_<事件名>`。
- 钩子调用处应放在**该流程关键节点**（如菜单打印后、回合结束前）。
- 若钩子需要**返回值**给主流程（例如「插件是否处理了某输入」），目前 `@PLUGIN_HOOK` 固定 `RETURN 0`，会覆盖 RESULT——需要扩展分发函数把 `RESULT` 聚合回来（见 §5.4）。
- 菜单类钩子常需要「插件打印额外选项 + 主流程响应」两个事件成对出现（参考 `CHARAMAKE_MENU` / `CHARAMAKE_SELECT`）。

### 2.3 完整示例：custom 插件如何接入角色菜单

`CHARA_MAKER.ERB` 的 `$MAKE_OR_LORD` 菜单：

```eramicscript
$MAKE_OR_LORD
PRINTFORMDL [0]角色制作
PRINTFORMDL [1]角色加载
;插件系统：CHARAMAKE 菜单钩子（插件可在此附加 [2] 等选项）
CALL PLUGIN_HOOK("CHARAMAKE_MENU")
CALL INPUTINT(0, 1, 2)          ;注意从 (0,1) 扩到 (0,1,2)
IF RESULT == 1
    ...原加载逻辑...
ELSEIF RESULT == 2
    ;插件自定义角色制作（由已开启插件响应，未响应则回菜单）
    CALL PLUGIN_HOOK("CHARAMAKE_SELECT")
    GOTO MAKE_OR_LORD
ENDIF
```

插件端（`ERB/PLUGIN/custom/PLUGIN_CUSTOM.ERB`）：

```eramicscript
@PLUGIN_custom_CHARAMAKE_MENU
PRINTFORMDL [2]自定义角色制作
RETURN 0

@PLUGIN_custom_CHARAMAKE_SELECT
CALL PLUGIN_CUSTOM_EDITOR
RETURN 0
```

**约束**：新增菜单选项时，主流程 `CALL INPUTINT(...)` 的上限要同步扩；插件打印的选项编号需与主流程 `ELSEIF RESULT == N` 分支一致。

---

## 三、编写一个插件（标准流程）

### 3.1 目录与文件

```
ERB/PLUGIN/<插件ID>/
└── PLUGIN_<插件ID>.ERB    # 命名随意，但建议 PLUGIN_<ID>.ERB
```

插件 ID 规范：**半角英文/数字**，小写，同时用作目录名、函数名前缀、注册表 ID。

### 3.2 钩子函数命名

```eramicscript
@PLUGIN_<插件ID>_<事件名>
```

- 大小写不敏感（Emuera 函数名不区分大小写），但保持全小写 ID + 大写事件名便于阅读。
- 一个插件可响应多个事件，写多个 `@PLUGIN_<ID>_<事件>` 函数即可；未响应的事件自动跳过。

### 3.3 登记注册表

在 `@PLUGIN_INIT` 中**按顺序追加**（custom 已占 0 号，新插件从 1 号起）：

```eramicscript
@PLUGIN_INIT
PLUGIN_ID:0   = custom
PLUGIN_NAME:0 = 角色制作增强
PLUGIN_DESC:0 = 在角色菜单增加[2]自定义角色制作
;↓↓ 新插件从序号 1 开始
PLUGIN_ID:1   = myplugin
PLUGIN_NAME:1 = 我的插件
PLUGIN_DESC:1 = 一句话简介
RETURN 0
```

> ⚠️ **字符串数组赋值必须无引号**（`PLUGIN_ID:0 = custom`，不是 `"custom"`）。带引号会把引号本身存进值（见 §4.4）。

### 3.4 提交与推送

```bash
git add ERB/PLUGIN/
git commit -m "开发插件xxx：<功能摘要>"
git push origin master
```

---

## 四、Emuera 语法陷阱清单（全部实机踩过，务必遵守）

### 4.1 `#DIM/#DIMS` 不能放 `.ERB` 顶层

- **只能放同名 `.ERH` 头文件**（Emuera 自动包含同目录同名 `.ERH`）。
- `.ERB` 顶层写 `#DIM` 报错：`変数宣言の直後以外に#行が使われています`。
- `.ERH` 里每行**只声明一个变量**：
  ```eramicscript
  #DIMS PLUGIN_ID, 32    ; 变量名, 容量
  #DIMS PLUGIN_NAME, 32
  ```
- ⚠️ **`#DIMS A, B, C` 逗号多变量声明不被支持**——`B` 会被当成容量解析，报 `B（解析为）識别子`。必须拆成多行。

### 4.2 `CONST` 常量只能函数内声明

`#DIMS CONST` 只能在函数体内用 `{}` 包裹声明（参考 `CONFIGURE.ERB` 的 `CONF` 数组），顶层不可用。

### 4.3 `SIF` 不支持单行冒号写法

```eramicscript
; ✗ 报错：構文解析中予期しない記号 ':'
SIF PLUGIN_ID:(LOCAL_I) == "" : CONTINUE
; ✓ 必须两行式
SIF PLUGIN_ID:(LOCAL_I) == ""
    CONTINUE
```

### 4.4 字符串数组赋值带引号 = 存引号本身（大坑）

```eramicscript
PLUGIN_ID:0 = "demo"   ; ✗ 实际存的值是 "demo"（含引号字符）
PLUGIN_ID:0 = demo     ; ✓ 存的是 demo
```

- 后果：`%PLUGIN_ID:0%` 展开出 `"demo`，拼出的函数名 `PLUGIN_"demo"_BOOT` 不存在，`TRYCALLFORM` 静默跳过——**完全无报错**，只能靠打印诊断发现。
- 本体先例：`LOCALS:0 = まだ柔らかい`（`COMMON_GETTER_CHARA.ERB`）。
- 纯 ASCII 的 ID 无引号赋值**不会**被当作变量解析（实测安全）。

### 4.5 字符串赋值是模板式，不是表达式（大坑）

```eramicscript
; ✗ 会把整段源码文本存进 LOCAL_FUNC（%LOCAL_FUNC% 展开出 "a"+变量+"b" 原文）
LOCAL_FUNC = "PLUGIN_" + PLUGIN_ID:(LOCAL_I) + "_" + ARGS
; ✓ 模板式：% 外是字面量，%变量% 展开
LOCAL_FUNC = PLUGIN_%LOCAL_ID%_%ARGS%
```

- 追加拼接用 `+=`：`LOCALS += "字面量" + 变量`（本体 `HTML_FUNC.ERB` 先例）。
- 单个数组元素取值用 `%` 包裹：`LOCAL_ID = %PLUGIN_ID:(LOCAL_I)%`（本体 `RESULTS = %CALLNAME:(RESULT:2)%` 先例）。

### 4.6 TRYCALLFORM 的 `%变量%` 展开只支持函数参数（最大坑）

实测结论（多轮对照实验）：
- `TRYCALLFORM %ARGS%` / `TRYCALLFORM PLUGIN_%ARGS%_%ARGS:1%` → **有效**（参数展开）
- `TRYCALLFORM %LOCAL_ID%`（局部变量）→ **无效**
- `TRYCALLFORM %PLUGIN_FUNC%`（全局变量）→ **无效**
- `TRYCALLFORM PLUGIN_%PLUGIN_ID:(LOCAL_I)%_%ARGS%`（数组元素）→ **无效**

**唯一可行方案**：经中间函数把插件 ID 作为参数传入：

```eramicscript
@PLUGIN_HOOK(ARGS)
#DIM LOCAL_I
#DIMS LOCAL_ID
CALL PLUGIN_INIT
FOR LOCAL_I, 0, 32
    SIF PLUGIN_ID:(LOCAL_I) == ""
        CONTINUE
    SIF GLOBAL:(100 + LOCAL_I) == 0
        CONTINUE
    LOCAL_ID = %PLUGIN_ID:(LOCAL_I)%          ; 数组→简单变量
    CALL PLUGIN_HOOK_DISPATCH(LOCAL_ID, ARGS) ; ID 作参数传入
NEXT
RETURN 0

@PLUGIN_HOOK_DISPATCH(ARGS, ARGS:1)
TRYCALLFORM PLUGIN_%ARGS%_%ARGS:1%            ; 参数展开，成功
RETURN 0
```

### 4.7 PRINT 文本中的方括号 `[...]` 会被当作指令/数式解析

```eramicscript
PRINTL [demo] xxx        ; ✗ 警告：数式指定が誤り（方括号内纯文本被当数式）
PRINTL (demo) xxx        ; ✓ 全角括号安全
PRINTFORML [{LOCAL}] ... ; ✓ 方括号包 {数式} 合法（参考 CONFIGURE.ERB）
```

- 方括号内是**数式**（`{变量}`）才合法；纯文本必须用全角括号 `（）` 或 `%"[10] 插件管理", 50, LEFT%` 包裹。
- `PRINTBUTTON` 的文本参数 `@"..."` 内可以自由用 `[ ]`（本体 `HTMLBUTTON`/`PRINTBUTTON` 广泛使用）。

### 4.8 `PRINTFORML` 中 `{...}` 是数式（数值），字符串用 `%...%`

```eramicscript
PRINTFORML (HOOK) 事件={ARGS} ...   ; ✗ ARGS 是字符串，报 {の中が数式ではありません
PRINTFORML (HOOK) 事件=%ARGS% ...   ; ✓ 字符串用 %展开
PRINTFORML (HOOK) 数值={LOCAL} ...  ; ✓ 数值用 {数式}
```

### 4.9 `%` 展开内不能有 `?` 条件运算符

```eramicscript
PRINTFORML %TALENT:MASTER:胆怯 ? 开 # 关%   ; ✗ 报错（"开"被当标识符）
PRINTFORML ...\@ TALENT:MASTER:胆怯 ? 开 # 关 \@  ; ✓ 本体标准分支语法
```

- 显示分支用 `\@ 条件 ? 值 # 值 \@`（本体 `CHARA_MAKER.ERB:90` 先例：`普通的\@ TALENT:MASTER:男人 ? 青年 # 女性 \@程度`）。
- 若要在表达式里算值给变量，先 `LOCAL_X = 条件 ? 1 # 0`（数值），再按数值显示。

### 4.10 `RETURNF` 只能在 `#FUNCTIONS` 函数中使用

```eramicscript
; 普通函数 ✗ 警告：RETURNFが#FUNCTION以外で使用されました
RETURNF -1
; 普通函数 ✓ 用 RETURN，其参数会写入 RESULT
RETURN -1
```

- 普通函数返回值 = 设置 `RESULT` 后 `RETURN 0`，或直接 `RETURN 值`（值写入 RESULT）。
- `RETURN 0` 会把 RESULT 覆盖为 0——若先设了 `RESULT = -1` 再 `RETURN 0`，RESULT 变 0，上层判断失效。**要么 `RETURN -1`，要么 `RETURN RESULT`**。

### 4.11 数组下标与赋值目标

- 下标可用括号表达式：`GLOBAL:(100 + LOCAL_I)`、`TALENT:MASTER:(LOCAL:1)`。
- 赋值目标必须是单一变量：`GLOBAL:(100 + LOCAL_SLOT) ^= 1` 合法；`GLOBAL:100 + X ^= 1` 非法。

### 4.12 块配对关键字

`IF/ENDIF`、`FOR/NEXT`、`SELECTCASE/ENDSELECT`、`DO/LOOP`、`WHILE/WEND`、方括号指令 `[IF_DEBUG]/[ENDIF]`、`[SKIPSTART]/[SKIPEND]`（SKIP 块内代码不编译）。

### 4.13 字符串引号

每行 `"` 必须成对；行首 `;` 是注释。

---

## 五、插件管理器内部机制（维护者必读）

### 5.1 注册表容量与遍历

- `PLUGIN_ID/NAME/DESC` 是容量 32 的全局字符串数组（`PLUGIN_MANAGER.ERH`）。
- 所有遍历用 `FOR LOCAL_I, 0, 32` + `SIF PLUGIN_ID:(LOCAL_I) == "" → CONTINUE`。
- **扩展容量**：改 `.ERH` 三处 `#DIMS ... , 32` → 新容量，并同步 `@PLUGIN_MANAGER` 与 `@PLUGIN_HOOK` 两处 `FOR ... , 0, 32` 的上限。

### 5.2 开关槽位

- 槽位 `i` 的开关 = `GLOBAL:(100 + i)`。`GLOBAL:100` 起是为了避开本体已使用的 GLOBAL 槽位。
- 切换：`GLOBAL:(100 + LOCAL_SLOT) ^= 1` + `SAVEGLOBAL`（立即落盘，重启不丢）。
- 管理界面输入序号（1,2,3…）→ 需映射回注册表槽位：遍历计数第 N 个非空槽。

### 5.3 管理界面显示规范（已实现）

- 标题：亮黄 `0xFFFF00`（与配置菜单一致）。
- 已启用插件：插件名绿色 `0x70C070` + `[开启]`；简介灰 `0x969696`。
- 未启用插件：插件名亮灰 `0xB0B0B0`（比简介亮一档）+ `[关闭]`；简介灰 `0x969696`。
- 每行用 `PRINTBUTTON @"[{序号}] %PLUGIN_NAME%　—　[开启/关闭]", 序号` 渲染成可点击按钮（悬停有反馈、可鼠标点击切换）。
- 按钮返回的序号与 `INPUT` 输入的数字**共用同一套序号映射**，所以键盘/鼠标操作一致。
- 记住当前颜色：进入时 `LOCAL_COLOR = GETCOLOR()`，每次 `SETCOLOR` 后恢复 `SETCOLOR LOCAL_COLOR`。
- 清屏用 `CLEARLINE LINECOUNT - LOCAL_LINE`（进入时 `LOCAL_LINE = LINECOUNT`）。

### 5.4 已知限制（待扩展）

- `@PLUGIN_HOOK` 固定 `RETURN 0`，**不聚合各插件的返回值**。若需要「插件报告是否处理了事件」，需在分发循环里收集（如各插件把结果写进 `GLOBAL` 或 `LOCALS`，或给 `PLUGIN_HOOK_DISPATCH` 加返回值聚合）。
- 事件名目前**不带参数**（只有事件名）。若插件需要主流程上下文（如当前角色、当前动作），需新增带参钩子或约定插件自行读取全局变量（`TARGET`/`MASTER`/`TFLAG` 等本体变量对插件同样可见）。
- 注册表容量 32，插件超过需扩容（见 5.1）。

### 5.5 配置菜单入口

- `ERB/SYSTEM/SHOP/CONFIGURE.ERB:37` 用 `PRINTFORML %"[10] 插件管理", 50, LEFT%` 打印入口（**注意：方括号文本用 `%"...", 50, LEFT%` 包裹，规避 §4.7**）。
- `CASE 10 → CALL PLUGIN_MANAGER`（第 76-77 行）。
- 新增配置项时参考 `CONFIGURE.ERB` 的 `INPUT_RANGE` 输入校验模式。

---

## 六、常见调试手法（实机验证有效）

### 6.1 定位「无报错但功能不生效」

`TRYCALLFORM` 目标不存在时**静默跳过、无任何报错**，这是最隐蔽的情况。按此排查：

1. **确认插件文件被编译**：插件 `.ERB` 顶层加一行临时 `PRINTL (xxx) 已编译`，启动看是否输出（注意：顶层 PRINTL 会在加载阶段执行，定位后删除）。
2. **确认分发走到了**：在 `@PLUGIN_HOOK` 内临时 `PRINTFORML (HOOK) 事件=%ARGS% 目标=%PLUGIN_FUNC%`，看目标函数名拼得对不对。
3. **确认函数存在**：临时 `CALL PLUGIN_<ID>_<事件>`（直接调用）对比——能调通则文件/函数没问题，问题在动态分发。
4. **确认注册表值**：打印 `%PLUGIN_ID:0%`，检查是否带引号（§4.4）。

### 6.2 字符串内容确认

`PRINTFORML 值=「%变量%」`（全角引号 `「」` 包住值，避免与方括号陷阱冲突）。

### 6.3 静态自检（提交前必跑）

检查：编码 BOM+CRLF、引号成对、块配对、无单行冒号 SIF、无 `%...?...%`、`RETURNF` 只在 `#FUNCTIONS`、`\@` 成对、GOTO 标签存在。可参考 `tools/` 下的历史自检脚本（一次性脚本，用完即删）。

### 6.4 编码检查

```bash
python -c "
raw = open('ERB/PLUGIN/xxx.ERB','rb').read()
print(raw.startswith(b'\xef\xbb\xbf'), b'\r\n' in raw)"
```

---

## 七、工作规范

- 动手前 `git status` / `git log --oneline -5`。
- 新写/修改的 ERB 保持 **UTF-8 BOM + CRLF**。
- 提交信息用中文，格式参照历史提交。
- 每次改完：静态自检 → 提交 → push，保持远端同步。
- 插件默认**关闭**（不写 `GLOBAL:100+X = 1`），由用户在插件管理中开启。
- 删除插件目录即可卸载；不用的插件用注释注销注册表（保留文件供日后测试，如 demo 插件）。
- 主流程改动（新增钩子点、菜单扩展）与插件本体改动**分开提交**，便于回溯。
