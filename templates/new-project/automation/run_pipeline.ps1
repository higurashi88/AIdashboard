# <NAME> 無人パイプライン（<SCHEDULE>）
#
# このファイルは必ず UTF-8 BOM 付きで保存する。Windows PowerShell 5.1 は BOM 無しの
# UTF-8 を CP932 として読み、日本語コメントの文字化けでブロックコメントまで壊し得る。

[CmdletBinding()]
param(
    # PS 5.1 では param() の既定値評価時に $PSScriptRoot が空になることがある。
    # パスの既定値は $null にし、param() の後で安全に解決する。
    [string]$ProjectRoot = $null,
    [string]$PromptFile = $null,
    [string]$LogDir = $null,
    [string]$DashboardClientPath = $null,
    [string]$ClaudeExe = $null,
    [ValidateSet("scheduled", "manual")][string]$Trigger = "scheduled"
)

$ErrorActionPreference = "Stop"

# タスクスケジューラで引数を落としても実行記録が静かに消えないよう、展開時に
# dashboard_client.ps1 の絶対パスを埋め込む。引数、環境変数、埋め込み値の順に優先する。
$embeddedDashboardClientPath = '<DASHBOARD_CLIENT>'
if ([string]::IsNullOrWhiteSpace($DashboardClientPath)) {
    $DashboardClientPath = $env:DASHBOARD_CLIENT_PATH
}
if ([string]::IsNullOrWhiteSpace($DashboardClientPath)) {
    $DashboardClientPath = $embeddedDashboardClientPath
}

# 連携ファイルの欠落・文字化け・構文エラーがあっても本体を止めないため、
# ドットソースを try/catch でガードし、未定義の関数だけを no-op で補う。
try {
    if ([string]::IsNullOrWhiteSpace($DashboardClientPath)) {
        throw "dashboard_client.ps1 のパスが未指定です。"
    }
    . $DashboardClientPath
}
catch { }

# $ErrorActionPreference = "Stop" では未定義関数がパイプライン全体を落とす。
# 連携を読み込めなかった場合も実処理を続けられるよう、何もしない関数で代替する。
if (-not (Get-Command Start-DashboardRun -ErrorAction SilentlyContinue)) {
    function Start-DashboardRun { param([string]$Key, [string]$LogPath, [string]$Trigger) }
}
if (-not (Get-Command Stop-DashboardRun -ErrorAction SilentlyContinue)) {
    function Stop-DashboardRun { param([string]$Status, [int]$ExitCode, [string]$Summary) }
}
if (-not (Get-Command Get-DashboardRunSummary -ErrorAction SilentlyContinue)) {
    function Get-DashboardRunSummary {
        param([Parameter(ValueFromPipeline)]$OutputLines)
        end { "" }
    }
}

$logFile = $null
$locationPushed = $false

# セットアップから終了記録までを同じ try/catch で囲む。成功・失敗のどちらでも
# Stop-DashboardRun を呼び、失敗時はタスクスケジューラへ非ゼロ終了を返す。
try {
    if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
        $ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
    }
    if ([string]::IsNullOrWhiteSpace($PromptFile)) {
        $PromptFile = Join-Path $PSScriptRoot "pipeline_prompt.md"
    }
    if ([string]::IsNullOrWhiteSpace($LogDir)) {
        $LogDir = Join-Path $PSScriptRoot "logs"
    }
    if ([string]::IsNullOrWhiteSpace($ClaudeExe)) {
        $ClaudeExe = "claude.exe"
    }

    if (-not (Test-Path -LiteralPath $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    }

    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $logFile = Join-Path $LogDir "<SLUG>_pipeline_$timestamp.log"

    # 実行の標準出力を automation/logs/ に残し、その同じ絶対パスを渡すことで、
    # 後からダッシュボードの Run と実ログを対応付けられるようにする。
    "=== <NAME> pipeline run started: $(Get-Date -Format o) ===" |
        Out-File -FilePath $logFile -Encoding utf8
    Start-DashboardRun -Key "<KEY>" -LogPath $logFile -Trigger $Trigger | Out-Null

    Push-Location $ProjectRoot
    $locationPushed = $true

    $promptText = Get-Content -LiteralPath $PromptFile -Raw -Encoding UTF8

    # MCP サーバーを登録しただけでは無人実行からツールを呼べないため、
    # dashboard のタスク管理5ツールを --allowedTools に明示する。
    $allowedTools = "Bash,Read,Edit,Write,Glob,Grep,"
    $allowedTools += "mcp__dashboard__get_project,mcp__dashboard__list_tasks,"
    $allowedTools += "mcp__dashboard__create_task,mcp__dashboard__update_task,"
    $allowedTools += "mcp__dashboard__report_session"

    $claudeArguments = @(
        "-p",
        "--permission-mode", "acceptEdits",
        "--allowedTools", $allowedTools,
        "--output-format", "text",
        "--no-session-persistence"
    )

    # PS 5.1 の既定の $OutputEncoding は ASCII で、日本語をパイプすると ? に潰れる。
    # claude.exe へ渡す直前に BOM 無し UTF-8 を指定し、プロンプト本文を保持する。
    $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $output = @($promptText | & $ClaudeExe @claudeArguments 2>&1)
    $claudeExitCode = $LASTEXITCODE

    $output | Out-File -FilePath $logFile -Append -Encoding utf8
    if ($null -ne $claudeExitCode -and $claudeExitCode -ne 0) {
        throw "claude.exe が終了コード $claudeExitCode で失敗しました。"
    }

    $summary = $output | Get-DashboardRunSummary
    "=== <NAME> pipeline run ended: $(Get-Date -Format o) ===" |
        Out-File -FilePath $logFile -Append -Encoding utf8

    Pop-Location
    $locationPushed = $false

    Stop-DashboardRun -Status "succeeded" -ExitCode 0 -Summary $summary
    $output
}
catch {
    $errorRecord = $_
    $errorMessage = $_.Exception.Message

    if ($locationPushed) {
        try { Pop-Location } catch { }
    }
    if (-not [string]::IsNullOrWhiteSpace($logFile)) {
        try {
            "ERROR: $errorMessage" | Out-File -FilePath $logFile -Append -Encoding utf8
            "=== <NAME> pipeline run ended: $(Get-Date -Format o) ===" |
                Out-File -FilePath $logFile -Append -Encoding utf8
        }
        catch { }
    }

    try {
        Stop-DashboardRun -Status "failed" -ExitCode 1 -Summary $errorMessage
    }
    catch { }

    [Console]::Error.WriteLine("ERROR: $errorMessage")
    exit 1
}
