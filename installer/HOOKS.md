# 钩子点清单（手动安装参考）

本文件列出插件系统需要的全部主流程改动。一键脚本 `installer/install.py` 会自动完成，
这里给出逐条内容，供手动安装或核对使用。

> 所有文件必须保持 **UTF-8 BOM + CRLF**。

---

## 1. `ERB/SYSTEM/SYSTEM.ERB` — BOOT

在 `@EVENTFIRST` 内，第二次 `LOADGLOBAL` 之后插入：

```eramicscript
SAVEGLOBAL
LOADGLOBAL
;插件系统：BOOT 事件钩子（已开启的插件在此时执行）
CALL PLUGIN_HOOK("BOOT")
;キャラクター役割変数を初期化
```

---

## 2. `ERB/SYSTEM/SHOP/SHOP.ERB` — SHOP

在商店菜单 `DRAWLINE` 之前插入：

```eramicscript
CALL HTMLPRINTL(HTMLBUTTON("[888] - 口上表示设定", "888", "设置口上的显示/隐藏"))
;插件系统：SHOP 事件钩子（已开启的插件在此时执行）
CALL PLUGIN_HOOK("SHOP")
DRAWLINE
```

---

## 3. `ERB/TRAIN/EVENTCOMEND.ERB` — EVENTCOMEND

在 `@EVENTCOMEND` 函数体最前面插入：

```eramicscript
@EVENTCOMEND
;插件系统：EVENTCOMEND 事件钩子（已开启的插件在此时执行）
CALL PLUGIN_HOOK("EVENTCOMEND")
;カウント変数
```

---

## 4. `ERB/SYSTEM/CHARAMAKING/CHARA_MAKER.ERB` — CHARAMAKE

把 `$MAKE_OR_LORD` 菜单中的 `CALL INPUTINT(0, 1)` 整行替换为：

```eramicscript
	$MAKE_OR_LORD
	PRINTFORMDL [0] 捏一个新角色
	PRINTFORMDL [1] 加载捏好的角色
	;插件系统：CHARAMAKE 菜单钩子（插件可在此附加 [2] 等选项）
	CALL PLUGIN_HOOK("CHARAMAKE_MENU")
	CALL INPUTINT(0, 1, 2)
	IF RESULT == 2
		;插件自定义角色制作（由已开启插件响应，未响应则回菜单）
		CALL PLUGIN_HOOK("CHARAMAKE_SELECT")
		GOTO MAKE_OR_LORD
	ENDIF
	IF RESULT == 1
```

**注意**：`INPUTINT` 上限必须同步从 `1` 扩到 `2`，否则插件打印的 `[2]` 选项无法被选中。

---

## 5. `ERB/SYSTEM/SHOP/CONFIGURE.ERB` — 管理界面入口

三处改动：

### 5.1 打印菜单项（在 `[ 9]` 之后、`DO` 之前）

```eramicscript
	PRINTFORML %"[ 9] 调教时的界面", 50, LEFT%%\@ FLAG:调教UI手柄化 ? 手柄用 # 通常 \@, 30, RIGHT%
	;插件系统：插件管理入口
	PRINTFORML %"[10] 插件管理", 50, LEFT%
	DO
```

### 5.2 放宽输入校验范围

```eramicscript
		LOCAL:0 = !INRANGE(RESULT, 0, 10)								;範囲チェック
```

### 5.3 新增 CASE 分支（在 `CASE 7 TO 9` 之后）

```eramicscript
		CASE 7 TO 9
			CALLFORM CONFIG_%CONF_FUNC:(LOCAL:0 - 7)%
		CASE 10
			CALL PLUGIN_MANAGER
	ENDSELECT
```

---

## 验证安装

```bash
python tools/plugin_check.py "<游戏目录>/ERB/PLUGIN/**/*.ERB"
grep -rn "PLUGIN_HOOK" "<游戏目录>/ERB" --include="*.ERB"
```

应看到 5 处 `PLUGIN_HOOK` 调用（`ERB/PLUGIN/` 内除外）与 1 处 `PLUGIN_MANAGER`。
进游戏后：**商店菜单 → `[178]` 配置 → `[10]` 插件管理**。
