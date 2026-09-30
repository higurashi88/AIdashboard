# 初回セットアップ手順

Windows の PC に AIdashboard を入れて、Claude Code からタスクを読み書きできるようになるまでの手順です。
所要時間は15分ほど（うち半分はコンテナのビルド待ち）。

各手順の背景や、手作業で1つずつ行う方法は [README](../README.md) の「セットアップ」を参照してください。

---

## 0. できあがる構成

```
ブラウザ ─┐
Claude Code (MCP) ─┼─▶ proxy (nginx, 127.0.0.1:8770) ─▶ api (Django) ─▶ db (PostgreSQL)
自動実行スクリプト ─┘                                └▶ web (React)
                                               discord-bot（任意）─▶ Discord
```

- すべて Docker のコンテナで動きます。ホストに Python や PostgreSQL は要りません
- 待ち受けるのは `127.0.0.1` だけで、同じ LAN の他の端末からも見えません（1台の PC で本人だけが使う前提）
- タスクの正本は PostgreSQL です。ファイルとしては残らないので、手順 6-1 のバックアップを設定してください

---

## 1. 必要なもの

| もの | 用途 | 入手先 |
|------|------|--------|
| Windows 10 / 11 | 動作環境（スクリプトは標準の Windows PowerShell 5.1 で動きます） | — |
| Docker Desktop | コンテナの実行 | <https://www.docker.com/products/docker-desktop/> |
| Git | リポジトリの取得 | <https://git-scm.com/download/win> |
| Claude Code（推奨） | MCP でタスクを読み書きするエージェント | <https://docs.anthropic.com/en/docs/claude-code/overview> |

Docker Desktop はインストール後に一度起動し、画面左下が「Engine running」になっていることを確認します。

---

## 2. リポジトリを取得する

置き場所は自由です。以下は `C:\src` に置く例です。

```powershell
cd C:\src
git clone https://github.com/higurashi88/AIdashboard.git
cd AIdashboard
```

---

## 3. セットアップスクリプトを実行する

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

スクリプトは次を順に行います。**何度実行しても大丈夫です**（済んでいる手順は飛ばします）。

1. Docker が使えるか確認する
2. `.env` を作り、DB のパスワードと `DJANGO_SECRET_KEY` をランダムに生成する
3. コンテナをビルドして起動し、正常になるまで待つ（初回は数分）
4. 画面用の API キーを発行して `.env` に書き、proxy を作り直す
5. 画面と API に届くか確認する

最後に次のように出れば成功です。

```
セットアップが終わりました。
  画面: http://127.0.0.1:8770
```

> **8770 番ポートを別のアプリが使っている場合**は、`-Port 8780` のように別の番号を付けて実行します。
> 以降の手順の `8770` は、その番号に読み替えてください。
>
> **`.env` は作り直さないでください。** DB はコンテナの初回起動時のパスワードで初期化されるため、
> `.env` を消して作り直すとパスワードが合わなくなります（README の「トラブルシューティング」参照）。
> `.env` には秘密の値が入るので、共有やコミットもしないでください（`.gitignore` 済み）。

---

## 4. プロジェクトを登録する

ブラウザで <http://127.0.0.1:8770> を開き、上部の「PJ管理」→「新規PJ」から登録します。

| 項目 | 入れるもの |
|------|-----------|
| 名前 | 画面に出る名前（日本語可） |
| ルートパス | そのプロジェクトの作業フォルダの絶対パス（例 `C:\src\my-app`） |

**ルートパスが大事です。** Claude Code がそのフォルダ（とその配下）で作業しているとき、
`get_project(cwd=...)` がこのパスの前方一致でプロジェクトを判定します。

識別子（slug と code）は自動で決まります。code はタスクの番号の頭（`APP-12` の `APP`）になり、登録後は変えられません。

> たくさんのプロジェクトを一度に登録したいときは、`config/projects.toml` に書いて取り込むこともできます（README 手順3）。

---

## 5. Claude Code から使えるようにする

### 5-1. MCP 用の API キーを発行して登録する

1. 画面の「設定」→「APIキー」で、名前に「Claude Code」など、用途に「MCP（Claude Code など）」を選んで「発行」
2. 表示された `claude mcp add ...` のコマンドをコピーして、PowerShell で実行する
   （キーはこのときしか表示されません。閉じる前に実行してください）
3. 登録できたか確認する

```powershell
claude mcp list
# dashboard: http://127.0.0.1:8770/mcp (HTTP) - ✓ Connected
```

`--scope user` で登録するので、どのフォルダで Claude Code を起動しても使えます。

### 5-2. 使い方を Claude Code に教える

MCP を登録しただけでは、Claude Code はダッシュボードのツールを使いません。
[docs/agent-instructions.md](agent-instructions.md) の ① のコードブロックの中身を、
`%USERPROFILE%\.claude\CLAUDE.md`（無ければ作る）の末尾に貼り付けます。

### 5-3. 動作確認

手順4で登録したフォルダで Claude Code を起動し、次のように頼みます。

```
このプロジェクトの未処理タスクを見せて
```

`get_project` が呼ばれ、登録したプロジェクトの情報が返れば完了です。
何か作業を頼むとタスクが登録され、画面のホームに表示されます。

---

## 6. 必要に応じて設定するもの

### 6-1. 毎日のバックアップ（強く推奨）

タスクは DB にしか無いので、毎日ダンプを取ります。`backups\` にダンプが溜まり、古いものは自動で消えます
（残す世代数は「設定 → バックアップ」で変更、既定 7）。

```powershell
# リポジトリ直下で実行する。毎日 22:30 に backup.ps1 を動かす
$repo = (Get-Location).Path
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$repo\scripts\backup.ps1`"" -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Daily -At 22:30
Register-ScheduledTask -TaskName 'AIdashboard Backup' -Action $action -Trigger $trigger `
    -Description 'AIdashboard の DB を毎日バックアップする'

# すぐに1回動かして確かめる
.\scripts\backup.ps1
```

復元のしかたは README の「バックアップ」を参照してください。

### 6-2. ホストのスクリプトからの記録（自動実行・リポジトリ状態・バックアップの世代数）

自動実行パイプラインの実行結果の記録、リポジトリ状態の収集、バックアップの世代数の読み取りは、
`pipeline` 用の API キーを Windows のユーザー環境変数から読みます。

1. 「設定 → APIキー」で用途「パイプライン（ホストのスクリプト）」のキーを発行する
2. 表示されたコマンドを PowerShell で実行する

```powershell
[Environment]::SetEnvironmentVariable('DASHBOARD_API_KEY_PIPELINE', '<キー>', 'User')
# ポートを 8770 から変えた場合だけ
[Environment]::SetEnvironmentVariable('DASHBOARD_URL', 'http://127.0.0.1:8780', 'User')
```

ユーザー環境変数は、設定した後に開いた PowerShell やタスクスケジューラの実行から見えます。

- 自動実行パイプラインに記録を足す方法 → README「自動実行パイプラインとの連携」
- ローカル Git リポジトリの状態をホームに出す → 「設定 → 監視するリポジトリ」で登録し、
  `.\scripts\register-repo-status-task.ps1` で15分ごとの収集を登録する（README「ローカルリポジトリの状態を集める」）

### 6-3. Discord への通知

判断待ち・自動実行の失敗・朝のまとめを Discord に投稿します。
Discord 側の bot の作成から、設定画面での入力、テスト送信までの手順は
**[docs/discord-setup.md](discord-setup.md)** にまとめてあります。

### 6-4. Django Admin（保守用、任意）

データを直接直したいときのための管理画面です。普段は使いません。

```powershell
docker compose -f compose.yaml exec api python manage.py createsuperuser
```

<http://127.0.0.1:8770/admin/> から、作ったユーザーでログインします。

---

## 7. 普段の操作

| やりたいこと | コマンド（リポジトリ直下で） |
|--------------|------------------------------|
| 止める（データは残る） | `docker compose -f compose.yaml stop` |
| 再開する | `docker compose -f compose.yaml start` |
| 新しい版に更新する | `git pull` のあと `docker compose -f compose.yaml up -d --build`、続けて `docker compose -f compose.yaml restart proxy` |
| ログを見る | `docker compose -f compose.yaml logs -f api` |

PC を再起動しても、Docker Desktop が起動すればコンテナは自動で戻ります。
DB の構造の変更（マイグレーション）は、更新後の起動時に自動で適用されます。

**`docker compose down -v` は実行しないでください。** `-v` は DB のボリュームごと消し、全タスクが失われます。

---

## 8. うまくいかないとき

| 症状 | 対処 |
|------|------|
| `Docker に接続できません` | Docker Desktop を起動し、「Engine running」になってから再実行する |
| `bind: ... forbidden by its access permissions` / ポートが使用中 | 別のポートで入れ直す。`.env` がまだ無ければ `setup.ps1 -Port 8780`。既に作ってあれば `.env` の `8770` をすべて新しい番号に書き換えて `setup.ps1` を再実行 |
| スクリプトが途中で止まった | 原因を直してから `setup.ps1` をもう一度実行する（済んだ手順は飛ばす） |
| `password authentication failed` | `.env` を作り直したため DB のパスワードが合っていない。まだデータが無いなら `docker compose -f compose.yaml down -v` で DB を消してから `setup.ps1` を再実行（**データがあるなら実行しない**。README のトラブルシューティング参照） |
| 更新後に画面が `502 Bad Gateway` | `docker compose -f compose.yaml restart proxy` |
| `claude mcp list` で接続できない | 画面が開けるか確認し、キーを発行し直して `claude mcp remove dashboard -s user` → `claude mcp add ...` をやり直す |
| Claude Code がツールを呼ばない | 手順 5-2 の CLAUDE.md への追記と、手順4のルートパスを確認する |

それでも解決しない場合は、`docker compose -f compose.yaml ps` と
`docker compose -f compose.yaml logs --tail 100 api` の出力を添えて Issue を立ててください
（**ログに含まれる絶対パスや API キーは伏せてください**）。
