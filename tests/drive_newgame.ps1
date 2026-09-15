<#
.SYNOPSIS
  驱动 eratohoЯeverse 走到「新游戏」并验证插件钩子是否真的触发。

.DESCRIPTION
  Emuera 是 GUI 程序：@EVENTFIRST（BOOT 钩子所在）只有在标题画面选择
  [0] NEW GAME 后才会执行。本脚本：
    1. 启动游戏
    2. 用 SendKeys 向窗口发送按键序列（0 → Enter）选择新游戏
    3. 检查插件写出的证据文件（SAVETEXT）与 global.sav

  一定会强制结束进程，不会残留。

.PARAMETER Game        游戏目录
.PARAMETER Seconds     每步等待秒数
.PARAMETER Evidence    证据文件名（相对游戏目录），存在即判定钩子触发

.EXAMPLE
  powershell -File tests/drive_newgame.ps1 -Game "_testgame" -Evidence "SMOKETEST_BOOT_FIRED.txt"
#>
param(
    [Parameter(Mandatory = $true)][string]$Game,
    [int]$Seconds = 8,
    [string]$Evidence = "SMOKETEST_BOOT_FIRED.txt"
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms

if (-not (Test-Path (Join-Path $Game "ERB"))) { Write-Error "不是游戏目录：$Game"; exit 2 }
$exe = Get-ChildItem -Path $Game -Filter "Emuera*.exe" | Select-Object -First 1
if (-not $exe) { Write-Error "找不到 Emuera*.exe"; exit 2 }

$globalSav = Join-Path $Game "sav\global.sav"
$evPath = Join-Path $Game $Evidence
Remove-Item $globalSav -Force -ErrorAction SilentlyContinue
Remove-Item $evPath -Force -ErrorAction SilentlyContinue

Write-Output "=================================================="
Write-Output "游戏目录：$Game"
Write-Output "证据文件：$Evidence"
Write-Output "=================================================="

$proc = Start-Process -FilePath $exe.FullName -WorkingDirectory $Game -PassThru
Start-Sleep -Seconds $Seconds

if ($proc.HasExited) { Write-Output "游戏提前退出（exit=$($proc.ExitCode)）"; exit 1 }
$proc.Refresh()
Write-Output "窗口标题：$($proc.MainWindowTitle)"

# 让窗口获得焦点
try {
    [void][System.Windows.Forms.SendKeys]
    $wsh = New-Object -ComObject WScript.Shell
    $ok = $wsh.AppActivate($proc.Id)
    Write-Output "取得焦点：$ok"
    Start-Sleep -Seconds 1
    # 标题菜单 [0] NEW GAME
    [System.Windows.Forms.SendKeys]::SendWait("0")
    Start-Sleep -Milliseconds 800
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
    Start-Sleep -Seconds $Seconds
} catch {
    Write-Output "SendKeys 失败：$_"
}

$alive = -not $proc.HasExited
if ($alive) { $proc.Refresh() }
Write-Output "操作后存活：$alive"
Write-Output "操作后标题：$($proc.MainWindowTitle)"

$hasEv = Test-Path $evPath
$evLen = 0
if ($hasEv) { $evLen = (Get-Item $evPath).Length }

Get-Process -Name $exe.BaseName -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 1

Write-Output "--------------------------------------------------"
Write-Output ("证据文件存在：" + $hasEv + " (" + $evLen + " bytes)")
Write-Output ("global.sav 存在：" + (Test-Path $globalSav))
if ($hasEv) {
    Write-Output "内容："
    Get-Content $evPath -TotalCount 5 -ErrorAction SilentlyContinue | ForEach-Object { Write-Output ("  " + $_) }
}
Write-Output "--------------------------------------------------"

if ($hasEv) {
    Write-Output "结果：PASS —— 钩子链路真实触发（已走到新游戏并执行 BOOT 钩子）"
    exit 0
} else {
    Write-Output "结果：FAIL —— 未观察到钩子证据"
    exit 1
}
