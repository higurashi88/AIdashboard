# dashboard_client.ps1
#
# 自動実行パイプライン（run_*.ps1）からダッシュボードへ実行記録を送るための共通関数。
#
# 使い方（呼び出し側の ps1 に3行足すだけ）:
#
#   . "<このリポジトリのパス>\scripts\dashboard_client.ps1"
#   Start-DashboardRun -Key "blog-weekly-draft" -LogPath $logFile | Out-Null
#   try   { <既存の claude.exe 実行>; Stop-DashboardRun -Status "succeeded" }
#   catch { <既存のエラーログ>;      Stop-DashboardRun -Status "failed" -ExitCode 1 -Summary $_.Exception.Message }
#
# 設計上の絶対条件:
#   ダッシュボードが停止していても、パイプラインを絶対に止めない。
#   このファイルの関数はいかなる場合も例外を投げず、戻り値だけで成否を伝える。

# 注意: このファイルは既存パイプラインへドットソースされる。
# Set-StrictMode や $ErrorActionPreference を設定しないこと。
# ドットソースは呼び出し元スコープで実行されるため、読み込むだけで
# 呼び出し元の挙動を変えてしまう。
#
# 注意: このファイルは必ず UTF-8 BOM 付きで保存すること。
# Windows PowerShell 5.1 は BOM の無いファイルを ANSI（日本語環境では CP932）
# として読む。日本語コメントが化けた結果ブロックコメントの終端 #> が壊れ、
# Start-DashboardRun / Stop-DashboardRun がパースエラーも出さずに
# 「定義されないまま」になる。タスクスケジューラは powershell.exe（5.1）で
# 起動するため、BOM を落とすと自動実行の記録が静かに失われる。

$script:DashboardTimeout = 5
$script:RunKey           = $null

# 環境変数は「読み込み時」ではなく「呼び出し時」に解決する。
# 呼び出し側の ps1 がドットソースの後に $env:DASHBOARD_URL を設定しても効くようにするため。
function Get-DashboardUrl {
    if ($env:DASHBOARD_URL) { return $env:DASHBOARD_URL.TrimEnd('/') }
    return 'http://127.0.0.1:8770'
}

function Get-DashboardApiKey {
    return $env:DASHBOARD_API_KEY_PIPELINE
}

function Write-DashboardTrace {
    param([string]$Message)
    # パイプライン側のログへ紛れ込ませない。詳細が要るときだけ環境変数で有効化する。
    if ($env:DASHBOARD_CLIENT_VERBOSE -eq '1') {
        Write-Host "[dashboard] $Message"
    }
}

function Invoke-DashboardApi {
    <#
        戻り値: 成功なら応答オブジェクト、失敗なら $null。
        例外は握り潰す。ダッシュボードの不調でパイプラインを落とさないため。
    #>
    param(
        [Parameter(Mandatory)][ValidateSet('Post', 'Patch')][string]$Method,
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][hashtable]$Body
    )

    $apiKey = Get-DashboardApiKey
    if ([string]::IsNullOrWhiteSpace($apiKey)) {
        Write-DashboardTrace 'DASHBOARD_API_KEY_PIPELINE が未設定のため送信をスキップします'
        return $null
    }

    try {
        # PowerShell 5.1 の既定は UTF-16。明示的に UTF-8 バイト列へ変換して送る。
        $json  = $Body | ConvertTo-Json -Compress -Depth 6
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)

        $params = @{
            Method      = $Method
            Uri         = "$(Get-DashboardUrl)$Path"
            Headers     = @{ Authorization = "Api-Key $apiKey" }
            ContentType = 'application/json; charset=utf-8'
            Body        = $bytes
            TimeoutSec  = $script:DashboardTimeout
        }
        return Invoke-RestMethod @params
    }
    catch {
        Write-DashboardTrace "送信に失敗しました（無視して継続）: $($_.Exception.Message)"
        return $null
    }
}

function Get-DashboardSetting {
    <#
        .SYNOPSIS
        設定画面の値を GET で読む（例: /api/v1/settings/backup/）。

        戻り値: 成功なら応答オブジェクト、失敗なら $null。例外は投げない。
        呼び出し側は $null のとき自分の既定値を使うこと。
    #>
    param([Parameter(Mandatory)][string]$Path)

    $apiKey = Get-DashboardApiKey
    if ([string]::IsNullOrWhiteSpace($apiKey)) {
        Write-DashboardTrace 'DASHBOARD_API_KEY_PIPELINE が未設定のため設定を読めません'
        return $null
    }
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Method Get `
            -Uri "$(Get-DashboardUrl)$Path" `
            -Headers @{ Authorization = "Api-Key $apiKey" } `
            -TimeoutSec $script:DashboardTimeout
        # PowerShell 5.1 は charset の無い応答を UTF-8 と見なさないことがあるため明示的に復号する
        $text = [System.Text.Encoding]::UTF8.GetString($response.RawContentStream.ToArray())
        return $text | ConvertFrom-Json
    }
    catch {
        Write-DashboardTrace "設定を読めませんでした（既定値で継続）: $($_.Exception.Message)"
        return $null
    }
}

function Start-DashboardRun {
    <#
        .SYNOPSIS
        実行開始をダッシュボードへ登録し、run_key を返す。

        .PARAMETER Key
        Automation.key（例: blog-weekly-draft）。ダッシュボードに登録済みであること。

        .PARAMETER LogPath
        このパイプラインのログファイルパス。ダッシュボードから参照できるよう記録する。

        .PARAMETER Trigger
        scheduled（タスクスケジューラ起動）か manual（手動実行）。
    #>
    param(
        [Parameter(Mandatory)][string]$Key,
        [string]$LogPath = '',
        [ValidateSet('scheduled', 'manual')][string]$Trigger = 'scheduled'
    )

    $script:RunKey = "$Key-$(Get-Date -Format 'yyyyMMdd_HHmmss')"

    $body = @{
        run_key        = $script:RunKey
        automation_key = $Key
        status         = 'running'
        trigger        = $Trigger
        started_at     = (Get-Date).ToString('o')
        log_path       = $LogPath
    }

    $response = Invoke-DashboardApi -Method Post -Path '/api/v1/runs/' -Body $body
    if ($null -ne $response) {
        Write-DashboardTrace "実行開始を登録しました: $($script:RunKey)"
    }
    return $script:RunKey
}

function Stop-DashboardRun {
    <#
        .SYNOPSIS
        実行終了をダッシュボードへ登録する。Start-DashboardRun を呼んでいなければ何もしない。

        .PARAMETER Status
        succeeded か failed。

        .PARAMETER Summary
        実行結果の要約。パイプラインの出力から抽出した1行を渡すとダッシュボードに表示される。
    #>
    param(
        [Parameter(Mandatory)][ValidateSet('succeeded', 'failed')][string]$Status,
        [int]$ExitCode = 0,
        [string]$Summary = ''
    )

    if ([string]::IsNullOrWhiteSpace($script:RunKey)) {
        Write-DashboardTrace 'Start-DashboardRun が呼ばれていないため終了登録をスキップします'
        return
    }

    $body = @{
        status    = $Status
        exit_code = $ExitCode
        ended_at  = (Get-Date).ToString('o')
        summary   = $Summary
    }

    $response = Invoke-DashboardApi -Method Patch -Path "/api/v1/runs/$($script:RunKey)/" -Body $body
    if ($null -ne $response) {
        Write-DashboardTrace "実行終了を登録しました: $Status ($($response.duration_sec)秒)"
    }
    $script:RunKey = $null
}

function Get-DashboardRunSummary {
    <#
        .SYNOPSIS
        パイプラインの標準出力から `RESULT: ...` の行を抜き出して要約として返す。

        プロンプト側に「処理結果を RESULT: で1行出力する」と
        書いておくと、その1行がダッシュボードの実行履歴に表示される。
        該当行が無ければ空文字を返すだけで、エラーにはしない。
    #>
    param([Parameter(ValueFromPipeline)]$OutputLines)

    # パイプラインは1要素ずつ process を回すため、いったん集めてから end で1回だけ返す。
    # （process 内で return すると行数分の配列が返り、-Summary に渡せなくなる）
    begin { $collected = New-Object System.Collections.Generic.List[string] }

    process {
        foreach ($line in @($OutputLines)) {
            if ($null -ne $line) { $collected.Add([string]$line) }
        }
    }

    end {
        for ($i = $collected.Count - 1; $i -ge 0; $i--) {
            if ($collected[$i] -match '^\s*RESULT:\s*(.+?)\s*$') {
                return $Matches[1]
            }
        }
        return ''
    }
}
