# collect_repo_status.ps1
#
# ダッシュボードに登録したローカル Git リポジトリの状態を集め、API へ送る。
# API（コンテナ）からはホストのファイルが見えないため、ホスト側で git を実行する。
#
# 読み取りだけで、リポジトリには何も書き込まない。
#   - git --no-optional-locks で index の自動更新もしない（作業中の git 操作とぶつからない）
#   - fetch もしない。behind（リモートより遅れている数）は、最後に fetch した時点の値になる
#
# 使い方:
#   .\scripts\collect_repo_status.ps1
#   定期実行は scripts\register-repo-status-task.ps1 で登録する（15分ごと）。
#
# 必要な環境変数（自動実行パイプラインと共通）:
#   DASHBOARD_API_KEY_PIPELINE  pipeline スコープのキー
#   DASHBOARD_URL               省略時 http://127.0.0.1:8770
#
# 注意: このファイルは UTF-8 BOM 付きで保存すること。
# Windows PowerShell 5.1 は BOM の無いファイルを CP932 として読み、日本語が壊れる。

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'dashboard_client.ps1')

$logDir = Join-Path $PSScriptRoot '..\automation\repo-status\logs'
if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
# 15分ごとに動くので、ログは直近1回分だけを上書きで残す。
$logFile = Join-Path $logDir 'last_run.log'
"=== started: $(Get-Date -Format o) ===" | Out-File -FilePath $logFile -Encoding utf8

function Write-CollectorLog {
    param([Parameter(Mandatory)][string]$Message)
    $Message | Out-File -FilePath $logFile -Append -Encoding utf8
    Write-Host $Message
}

function Invoke-Git {
    <#
        git を実行し、標準出力・標準エラーを UTF-8 として受け取る。
        PowerShell のパイプで受けると [Console]::OutputEncoding（タスクスケジューラ実行時は
        CP932）で復号され、日本語のコミットメッセージが化ける（DASH-7 / DASH-20 と同種）。
    #>
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string[]]$Arguments
    )

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = 'git'
    $psi.Arguments = (@('--no-optional-locks', '-C', "`"$Path`"") + $Arguments) -join ' '
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8

    $process = [System.Diagnostics.Process]::Start($psi)
    # 片方ずつ読み切ると、もう片方のバッファが埋まったときに止まるため、stdout は非同期で読む。
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()

    return [pscustomobject]@{
        ExitCode = $process.ExitCode
        Out      = $stdoutTask.Result
        Err      = $stderr.Trim()
    }
}

function Get-RepositoryStatus {
    param([Parameter(Mandatory)][string]$Path)

    $item = [ordered]@{
        path                = $Path
        branch              = ''
        upstream            = ''
        ahead               = $null
        behind              = $null
        changed_files       = $null
        untracked_files     = $null
        last_commit_at      = $null
        last_commit_sha     = ''
        last_commit_subject = ''
        status_error        = ''
    }

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        $item.status_error = 'フォルダが見つかりません'
        return $item
    }

    try {
        $status = Invoke-Git -Path $Path -Arguments @('status', '--porcelain=v2', '--branch')
    }
    catch {
        $item.status_error = "git を実行できませんでした: $($_.Exception.Message)"
        return $item
    }
    if ($status.ExitCode -ne 0) {
        $item.status_error = if ($status.Err) { $status.Err } else { "git status が失敗しました (exit $($status.ExitCode))" }
        return $item
    }

    $changed = 0
    $untracked = 0
    foreach ($line in ($status.Out -split "`n")) {
        $line = $line.TrimEnd("`r")
        if ($line.StartsWith('# branch.head ')) {
            $item.branch = $line.Substring('# branch.head '.Length)
        }
        elseif ($line.StartsWith('# branch.upstream ')) {
            $item.upstream = $line.Substring('# branch.upstream '.Length)
        }
        elseif ($line -match '^# branch\.ab \+(\d+) -(\d+)$') {
            $item.ahead = [int]$Matches[1]
            $item.behind = [int]$Matches[2]
        }
        elseif ($line.StartsWith('? ')) {
            $untracked++
        }
        elseif ($line -match '^[12u] ') {
            $changed++
        }
    }
    $item.changed_files = $changed
    $item.untracked_files = $untracked

    # コミットがまだ無いリポジトリでは失敗するので、そのときは空のままにする。
    $log = Invoke-Git -Path $Path -Arguments @('log', '-1', '--format=%cI%x1f%H%x1f%s')
    if ($log.ExitCode -eq 0 -and $log.Out.Trim()) {
        $parts = $log.Out.Trim() -split [char]0x1f, 3
        if ($parts.Count -eq 3) {
            $item.last_commit_at = $parts[0]
            $item.last_commit_sha = $parts[1]
            $item.last_commit_subject = $parts[2]
        }
    }

    return $item
}

function Get-DashboardJson {
    <#
        GET して JSON を返す。応答は UTF-8 として明示的に復号する
        （PowerShell 5.1 は charset の無い応答を UTF-8 と見なさないことがあり、日本語のパスが壊れる）。
    #>
    param([Parameter(Mandatory)][string]$Path)

    $response = Invoke-WebRequest -UseBasicParsing -Method Get `
        -Uri "$(Get-DashboardUrl)$Path" `
        -Headers @{ Authorization = "Api-Key $(Get-DashboardApiKey)" } `
        -TimeoutSec 10
    $text = [System.Text.Encoding]::UTF8.GetString($response.RawContentStream.ToArray())
    # 5.1 の ConvertFrom-Json は配列を1個のオブジェクトとして返すので、要素に展開し直す。
    $parsed = $text | ConvertFrom-Json
    return ,@($parsed | ForEach-Object { $_ })
}

try {
    if ([string]::IsNullOrWhiteSpace((Get-DashboardApiKey))) {
        throw 'DASHBOARD_API_KEY_PIPELINE が未設定です（README「自動実行パイプラインとの連携」参照）'
    }

    $repositories = Get-DashboardJson -Path '/api/v1/repositories/'
    if ($repositories.Count -eq 0) {
        Write-CollectorLog '登録済みのリポジトリがありません（config/projects.toml の [[repository]] を確認）'
        exit 0
    }

    $items = @()
    foreach ($repository in $repositories) {
        $status = Get-RepositoryStatus -Path $repository.path
        $items += $status
        $summary = if ($status.status_error) {
            "ERROR $($status.status_error)"
        }
        else {
            "$($status.branch) 変更$($status.changed_files) 未追跡$($status.untracked_files) ahead=$($status.ahead) behind=$($status.behind)"
        }
        Write-CollectorLog "$($repository.name): $summary"
    }

    $result = Invoke-DashboardApi -Method Post -Path '/api/v1/repositories/status/' -Body @{ repositories = $items }
    if ($null -eq $result) {
        throw 'ダッシュボードへの送信に失敗しました（DASHBOARD_CLIENT_VERBOSE=1 で詳細を表示）'
    }
    Write-CollectorLog "送信しました: updated=$($result.updated)"
    "=== ended: $(Get-Date -Format o) ===" | Out-File -FilePath $logFile -Append -Encoding utf8
}
catch {
    try { Write-CollectorLog "ERROR: $($_.Exception.Message)" } catch { }
    exit 1
}
