<#
.SYNOPSIS
  启动 eratohoЯeverse 做冒烟测试：确认游戏能在装了插件的前提下正常启动。

.DESCRIPTION
  Emuera 是 GUI 程序，无法直接读 stdout。本脚本用「启动 → 观察窗口标题/响应性 →
  检查 sav/global.sav 是否被写出」来判定启动是否成功：
  global.sav 由 @EVENTFIRST 里的 SAVEGLOBAL 写出，能写出即说明主流程（含插件钩子）
  已完整执行一轮、没有编译错误或运行时中断。

  一定会强制结束进程，不会残留。

.PARAMETER Game
  游戏目录（含 Emuera*.exe 与 ERB/）

.PARAMETER Seconds
  启动后等待秒数，默认 10

.EXAMPLE
  powershell -File tests/smoke_test.ps1 -Game "D:/.../eratohoЯeverse-1.214-CNTESTv0.219"
#>
param(
    [Parameter(Mandatory = $true)][string]$Game,
    [int]$Seconds = 10,
    [switch]$KeepSave
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path (Join-Path $Game "ERB"))) {
    Write-Error "不是游戏目录（找不到 ERB/）：$Game"
    exit 2
}

$exe = Get-ChildItem -Path $Game -Filter "Emuera*.exe" | Select-Object -First 1
if (-not $exe) {
    Write-Error "找不到 Emuera*.exe：$Game"
    exit 2
}

$sav = Join-Path $Game "sav"
$globalSav = Join-Path $sav "global.sav"

Write-Output "=================================================="
Write-Output "游戏目录：$Game"
Write-Output "可执行  ：$($exe.Name)"
Write-Output "=================================================="

# 判断是否装了插件
$hasPlugin = Test-Path (Join-Path $Game "ERB/PLUGIN/PLUGIN_MANAGER.ERB")
Write-Output ("插件系统：" + $(if ($hasPlugin) { "已安装" } else { "未安装" }))

# 清掉旧的 global.sav，确保观察到的是本次启动写出的
if (Test-Path $globalSav) {
    Remove-Item $globalSav -Force
    Write-Output "已清除旧的 global.sav"
}

Write-Output "启动中（等待 $Seconds 秒）..."
$proc = Start-Process -FilePath $exe.FullName -WorkingDirectory $Game -PassThru
Start-Sleep -Seconds $Seconds

$result = [ordered]@{
    Pid        = $proc.Id
    Alive      = -not $proc.HasExited
    Title      = $null
    Responding = $null
    GlobalSav  = $false
    SavBytes   = 0
}

if ($result.Alive) {
    $proc.Refresh()
    $result.Title = $proc.MainWindowTitle
    $result.Responding = $proc.Responding
}

if (Test-Path $globalSav) {
    $result.GlobalSav = $true
    $result.SavBytes = (Get-Item $globalSav).Length
}

# 强制结束（含可能的子进程）
Get-Process -Name $exe.BaseName -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 1

Write-Output "--------------------------------------------------"
Write-Output ("进程存活  ：" + $result.Alive)
Write-Output ("窗口标题  ：" + $result.Title)
Write-Output ("界面响应  ：" + $result.Responding)
Write-Output ("global.sav：" + $result.GlobalSav + " (" + $result.SavBytes + " bytes)")
Write-Output "--------------------------------------------------"

$pass = $result.Alive -and $result.GlobalSav
if ($pass) {
    Write-Output "结果：PASS —— 游戏正常启动，主流程执行完毕（含插件钩子）"
    exit 0
} else {
    Write-Output "结果：FAIL —— 游戏未能正常启动或无窗口"
    exit 1
}
