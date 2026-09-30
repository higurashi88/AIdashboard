# new-project.ps1
#
# templates/new-project/ を新規プロジェクトへ安全に展開する。
# このファイル自体を UTF-8 BOM 付きで保存し、Windows PowerShell 5.1 で日本語を正しく読む。

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Slug,
    [Parameter(Mandatory = $true)][string]$Name,
    [string]$Code = $null,
    [Parameter(Mandatory = $true)][string]$Path,
    [switch]$WithAutomation,
    [string]$Key = $null,
    [string]$TaskName = $null,
    [string]$Schedule = $null,
    [string]$Summary = $null
)

$ErrorActionPreference = "Stop"

function ConvertTo-TomlBasicString {
    param([AllowEmptyString()][string]$Value)

    $escaped = $Value.Replace('\', '\\').Replace('"', '\"')
    $escaped = $escaped.Replace("`r", '\r').Replace("`n", '\n').Replace("`t", '\t')
    return '"' + $escaped + '"'
}

function ConvertTo-ScheduledTaskName {
    param([Parameter(Mandatory = $true)][string]$ProjectSlug)

    $pascalParts = @(
        foreach ($part in ($ProjectSlug -split '[-_]+')) {
            if ($part.Length -eq 1) {
                $part.ToUpperInvariant()
            }
            else {
                $part.Substring(0, 1).ToUpperInvariant() + $part.Substring(1)
            }
        }
    )
    return ($pascalParts -join '') + '_Pipeline'
}

$Slug = $Slug.Trim()
$Name = $Name.Trim()
$Path = $Path.Trim()

if ($Slug -notmatch '^[a-z0-9]+(?:[-_][a-z0-9]+)*$' -or $Slug.Length -gt 64) {
    throw "-Slug は64文字以内の半角小文字・数字・ハイフン・アンダースコアで指定してください。"
}
if ([string]::IsNullOrWhiteSpace($Name)) {
    throw "-Name は空にできません。"
}
if ([string]::IsNullOrWhiteSpace($Path)) {
    throw "-Path は空にできません。"
}

# project_codes.py の code 生成は既存DBとの衝突判定を含むため、ここでは再実装しない。
# 未指定ならダッシュボード登録時に自動生成された code を確認して再実行してもらう。
if ([string]::IsNullOrWhiteSpace($Code)) {
    throw "-Code は必須です。先にダッシュボードでプロジェクトを登録し、自動生成された code を確認して指定してください。"
}
$Code = $Code.Trim().ToUpperInvariant()
if ($Code -notmatch '^[A-Z0-9]{1,12}$') {
    throw "-Code は12文字以内の半角英大文字と数字で指定してください。"
}

if ([string]::IsNullOrWhiteSpace($Key)) {
    $Key = "$Slug-pipeline"
}
if ([string]::IsNullOrWhiteSpace($TaskName)) {
    $TaskName = ConvertTo-ScheduledTaskName $Slug
}
else {
    $TaskName = $TaskName.Trim()
}
if ($TaskName -notmatch '^[A-Za-z0-9_]+$') {
    throw "-TaskName は半角英数字とアンダースコアのみで指定してください。"
}
if ([string]::IsNullOrWhiteSpace($Schedule)) {
    $Schedule = "未設定"
}
if ([string]::IsNullOrWhiteSpace($Summary)) {
    $Summary = "$Name の目的・方針は Overview.md を参照"
}

$destinationPath = [System.IO.Path]::GetFullPath($Path)
$templateRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\templates\new-project"))
$dashboardClientPath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'dashboard_client.ps1'))

if (-not (Test-Path -LiteralPath $templateRoot -PathType Container)) {
    throw "テンプレートが見つかりません: $templateRoot"
}
if (-not (Test-Path -LiteralPath $dashboardClientPath -PathType Leaf)) {
    throw "ダッシュボード連携ファイルが見つかりません: $dashboardClientPath"
}

# 既存のファイルを1つでも見つけた時点で、コピーやディレクトリ作成より前に中止する。
# 空ディレクトリだけなら利用できるが、既存ファイルは内容にかかわらず上書きしない。
if (Test-Path -LiteralPath $destinationPath) {
    $destinationItem = Get-Item -LiteralPath $destinationPath
    if (-not $destinationItem.PSIsContainer) {
        throw "展開先は既存ファイルです。上書きしません: $destinationPath"
    }
    $existingFile = Get-ChildItem -LiteralPath $destinationPath -File -Recurse -Force |
        Select-Object -First 1
    if ($null -ne $existingFile) {
        throw "展開先に既存ファイルがあります。上書きしません: $($existingFile.FullName)"
    }
}

$replacementValues = @{
    '<SLUG>' = $Slug
    '<NAME>' = $Name
    '<CODE>' = $Code
    '<KEY>' = $Key
    '<TASKNAME>' = $TaskName
    '<SCHEDULE>' = $Schedule
    '<DASHBOARD_CLIENT>' = $dashboardClientPath.Replace("'", "''")
}
$placeholderPattern = ([char]60) + '(?:SLUG|NAME|CODE|KEY|TASKNAME|SCHEDULE|DASHBOARD_CLIENT)' + ([char]62)

$renderedFiles = @()
$templateFiles = Get-ChildItem -LiteralPath $templateRoot -File -Recurse
foreach ($templateFile in $templateFiles) {
    $relativePath = $templateFile.FullName.Substring($templateRoot.Length).TrimStart('\', '/')
    if ($relativePath -ieq 'SETUP.md') {
        continue
    }
    if (-not $WithAutomation -and $relativePath -like 'automation\*') {
        continue
    }

    $content = [System.IO.File]::ReadAllText($templateFile.FullName)
    foreach ($placeholder in $replacementValues.Keys) {
        $content = $content.Replace($placeholder, [string]$replacementValues[$placeholder])
    }
    if ($content -match $placeholderPattern) {
        throw "プレースホルダの置換に失敗しました: $relativePath ($($Matches[0]))"
    }

    $renderedFiles += [PSCustomObject]@{
        RelativePath = $relativePath
        Content = $content
    }
}

if (-not (Test-Path -LiteralPath $destinationPath)) {
    New-Item -ItemType Directory -Path $destinationPath -Force | Out-Null
}

# 生成物はすべて BOM 付き UTF-8 で書く。特に ps1 の BOM が落ちると PS 5.1 が
# 日本語を CP932 と誤認し、パイプライン関数が定義されない実障害につながる。
$utf8Bom = [System.Text.UTF8Encoding]::new($true)
foreach ($renderedFile in $renderedFiles) {
    $outputPath = Join-Path $destinationPath $renderedFile.RelativePath
    $outputDirectory = Split-Path -Parent $outputPath
    if (-not (Test-Path -LiteralPath $outputDirectory)) {
        New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
    }
    [System.IO.File]::WriteAllText($outputPath, $renderedFile.Content, $utf8Bom)
}

$tomlLines = @(
    '[[project]]',
    "slug = $(ConvertTo-TomlBasicString $Slug)",
    "code = $(ConvertTo-TomlBasicString $Code)",
    "name = $(ConvertTo-TomlBasicString $Name)",
    "root_path = $(ConvertTo-TomlBasicString $destinationPath)",
    "summary = $(ConvertTo-TomlBasicString $Summary)",
    'is_active = true'
)

if ($WithAutomation) {
    $pipelinePath = Join-Path $destinationPath 'automation\run_pipeline.ps1'
    $dashboardClientSuggestion = Join-Path $PSScriptRoot 'dashboard_client.ps1'
    $tomlLines += @(
        '',
        '[[automation]]',
        "key = $(ConvertTo-TomlBasicString $Key)",
        "project = $(ConvertTo-TomlBasicString $Slug)",
        "name = $(ConvertTo-TomlBasicString "$Name パイプライン")",
        "scheduled_task_name = $(ConvertTo-TomlBasicString $TaskName)",
        "schedule_human = $(ConvertTo-TomlBasicString $Schedule)",
        "script_path = $(ConvertTo-TomlBasicString $pipelinePath)",
        'state = "paused"'
    )
}

Write-Output "展開しました: $destinationPath"
Write-Output ""
Write-Output "config/projects.toml に次を手動で追記してください（このスクリプトはファイルを変更していません）:"
Write-Output ""
$tomlLines | Write-Output
Write-Output ""
Write-Output "次の手順:"
Write-Output "1. 上の内容を config/projects.toml に追記する。"
Write-Output "2. docker compose -f compose.yaml exec api python manage.py seed_initial_data --dry-run"
Write-Output "3. docker compose -f compose.yaml exec api python manage.py seed_initial_data"
Write-Output "4. $destinationPath\Overview.md と Current-Status.md を具体化する。"
if ($WithAutomation) {
    Write-Output "5. automation/pipeline_prompt.md を具体化し、Windows タスクスケジューラへ '$TaskName'（$Schedule）を登録する。"
    Write-Output "   powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$pipelinePath`" -DashboardClientPath `"$dashboardClientSuggestion`""
    Write-Output "   登録・動作確認後、[[automation]] の state を active に更新して seed_initial_data を再実行する。"
}
