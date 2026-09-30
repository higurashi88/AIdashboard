# backup.ps1
#
# PostgreSQL のダンプを取得し、世代管理する。
# タスクの正本は DB なので、Markdown 運用と違いバックアップは必須。
#
# 使い方:
#   .\scripts\backup.ps1
#   .\scripts\backup.ps1 -Keep 14 -OutDir "D:\backups\dashboard"
#
# 保持世代数は、-Keep を指定しなければダッシュボードの設定画面の値を使う
# （pipeline キーで読めなければ 7）。
#
# タスクスケジューラで日次実行することを推奨。

[CmdletBinding()]
param(
    # 保持する世代数。0（省略）なら設定画面の値
    [int]$Keep = 0,

    # 出力先。既定はリポジトリ直下の backups/
    [string]$OutDir = $null,

    # compose ファイル。開発モードで動かしているなら compose.override.yaml も効く
    [string]$ComposeFile = $null
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $OutDir = Join-Path $PSScriptRoot '..\backups'
}
if ([string]::IsNullOrWhiteSpace($ComposeFile)) {
    $ComposeFile = Join-Path $PSScriptRoot '..\compose.yaml'
}

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$OutDir = [System.IO.Path]::GetFullPath($OutDir)

if (-not (Test-Path $OutDir)) {
    New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
}

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$logDir = Join-Path $OutDir 'logs'
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$logFile = Join-Path $logDir "backup_$timestamp.log"
"=== backup started: $(Get-Date -Format o) ===" | Out-File -FilePath $logFile -Encoding utf8

function Write-BackupLog {
    param([Parameter(Mandatory)][string]$Message)

    $Message | Out-File -FilePath $logFile -Append -Encoding utf8
    Write-Host $Message
}

function Remove-OldBackupLogs {
    $logs = Get-ChildItem -Path $logDir -Filter 'backup_*.log' |
        Sort-Object LastWriteTime -Descending

    if ($logs.Count -gt $Keep) {
        $logs | Select-Object -Skip $Keep | ForEach-Object {
            Remove-Item $_.FullName -Force
        }
    }
}

# ダッシュボード連携の読み込み。失敗してもバックアップは止めない。
# $ErrorActionPreference = 'Stop' のため、未定義関数の呼び出しはスクリプト全体を
# 落とす。読み込めなかった場合は何もしない関数で代替する。
try { . (Join-Path $PSScriptRoot 'dashboard_client.ps1') } catch { }
if (-not (Get-Command Start-DashboardRun -ErrorAction SilentlyContinue)) {
    function Start-DashboardRun { param([string]$Key, [string]$LogPath, [string]$Trigger) }
    function Stop-DashboardRun  { param([string]$Status, [int]$ExitCode, [string]$Summary) }
}
Start-DashboardRun -Key 'dashboard-backup' -LogPath $logFile | Out-Null

# 保持世代数。-Keep を指定しなければ設定画面の値を使い、読めなければ 7 にする。
$keepSource = '引数'
if ($Keep -le 0) {
    $Keep = 7
    $keepSource = '既定値'
    if (Get-Command Get-DashboardSetting -ErrorAction SilentlyContinue) {
        $backupSetting = Get-DashboardSetting -Path '/api/v1/settings/backup/'
        if ($null -ne $backupSetting -and [int]$backupSetting.keep -ge 1) {
            $Keep = [int]$backupSetting.keep
            $keepSource = '設定画面'
        }
    }
}
Write-BackupLog "保持世代数: $Keep（$keepSource）"

try {

# .env から DB 名とユーザーを読む（compose と同じ値を使うため）
$envFile = Join-Path $projectRoot '.env'
if (-not (Test-Path $envFile)) {
    throw ".env が見つかりません: $envFile  （README のセットアップ手順1を実行してください）"
}

$envMap = @{}
foreach ($line in Get-Content $envFile) {
    if ($line -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)$') {
        $envMap[$Matches[1]] = $Matches[2].Trim()
    }
}
$dbName = if ($envMap.ContainsKey('POSTGRES_DB'))   { $envMap['POSTGRES_DB'] }   else { 'dashboard' }
$dbUser = if ($envMap.ContainsKey('POSTGRES_USER')) { $envMap['POSTGRES_USER'] } else { 'dashboard' }

$dumpPath  = Join-Path $OutDir "dashboard_$timestamp.sql"

Write-BackupLog "バックアップを開始します: $dumpPath"

# db コンテナが動いていることを確認する
$running = & docker compose -f $ComposeFile ps --status running --services 2>$null
if ($LASTEXITCODE -ne 0 -or $running -notcontains 'db') {
    throw "db コンテナが起動していません。先に docker compose -f compose.yaml up -d を実行してください。"
}

# pg_dump の出力を PowerShell のパイプに通してはいけない。パイプは出力を
# [Console]::OutputEncoding（タスクスケジューラ実行時は CP932）で文字列に復号するため、
# UTF-8 の日本語がすべて化ける（DASH-20）。コンテナ内のファイルへ書き出し、
# docker compose cp でバイト列のまま取り出す。
$containerDump = "/tmp/dashboard_$timestamp.sql"
try {
    & docker compose -f $ComposeFile exec -T db pg_dump -U $dbUser -d $dbName -f $containerDump
    if ($LASTEXITCODE -ne 0) {
        throw "pg_dump が失敗しました (exit $LASTEXITCODE)"
    }
    & docker compose -f $ComposeFile cp "db:$containerDump" $dumpPath
    if ($LASTEXITCODE -ne 0) {
        throw "ダンプをコンテナから取り出せませんでした (exit $LASTEXITCODE)"
    }
}
catch {
    if (Test-Path $dumpPath) { Remove-Item $dumpPath -Force }
    throw
}
finally {
    & docker compose -f $ComposeFile exec -T db rm -f $containerDump | Out-Null
}

$size = (Get-Item $dumpPath).Length
if ($size -eq 0) {
    Remove-Item $dumpPath -Force
    throw "ダンプが空でした。バックアップを中止します。"
}

# 圧縮する（.sql は消す）
$gzPath = "$dumpPath.gz"
try {
    $input  = [System.IO.File]::OpenRead($dumpPath)
    $output = [System.IO.File]::Create($gzPath)
    $gzip   = New-Object System.IO.Compression.GZipStream($output, [System.IO.Compression.CompressionLevel]::Optimal)
    $input.CopyTo($gzip)
}
finally {
    if ($gzip)   { $gzip.Dispose() }
    if ($output) { $output.Dispose() }
    if ($input)  { $input.Dispose() }
}
Remove-Item $dumpPath -Force

$gzSize = [math]::Round((Get-Item $gzPath).Length / 1KB, 1)
Write-BackupLog "完了: $gzPath ($gzSize KB)"

# 世代管理。新しいものから $Keep 件を残し、それより古いものを削除する。
$existing = Get-ChildItem -Path $OutDir -Filter 'dashboard_*.sql.gz' |
    Sort-Object LastWriteTime -Descending

if ($existing.Count -gt $Keep) {
    $obsolete = $existing | Select-Object -Skip $Keep
    foreach ($file in $obsolete) {
        Remove-Item $file.FullName -Force
        Write-BackupLog "古い世代を削除しました: $($file.Name)"
    }
}

Write-BackupLog "保持世代: $([math]::Min($existing.Count, $Keep)) / $Keep"

Remove-OldBackupLogs

$summary = "$([System.IO.Path]::GetFileName($gzPath)) ${gzSize}KB / ${Keep}世代"
"=== backup ended: $(Get-Date -Format o) ===" | Out-File -FilePath $logFile -Append -Encoding utf8
Stop-DashboardRun -Status 'succeeded' -Summary $summary
}
catch {
    $errorRecord = $_
    $errorMessage = $_.Exception.Message
    try {
        Write-BackupLog "ERROR: $errorMessage"
        "=== backup ended: $(Get-Date -Format o) ===" | Out-File -FilePath $logFile -Append -Encoding utf8
    }
    catch { }
    try { Remove-OldBackupLogs } catch { }
    Stop-DashboardRun -Status 'failed' -ExitCode 1 -Summary $errorMessage
    throw $errorRecord
}

# 復元手順は README の「バックアップ」を参照。
# ダンプは PowerShell のパイプに通さず、docker compose cp でコンテナへ渡して中で展開する。
