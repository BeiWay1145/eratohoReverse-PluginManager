# eratohoЯeverse 插件管理器

为 **eratohoЯeverse（Emuera 引擎）** 提供插件系统：插件注册表、独立开关、事件钩子分发与图形化管理界面。

已针对汉化版 **CNTEST v0.219**（eratohoЯeverse 1.2.14-CN）适配并实测验证。

---

## 一、三种使用方式

按门槛从低到高排列，**任选其一**：

| | 方式 ①：整合包 | 方式 ②：增量覆盖包 | 方式 ③：安装脚本 |
|---|---|---|---|
| 适合 | 没有游戏本体 | 已有**同版本**本体 | 本体**任意版本**（含汉化更新后） |
| 体积 | 约 11 MB | 约 57 KB | 约 60 KB |
| 门槛 | **解压双击即玩** | 解压覆盖 | 需要 Python 3 |
| 抗汉化更新 | — | 弱 | **强**：锚点自动适配 |

产物均由 `installer/make_release.py` 生成，无需手工维护。

### 方式 ①：整合包（解压即用，推荐给新玩家）

下载 `eratohoReverse-<版本>-PluginManager-<日期>-full.zip`，解压后**双击 `Emuera1824+v1.exe`** 即可。

游戏内：**商店菜单 → `[178]` 配置 → `[10]` 插件管理**。

> 包内已附 `README-先读我.txt`，含使用说明与版权署名。

### 方式 ②：增量覆盖包（已自备本体）

下载 `plugin-<日期>-overlay.zip`，把里面的 `ERB/` 覆盖到游戏目录的 `ERB/` 上。

⚠️ 仅适用于**与构建版本一致**的本体；版本不符请改用方式 ③。

### 方式 ③：安装脚本（本体任意版本）

```bash
python installer/install.py --game "D:/path/to/eratohoЯeverse-1.214-CNTESTv0.219"
```

| 参数 | 作用 |
|------|------|
| `--dry-run` | 只打印计划，不写盘 |
| `--backup` | 改动前备份到 `<游戏>/.plugin_backup/<时间戳>/` |

脚本会：校验游戏目录 → 读取版本 → 复制框架 → 插入 5 处钩子 → 装配置菜单入口，
最后打印 `安装 N / 已装 N / 跳过 N / 失败 N`。**失败会返回非 0 退出码**，不会静默装坏。

---

## 二、内置插件

| 槽位 | ID | 名称 | 说明 |
|------|----|------|------|
| 0 | `custom` | 角色制作增强 | 角色菜单增加 `[2]` 自定义角色制作（姓名/性别/性格/性质/经验，存 GLOBALS 槽位） |
| — | `demo` | 示例插件 | **未登记**，保留文件供测试钩子链路 |

插件默认**全部关闭**，需在 `[10]` 插件管理 中手动开启。

---

## 三、加固设计（为什么不怕汉化更新）

汉化组更新时文案与结构都会变，写死字符串的补丁必然失效。本安装器：

1. **版本探测** —— 读 `CSV/GameBase.csv` 的 `バージョン` / `ウィンドウタイトル` 并打印。
2. **结构锚点优先，多候选兜底** —— 每处钩子配多个锚点，按序尝试，任一命中即可。
   实测：改掉 `[888] - 口上表示设定` 的文案、在 `SAVEGLOBAL/LOADGLOBAL` 间插注释，安装依然成功。
3. **失败即报告** —— 所有锚点都不命中时返回 `MISS` + 退出码 1，**绝不静默跳过**。
4. **幂等** —— 重复运行报 `ALREADY`，不会重复插入。

### ⚠️ 一条用血换来的约束

**钩子绝不能插在 `@函数名` 与紧随其后的 `#DIM` 声明块之间。**
Emuera 要求 `#DIM` 必须紧跟函数声明；中间插语句会让整块声明失效，
本项目曾因此产生 **503 条连锁报错**（变量未定义、FOR/NEXT 失配）。
安装器已修正为插到 `#DIM` 块**之后**。

回归测试：

```bash
python tests/test_installer.py --game "<纯净游戏目录>"
```

覆盖 5 类场景：干净本体 / 文案被改 / 主锚点被破坏 / 锚点消失（应报 MISS） / CASE 形式变化。

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

## 五、开发

- **插件开发指南**：[ERB/PLUGIN/PLUGIN_DEV_GUIDE.md](ERB/PLUGIN/PLUGIN_DEV_GUIDE.md)
- **静态自检**（提交前必跑）：

```bash
python tools/plugin_check.py "游戏目录/ERB/PLUGIN/**/*.ERB" "游戏目录/ERB/PLUGIN/**/*.ERH"
```

- **运行时验证**：[`tools/emuera-driver/`](tools/emuera-driver/) —— MCP 服务器，
  可启动游戏、抓取引擎日志、注入探针验证钩子链路。附带
  [输入注入方案](tools/emuera-driver/INPUT-INJECTION.md)（实测验证）。

### 编码规范（重要）

所有 `.ERB`/`.ERH` 必须是 **UTF-8 BOM + CRLF**。

⚠️ 很多编辑器与自动化工具写回文件时会**静默丢掉 BOM**。本项目实际踩到过，提交前务必确认：

```bash
python tools/fix_bom.py "游戏目录/ERB" --dry-run   # 只报告
python tools/fix_bom.py "游戏目录/ERB"             # 修正
```

---

## 六、目录结构

```
ERB/PLUGIN/                  插件框架
installer/install.py         安装脚本（方式 ③）
installer/make_release.py    生成整合包 / 增量包（方式 ①②）
installer/HOOKS.md           钩子点手动安装参考
tools/plugin_check.py        插件静态自检
tools/fix_bom.py             BOM/换行修复
tools/emuera-driver/         运行时驱动 MCP + 注入方案
tests/                       安装器回归 + 游戏冒烟/驱动脚本
```

---

## 七、版权与致谢

- **游戏本体**：eratohoЯeverse —— 版权归 **Reverse Developers team** 所有。
- **中文汉化**：版权归 **汉化组** 所有。本仓库**不对汉化内容主张任何权利**，
  发布的整合包也**未改动汉化内容**，仅在其之上增加了插件层。
- **Emuera 引擎**：版权归其原作者所有。
- **东方 Project**：二次创作，版权归 上海アリス幻樂団 / ZUN 所有。
- **插件系统与插件**：BeiWay1145。

**分发条件**（摘自原版 readme）：

> 「サポートは各バリアントの作者が行う事が改編・再配布の条件となっています」

即允许改编与再分发，条件是**由本 variant 的作者提供支持**。
请勿就本项目向原引擎作者或上海アリス幻樂団咨询。

> 本游戏含过激性描写，**18 岁以下禁止游玩**。
