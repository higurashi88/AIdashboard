# 新規プロジェクトテンプレート

このディレクトリは `scripts/new-project.ps1` から展開する。`SETUP.md` 自体は展開先へコピーされない。
タスクの正本はダッシュボードなので、`Tasks.md` は作成しない。

## 展開

`<CODE>` はダッシュボード登録時に確定した code を指定する。code の自動生成は既存データとの
衝突判定を含むため、このスクリプトでは再実装しない。未登録なら先にダッシュボードで
プロジェクトを登録し、自動生成された code を確認する。

```powershell
.\scripts\new-project.ps1 `
    -Slug "<SLUG>" `
    -Name "<NAME>" `
    -Code "<CODE>" `
    -Path "C:\src\<SLUG>"
```

自動実行も使う場合は `-WithAutomation` を付ける。未指定の key は `<SLUG>-pipeline`、
Windows タスク名は slug から生成した半角名（例: `my-app` → `MyApp_Pipeline`）、予定は `未設定` になる。
`-TaskName` を指定する場合も半角英数字とアンダースコアのみを使う。

```powershell
.\scripts\new-project.ps1 `
    -Slug "<SLUG>" `
    -Name "<NAME>" `
    -Code "<CODE>" `
    -Path "C:\src\<SLUG>" `
    -WithAutomation `
    -Key "<KEY>" `
    -TaskName "<TASKNAME>" `
    -Schedule "<SCHEDULE>"
```

## 展開後

1. 標準出力の `[[project]]` と、必要なら `[[automation]]` を `config/projects.toml` へ手動で追記する。
2. `seed_initial_data --dry-run` で確認してから `seed_initial_data` を実行する。
3. `Overview.md` と `Current-Status.md` の案内文を実際の内容に更新する。
4. 自動実行を使う場合は `automation/pipeline_prompt.md` を具体化し、Windows タスクスケジューラへ登録する。
5. `run_pipeline.ps1` には展開時点の `dashboard_client.ps1` の絶対パスが埋め込まれる。
   移動後のパスへ上書きするときだけ `-DashboardClientPath` または環境変数
   `DASHBOARD_CLIENT_PATH` を使う（優先順位は引数 → 環境変数 → 埋め込み値）。

自動実行が不要になったら `automation/` はディレクトリごと削除してよい。
