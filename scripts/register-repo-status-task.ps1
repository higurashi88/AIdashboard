# register-repo-status-task.ps1
#
# collect_repo_status.ps1 を15分ごとに実行するタスクをタスクスケジューラへ登録する。
# 何度実行してもよい（同名のタスクは置き換える）。
#
# 使い方:
#   .\scripts\register-repo-status-task.ps1
#   .\scripts\register-repo-status-task.ps1 -IntervalMinutes 30
#   .\scripts\register-repo-status-task.ps1 -Unregister
#
# ログオン中のユーザーとして動かす（DASHBOARD_API_KEY_PIPELINE をユーザー環境変数から読むため）。
# 15分ごとにコンソールが一瞬開かないよう、conhost --headless 経由で起動する（Windows 11）。
#
# 注意: このファイルは UTF-8 BOM 付きで保存すること。

[CmdletBinding()]
param(
    [ValidateRange(5, 1440)]
    [int]$IntervalMinutes = 15,

    [string]$TaskName = 'PersonalDashboard_RepoStatus',

    [switch]$Unregister
)

$ErrorActionPreference = 'Stop'

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "削除しました: $TaskName"
    return
}

$script = (Resolve-Path (Join-Path $PSScriptRoot 'collect_repo_status.ps1')).Path
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$conhost = Join-Path $env:SystemRoot 'System32\conhost.exe'

$action = New-ScheduledTaskAction `
    -Execute $conhost `
    -Argument "--headless `"$powershell`" -NoProfile -ExecutionPolicy Bypass -File `"$script`""

$trigger = New-ScheduledTaskTrigger `
    -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)

$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Description 'AIdashboard: 登録したローカル Git リポジトリの状態をダッシュボードへ送る（読み取りのみ）' `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null

Write-Host "登録しました: $TaskName（$IntervalMinutes 分ごと）"
