# eratohoЯeverse 插件管理器

为 **eratohoЯeverse（Emuera 引擎）** 提供插件系统：插件注册表、独立开关、事件钩子分发与图形化管理界面。

> 本仓库**只包含插件系统本身**，不含游戏本体。
> 已针对汉化版 **CNTEST v0.219**（eratohoЯeverse 1.2.14-CN）验证。

---

## 一、两种安装方式

| | 方式 A：安装脚本 | 方式 B：增量覆盖包 |
|---|---|---|
| 适合 | 游戏本体**任何版本**（含汉化更新后） | 与构建版本**完全一致**的本体 |
| 做法 | 跑脚本，自动适配你的文件结构 | 解压覆盖 `ERB/` |
| 门槛 | 需要 Python 3 | 零门槛 |
| 抗更新 | **强**：锚点自动适配，失败会明确报告 | 弱：版本不符可能覆盖错 |

**推荐 A。** B 包由 A 自动产出（见下），无需手工维护。

### 方式 A：安装脚本（推荐）

```bash
python installer/install.py --game "D:/path/to/eratohoЯeverse-1.214-CNTESTv0.219"
```

常用参数：

| 参数 | 作用 |
|------|------|
| `--dry-run` | 只打印计划，不写盘 |
| `--backup` | 改动前备份到 `<游戏>/.plugin_backup/<时间戳>/` |

脚本会：校验游戏目录 → 读取版本 → 复制框架 → 插入 5 处钩子 → 装配置菜单入口，
最后打印 `安装 N / 已装 N / 跳过 N / 失败 N`。**失败会返回非 0 退出码**，不会静默装坏。

### 方式 B：从 release 包覆盖

```bash
python installer/make_release.py --game "<已装好插件的游戏目录>"
# 产出 release/plugin-<日期>.zip，用户解压覆盖 ERB/ 即可
```

---

## 二、加固设计（为什么不怕汉化更新）

汉化组更新时文案与结构都会变，写死字符串的补丁必然失效。本安装器：

1. **版本探测** —— 读 `CSV/GameBase.csv` 的 `バージョン` / `ウィンドウタイトル` 并打印，
   让你一眼确认补丁是否作用于预期版本。
2. **结构锚点优先，多候选兜底** —— 每处钩子配多个锚点，按序尝试，任一命中即可。
   实测：把 `[888] - 口上表示设定` 的文案改掉、在 `SAVEGLOBAL/LOADGLOBAL` 间插注释，
   安装依然成功（自动降级到兜底锚点）。
3. **失败即报告** —— 所有锚点都不命中时返回 `MISS` + 退出码 1，
   提示按 `installer/HOOKS.md` 手动处理，**绝不静默跳过**。
4. **幂等** —— 重复运行报 `ALREADY`，不会重复插入。

回归测试：

```bash
python tests/test_installer.py --game "<纯净游戏目录>"
```

覆盖 5 类场景：干净本体 / 文案被改 / 主锚点被破坏 / 锚点消失（应报 MISS） / CASE 形式变化。

---

## 三、使用

游戏内：**商店菜单 → `[178]` 配置 → `[10]` 插件管理**

显示每个插件的名称、简介与 `[开启/关闭]`，点击整行（或输入序号）切换。
开关立即 `SAVEGLOBAL` 落盘，重启不丢、跨存档共享。插件默认**关闭**。

---

## 四、钩子点

| 事件名 | 位置 | 触发时机 |
|--------|------|----------|
| `BOOT` | `ERB/SYSTEM/SYSTEM.ERB` | 新游戏初始化 |
| `SHOP` | `ERB/SYSTEM/SHOP/SHOP.ERB` | 商店菜单 |
| `EVENTCOMEND` | `ERB/TRAIN/EVENTCOMEND.ERB` | 一次调教结束 |
| `CHARAMAKE_MENU` | `ERB/SYSTEM/CHARAMAKING/CHARA_MAKER.ERB` | 角色菜单显示时（可附加选项） |
| `CHARAMAKE_SELECT` | 同上 | 玩家选择插件附加的选项时 |

手动安装参考见 [`installer/HOOKS.md`](installer/HOOKS.md)。

---

## 五、已包含的插件

| 槽位 | ID | 名称 | 说明 |
|------|----|------|------|
| 0 | `custom` | 角色制作增强 | 角色菜单增加 `[2]` 自定义角色制作（姓名/性别/性格/性质/经验，存 GLOBALS 槽位） |
| — | `demo` | 示例插件 | **未登记**，保留文件供测试钩子链路 |

---

## 六、开发插件

见 [`ERB/PLUGIN/PLUGIN_DEV_GUIDE.md`](ERB/PLUGIN/PLUGIN_DEV_GUIDE.md)。

提交前跑静态自检：

```bash
python tools/plugin_check.py "游戏目录/ERB/PLUGIN/**/*.ERB" "游戏目录/ERB/PLUGIN/**/*.ERH"
```

---

## 七、编码规范（重要）

所有 `.ERB`/`.ERH` 必须是 **UTF-8 BOM + CRLF**。

⚠️ 很多编辑器与自动化工具写回文件时会**静默丢掉 BOM**。本项目开发过程中已实际踩到，
提交前务必确认：

```bash
python tools/fix_bom.py "游戏目录/ERB" --dry-run   # 只报告
python tools/fix_bom.py "游戏目录/ERB"             # 修正
```

---

## 八、目录结构

```
ERB/PLUGIN/            插件框架（发布时复制进游戏）
installer/install.py   安装脚本（方式 A）
installer/HOOKS.md     钩子点手动安装参考
installer/make_release.py  生成增量覆盖包（方式 B）
tools/plugin_check.py  插件静态自检
tools/fix_bom.py       BOM/换行修复
tests/test_installer.py 安装器回归测试
```
