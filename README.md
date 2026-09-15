# eratohoЯeverse 插件管理器

为 **eratohoЯeverse（Emuera 引擎）** 提供插件系统：插件注册表、独立开关、事件钩子分发与图形化管理界面。

> 本仓库**只包含插件系统本身**，不含游戏本体。
> 游戏本体请从汉化组渠道获取（本系统针对 **CNTEST v0.219** 汉化版适配）。

---

## 一、它是什么

一套轻量插件框架。每个插件是一个独立目录，删目录即卸载：

```
ERB/PLUGIN/
├── PLUGIN_MANAGER.ERH     全局数组声明（Emuera 自动包含）
├── PLUGIN_MANAGER.ERB     注册表 + 管理界面 + 事件分发
├── PLUGIN_DEV_GUIDE.md    插件开发指南（语法陷阱清单）
├── <插件ID>/              每个插件一个目录
│   └── PLUGIN_<ID>.ERB
└── ...
```

三个核心机制：

| 机制 | 实现 | 说明 |
|------|------|------|
| 注册表 | `@PLUGIN_INIT` 给 `PLUGIN_ID/NAME/DESC` 数组赋值 | 从序号 0 连续登记，不可跳号 |
| 开关 | `GLOBAL:(100+序号)`，1=开 0=关 | 随 `SAVEGLOBAL` 跨存档共享，无需额外保存代码 |
| 分发 | `CALL PLUGIN_HOOK("事件名")` | 对每个已开启插件 `TRYCALLFORM PLUGIN_<ID>_<事件名>` |

未实现某事件的插件会被自动跳过，不报错。

---

## 二、安装

插件系统需要**在主流程中埋入钩子点**，因此安装分两步：复制文件 + 打补丁。

### 方式 A：一键安装脚本（推荐）

```bash
python installer/install.py --game "D:/path/to/eratohoЯeverse-1.214-CNTESTv0.219"
```

脚本会：
1. 校验游戏目录（找 `Emuera*.exe` 与 `ERB/`）
2. 复制 `ERB/PLUGIN/` 到游戏
3. 在 5 个主流程位置插入钩子（**幂等**：已插入则跳过，不重复插入）
4. 打印每一处改动

加 `--dry-run` 可只看计划不落盘。安装前请自行备份 `ERB/`。

### 方式 B：手动

1. 把 `ERB/PLUGIN/` 整个复制进游戏的 `ERB/` 下；
2. 按 [`installer/HOOKS.md`](installer/HOOKS.md) 手动插入 5 处钩子与配置菜单入口。

---

## 三、使用

游戏内：**商店菜单 → `[178]` 配置 → `[10]` 插件管理**

界面显示每个插件的名称、简介与 `[开启/关闭]` 状态，点击整行（或输入序号）即可切换。
开关立即 `SAVEGLOBAL` 落盘，重启不丢、跨存档共享。

插件默认**关闭**，需手动开启。

---

## 四、适配的钩子点

| 事件名 | 位置 | 触发时机 |
|--------|------|----------|
| `BOOT` | `ERB/SYSTEM/SYSTEM.ERB` | 新游戏初始化 |
| `SHOP` | `ERB/SYSTEM/SHOP/SHOP.ERB` | 商店菜单 |
| `EVENTCOMEND` | `ERB/TRAIN/EVENTCOMEND.ERB` | 一次调教结束 |
| `CHARAMAKE_MENU` | `ERB/SYSTEM/CHARAMAKING/CHARA_MAKER.ERB` | 角色菜单显示时（可附加选项） |
| `CHARAMAKE_SELECT` | 同上 | 玩家选择插件附加的选项时 |

---

## 五、已包含的插件

| 槽位 | ID | 名称 | 说明 |
|------|----|------|------|
| 0 | `custom` | 角色制作增强 | 角色菜单增加 `[2]` 自定义角色制作（姓名/性别/性格/性质/经验，存 GLOBALS 槽位） |
| — | `demo` | 示例插件 | **未登记**，保留文件供测试钩子链路 |

---

## 六、开发插件

见 [`ERB/PLUGIN/PLUGIN_DEV_GUIDE.md`](ERB/PLUGIN/PLUGIN_DEV_GUIDE.md)（钩子写法、Emuera 语法陷阱清单、调试手法）。

提交前请跑静态自检：

```bash
python tools/plugin_check.py "游戏目录/ERB/PLUGIN/**/*.ERB" "游戏目录/ERB/PLUGIN/**/*.ERH"
```

检查：UTF-8 BOM + CRLF、引号成对、块配对、单行冒号 SIF、`%..?..%`、`RETURNF` 误用、
`PRINT` 文本方括号、`GOTO` 标签存在、`\@` 成对。退出码 0 = 通过。

---

## 七、编码规范

所有 `.ERB`/`.ERH` 必须是 **UTF-8 BOM + CRLF**，与游戏本体一致。
注意：不少编辑器（含部分自动化工具）写回文件时会**丢掉 BOM**，提交前务必用
`tools/plugin_check.py` 或 `tools/fix_bom.py` 确认。
