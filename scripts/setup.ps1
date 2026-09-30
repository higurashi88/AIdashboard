# setup.ps1
#
# 初回セットアップを一通り行う。何度実行してもよい（済んでいる手順は飛ばす）。
#
#   1. Docker が使えるか確認する
#   2. .env が無ければ .env.example から作り、パスワードと秘密鍵をランダムに生成する
#   3. コンテナをビルドして起動し、正常になるまで待つ
#   4. 画面用（web スコープ）の API キーを発行して .env に書き、proxy を作り直す
#   5. 画面と API に届くか確認する
#
# 使い方（リポジトリ直下で）:
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -Port 8780   # 8770 が使用中のとき
#
# 注意: このファイルは UTF-8 BOM 付きで保存すること。
# Windows PowerShell 5.1 は BOM の無いファイルを CP932 として読み、日本語が壊れる。

[CmdletBinding()]
param(
    # ブラウザで開くポート（127.0.0.1 のみで待ち受ける）。.env を新しく作るときだけ使う。
    [ValidateRange(1024, 65535)][int]$Port = 8770
)

$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$composeFile = Join-Path $root 'compose.yaml'
$envFile = Join-Path $root '.env'
$exampleFile = Join-Path $root '.env.example'
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Step {
    param([string]$Message)
    Write-Host ''
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function New-RandomString {
    # 英数字だけにする（DATABASE_URL に入れても URL エンコードが要らない）
    param([int]$Length)
    $alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    $bytes = New-Object byte[] ($Length * 2)
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $chars = foreach ($byte in $bytes) {
        # 248 以上は捨てて偏りを無くす（248 = 62 * 4）
        if ($byte -lt 248) { $alphabet[$byte % 62] }
    }
    return (-join $chars).Substring(0, $Length)
}

function Read-EnvValue {
    param([string]$Name)
    foreach ($line in [System.IO.File]::ReadAllLines($envFile, $utf8NoBom)) {
        if ($line -match "^\s*$Name\s*=\s*(.*)$") { return $Matches[1].Trim() }
    }
    return $null
}

function Set-EnvValue {
    param([string]$Name, [string]$Value)
    $text = [System.IO.File]::ReadAllText($envFile, $utf8NoBom)
    $pattern = "(?m)^$Name=.*$"
    if ($text -match $pattern) {
        $text = [regex]::Replace($text, $pattern, "$Name=$Value")
    }
    else {
        $text = $text.TrimEnd() + "`n$Name=$Value`n"
    }
    [System.IO.File]::WriteAllText($envFile, $text, $utf8NoBom)
}

function Invoke-Compose {
    # docker compose の進行表示は stderr に出る。リダイレクトすると 5.1 がエラー扱いするため、そのまま流す。
    & docker compose -f $composeFile @args
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose $($args -join ' ') が失敗しました (exit $LASTEXITCODE)"
    }
}

Push-Location $root
try {
    Write-Step 'Docker を確認します'
    & docker version --format '{{.Server.Version}}' | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker に接続できません。Docker Desktop を起動してから、もう一度実行してください。'
    }
    & docker compose version | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'docker compose が見つかりません。Docker Desktop を最新にしてください。'
    }
    Write-Host 'OK'

    Write-Step '.env を用意します'
    if (Test-Path -LiteralPath $envFile) {
        # DB は初回起動時のパスワードで初期化済みなので、.env は作り直さない
        Write-Host '既存の .env を使います'
    }
    else {
        $text = [System.IO.File]::ReadAllText($exampleFile, $utf8NoBom)
        $dbPassword = New-RandomString 32
        $secretKey = New-RandomString 64
        $text = [regex]::Replace($text, '(?m)^POSTGRES_PASSWORD=.*$', "POSTGRES_PASSWORD=$dbPassword")
        $text = [regex]::Replace($text, '(?m)^DATABASE_URL=.*$', "DATABASE_URL=postgresql://dashboard:$dbPassword@db:5432/dashboard")
        $text = [regex]::Replace($text, '(?m)^DJANGO_SECRET_KEY=.*$', "DJANGO_SECRET_KEY=$secretKey")
        if ($Port -ne 8770) {
            $text = $text.Replace('8770', "$Port")
        }
        [System.IO.File]::WriteAllText($envFile, $text, $utf8NoBom)
        Write-Host ".env を作りました（DB パスワードと DJANGO_SECRET_KEY は自動生成、ポート $Port）"
    }
    $configuredPort = Read-EnvValue 'DASHBOARD_PORT'
    if ([string]::IsNullOrWhiteSpace($configuredPort)) { $configuredPort = '8770' }
    $baseUrl = "http://127.0.0.1:$configuredPort"

    Write-Step 'コンテナをビルドして起動します（初回は数分かかります）'
    Invoke-Compose up -d --build --wait

    Write-Step '画面用の API キーを確認します'
    $webKey = Read-EnvValue 'DASHBOARD_WEB_API_KEY'
    if ([string]::IsNullOrWhiteSpace($webKey) -or $webKey -eq 'change_me') {
        $output = & docker compose -f $composeFile exec -T api python manage.py create_api_key --name web-ui --scope web
        if ($LASTEXITCODE -ne 0) { throw 'API キーを発行できませんでした' }
        $webKey = (@($output) | Where-Object { $_ -match '^pdb_' } | Select-Object -Last 1)
        if (-not $webKey) { throw "API キーの出力を読み取れませんでした: $output" }
        Set-EnvValue 'DASHBOARD_WEB_API_KEY' $webKey.Trim()
        Write-Host '発行して .env に書きました。proxy を作り直します'
        Invoke-Compose up -d --force-recreate --no-deps --wait proxy
    }
    else {
        Write-Host '設定済みです'
    }

    Write-Step '動作を確認します'
    $response = Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/api/v1/dashboard/summary/" -TimeoutSec 15
    if ($response.StatusCode -ne 200) { throw "API が $($response.StatusCode) を返しました" }
    $page = Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/" -TimeoutSec 15
    if ($page.StatusCode -ne 200) { throw "画面が $($page.StatusCode) を返しました" }
    Write-Host 'OK'

    Write-Host ''
    Write-Host 'セットアップが終わりました。' -ForegroundColor Green
    Write-Host "  画面: $baseUrl"
    Write-Host ''
    Write-Host '次にやること（詳しくは docs/setup.md）:'
    Write-Host '  1. 画面の「PJ管理」でプロジェクトを登録する'
    Write-Host '  2. 「設定 → APIキー」で MCP 用のキーを発行し、表示された claude mcp add を実行する'
    Write-Host '  3. docs/agent-instructions.md の内容を ~/.claude/CLAUDE.md に追記する'
}
catch {
    Write-Host ''
    Write-Host "エラー: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'docs/setup.md の「うまくいかないとき」を確認してください。'
    exit 1
}
finally {
    Pop-Location
}
