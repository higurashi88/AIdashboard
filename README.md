# AIdashboard

複数プロジェクトのタスク状況を1画面に集約する、個人用のダッシュボード。
Claude Code / Codex のセッションが MCP 経由でタスクを直接更新し、自動実行パイプラインが実行結果を記録する。

タスクの正本は PostgreSQL に置き、Markdown ファイルでの管理を置き換える。
エージェントの運用を変えずに導入できるよう、書き込みは MCP ツール経由で行う。

## 現在の実装状況

| 機能 | 状態 |
|------|------|
| PostgreSQL のデータモデル（Project / Task / TaskEvent / Session / Automation / Run） | 実装済み |
| REST API（タスクCRUD、ダッシュボード集約、実行記録、OpenAPI） | 実装済み |
| MCP サーバー（6ツール） | 実装済み |
| Django Admin | 実装済み |
| 自動実行パイプライン連携（PowerShell） | 実装済み |
| React UI（ホーム、タスク管理、PJ管理、設定） | 実装済み |
| Discord 通知（判断待ち・自動実行の失敗・朝のまとめ） | 実装済み（任意） |
| ローカル Git リポジトリの状態一覧（ホームの「リポジトリ」欄） | 実装済み（任意） |

人間は React UI からタスクの作成・閲覧・更新・削除と、プロジェクトの登録・編集・
アーカイブを行える。「設定」画面では Discord bot の接続先と通知の ON/OFF、監視する
リポジトリ、API キー、バックアップの保持世代数を変更できる。Django Admin は保守用として引き続き利用できる。

---

## 必要なもの

- Docker Desktop for Windows
- Git
- Claude Code（MCP クライアントとして）

ホスト側に Python や PostgreSQL は不要。すべてコンテナ内で動く。

---

## セットアップ

**初めての場合は [docs/setup.md](docs/setup.md) の手順書に沿って進めるのが早い。**
`scripts/setup.ps1` が `.env` の生成（パスワードと秘密鍵の自動生成）・起動・画面用 API キーの発行までを行う。

```powershell
git clone https://github.com/higurashi88/AIdashboard.git
cd AIdashboard
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

以下は、同じことを手作業で1つずつ行う場合の詳細。

### 1. `.env` を作る

```powershell
Copy-Item .env.example .env
```

`.env` を開き、**最低限この2つ**を変更する。どちらも自分で決める値で、どこかから発行されるものではない。

| 変数 | 値 |
|------|-----|
| `DJANGO_SECRET_KEY` | 十分に長いランダム文字列。未設定だと `DJANGO_DEBUG=False` では起動しない |
| `POSTGRES_PASSWORD` | 任意のパスワード。`DATABASE_URL` の中のパスワードも同じ値に揃える |

#### ランダム値の生成

```powershell
# SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(64))"

# POSTGRES_PASSWORD（記号なし。DATABASE_URL に埋めるため）
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

Python が無ければ `openssl rand -hex 32`（Git Bash に同梱）でもよい。
`openssl rand -base64` は `/` `+` を含むため、**`DATABASE_URL` に埋めるパスワードには使わない**
（URLの区切りと衝突する）。

起動後であれば、Django 標準のユーティリティも使える。SECRET_KEY のローテーション時はこちらが定番。

```powershell
docker compose -f compose.yaml exec api python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

> 初回はまだコンテナが起動できないため（SECRET_KEY 未設定では起動しない）、上の Python か openssl を使う。

#### パスワードは2箇所

```dotenv
POSTGRES_PASSWORD=<生成したパスワード>
DATABASE_URL=postgresql://dashboard:<同じパスワード>@db:5432/dashboard
```

**片方だけ直すと `password authentication failed` になる。**

#### APIキーの置き場所

MCP と pipeline のキーは `.env` に書かない。`.env` は Docker Compose がコンテナへ
渡すものなので、ホストで動くクライアントからは見えない。web キーだけは nginx が
APIリクエストへ付与するため、手順5で `.env` の `DASHBOARD_WEB_API_KEY` に設定する。

- `mcp` → `claude mcp add` の `--header`
- `pipeline` → Windows のユーザー環境変数
- `web` → `.env` の `DASHBOARD_WEB_API_KEY`（ブラウザやwebイメージには渡らない）

### 2. 起動

```powershell
docker compose -f compose.yaml up -d --build
```

`db` → `api`、`web` → `proxy` の順に healthy になれば成功。初回は5分ほどかかる。

```powershell
docker compose -f compose.yaml ps
```

`api` の起動時に migrate と collectstatic が自動実行されるので、手動でのマイグレーションは不要。

### 3. 自分のプロジェクトを登録する

画面の「PJ管理 → 新規PJ」で、名前とルートパスを入れて登録するのが簡単。
自動実行（Automation）の定義も含めてまとめて登録したい場合は、次の設定ファイルを使う。

雛形をコピーして編集する。

```powershell
Copy-Item config\projects.example.toml config\projects.toml
```

`config/projects.toml` にプロジェクトと自動実行を書く。書き方はファイル内のコメントを参照。
**このファイルは `.gitignore` 済み**（ローカル固有の絶対パスを含むため）。

内容を確認してから投入する。

```powershell
docker compose -f compose.yaml exec api python manage.py seed_initial_data --dry-run
docker compose -f compose.yaml exec api python manage.py seed_initial_data
```

**冪等なので何度実行してもよい。** `slug` と `key` をキーに更新される。
プロジェクトを追加したくなったら、このファイルに追記して再実行するか、Django Admin から直接登録する。

### 4. 管理ユーザーを作る

```powershell
docker compose -f compose.yaml exec api python manage.py createsuperuser
```

**この手順を飛ばすと Django Admin にログインできない。**

### 5. API キーを発行する

用途ごとにスコープを分ける。**平文が表示されるのは発行時の一度だけ**なので控えておくこと。
最初の `web` キーはコマンドで発行する（画面を開くのに必要なため）。2本目以降は画面の
「設定 → APIキー」からも発行・無効化できる。

```powershell
docker compose -f compose.yaml exec api python manage.py create_api_key --name claude-code --scope mcp
docker compose -f compose.yaml exec api python manage.py create_api_key --name pipeline    --scope pipeline
docker compose -f compose.yaml exec api python manage.py create_api_key --name web         --scope web
```

| スコープ | 使えるもの |
|----------|-----------|
| `mcp` | MCP サーバー（`/mcp`）のみ |
| `pipeline` | `/api/v1/runs/`、リポジトリ状態の送信（`/api/v1/repositories/`）、バックアップの保持世代数の読み取り |
| `web` | 読み取りとタスク CRUD、ダッシュボード集約、設定画面（設定・APIキー・リポジトリの編集） |
| `discord` | ダッシュボード集約、`/api/v1/events/`、`GET /api/v1/runs/`、bot の設定の読み取り（`/api/v1/discord/config/`）と接続状態の報告のみ |

スコープが違うキーは 403 で拒否される。

`web` キーとして表示された平文を `.env` に設定し、nginxだけを再作成する。

```dotenv
DASHBOARD_WEB_API_KEY=<発行されたwebキー>
```

```powershell
docker compose -f compose.yaml up -d --force-recreate proxy
```

nginx はブラウザから `/api/` へ届いたリクエストにこのキーを付与する。キーはReactの
JavaScriptや静的ファイルには埋め込まれない。明示的な `Authorization` がある
pipelineクライアントのリクエストは上書きしない。

### 6. 動作確認

```powershell
curl http://127.0.0.1:8770/api/v1/healthz/
# {"status":"ok","database":"ok"}
```

ブラウザで開くもの:

| URL | 内容 |
|-----|------|
| <http://127.0.0.1:8770/> | React ダッシュボード |
| <http://127.0.0.1:8770/admin/> | Django Admin（手順4のユーザーでログイン） |
| <http://127.0.0.1:8770/api/schema/swagger-ui/> | API 仕様（認証不要） |

---

## 前提と安全な運用範囲

**このアプリは「1台のPCで、本人だけが使う」前提で作ってある。**

- `proxy` は `127.0.0.1` にのみバインドしており、同じLANの他端末からも見えない
- 認証はAPIキーのみ。ユーザー管理や権限分離は無い（Django Admin を除く）
- HTTPS を張っていない

**外部からアクセスできる場所に置く場合は、最低でも次を見直すこと。**

| 項目 | 対応 |
|------|------|
| 通信の暗号化 | リバースプロキシで HTTPS を終端する。または Tailscale 等の VPN 経由にする |
| `DJANGO_SECRET_KEY` | 必ず設定する（未設定だと `DJANGO_DEBUG=False` では起動しない） |
| `DJANGO_ALLOWED_HOSTS` | 実際のホスト名を設定する |
| `MCP_ALLOWED_HOSTS` | 実際のホスト名だけを列挙する。**`*` などで広げないこと**（DNS リバインディング保護が無効になる） |
| APIキーの総当たり | `API_KEY_FAILURE_LIMIT`（既定10回）/ `API_KEY_FAILURE_WINDOW_SEC`（既定300秒）で調整。**既定のキャッシュはワーカーごとに独立するため、実効上限は「上限 × ワーカー数」になる**。厳密にしたい場合は共有キャッシュを設定する |
| Django Admin | `/admin/` が露出する。不要ならURLを変更するか無効化する |
| レート制限 | `THROTTLE_ANON` / `THROTTLE_USER` で調整 |

ポートを直接インターネットへ開放する運用は想定していない。

---

## データの置き場所と停止のしかた

**タスクの正本は PostgreSQL であり、Markdown のようにファイルとして残らない。**
データは Docker の名前付きボリューム `<フォルダ名>_pgdata`（例: `aidashboard_pgdata`）にある。

| コマンド | 結果 |
|----------|------|
| `docker compose -f compose.yaml stop` | 停止する。データは残る |
| `docker compose -f compose.yaml down` | コンテナを削除する。**データは残る** |
| `docker compose -f compose.yaml down -v` | **⚠ ボリュームごと削除する。全タスクが消える** |

`-v` を付けるのは、意図的に初期状態へ戻したいときだけ。
**運用を始めたあとは付けない。** 消えたデータはバックアップからしか戻せない。

```powershell
# データが残っているか確認する
docker volume ls --filter name=pgdata
```

PC の再起動でデータが消えることはない。`restart: unless-stopped` を設定してあるので、
Docker Desktop が起動すればコンテナも自動で復帰する。

---

## Claude Code から使う

### MCP サーバーを登録する

**ユーザースコープで一度だけ登録すれば、すべてのプロジェクトで使える。**

```powershell
claude mcp add --scope user --transport http dashboard http://127.0.0.1:8770/mcp `
  --header "Authorization: Api-Key <手順5のmcpキー>"
```

> 実際のフラグは `claude mcp add --help` で確認すること。

登録できたか確認する。

```powershell
claude mcp list
```

### 指示ファイルに書く

**MCP を登録しただけではエージェントはツールを呼ばない。** 指示ファイルへの記載が必要。

手順の本体は `~/.claude/CLAUDE.md` に一度だけ書き、各プロジェクトには1行だけ置く。
そのまま貼れる文面は [docs/agent-instructions.md](docs/agent-instructions.md) にある。

### 使えるツール

| ツール | 呼ぶタイミング |
|--------|---------------|
| `get_project(slug, cwd)` | **作業開始時。** 未処理タスクと判断待ちをまとめて取得 |
| `list_projects()` | 対象プロジェクトが曖昧なとき |
| `list_tasks(project, status, query)` | 既存タスクを探すとき |
| `create_task(project, title, actor_type="agent", ...)` | 該当タスクが無いとき |
| `update_task(key, status, note, actor_type=None, ...)` | 着手・完了・判断待ちが発生したとき |
| `report_session(project, summary, task_keys)` | **作業終了時** |

`get_project` は `cwd` を渡すと、`root_path` の前方一致でプロジェクトを自動判定する。

**未登録のディレクトリで作業しているときは、ダッシュボードのことに触れず従来どおり動作すること。**
エージェントにプロジェクト登録を促させない（登録するかどうかは人間が決める）。

---

## 自動実行パイプラインとの連携

`scripts/dashboard_client.ps1` を既存のパイプラインからドットソースし、3行足すだけでよい。

### 環境変数（ユーザー環境変数に設定する）

```powershell
[Environment]::SetEnvironmentVariable('DASHBOARD_URL', 'http://127.0.0.1:8770', 'User')
[Environment]::SetEnvironmentVariable('DASHBOARD_API_KEY_PIPELINE', '<手順5のpipelineキー>', 'User')
```

**ps1 にキーをハードコードしないこと。**

### 既存 ps1 への追記

```powershell
# ダッシュボード連携の読み込み。失敗してもパイプラインは止めない。
# 呼び出し側が $ErrorActionPreference = "Stop" の場合、未定義関数の呼び出しは
# スクリプト全体を落とす。読み込めなかったときは何もしない関数で代替する。
try { . "<このリポジトリのパス>\scripts\dashboard_client.ps1" } catch { }
if (-not (Get-Command Start-DashboardRun -ErrorAction SilentlyContinue)) {
    function Start-DashboardRun { param([string]$Key, [string]$LogPath, [string]$Trigger) }
    function Stop-DashboardRun  { param([string]$Status, [int]$ExitCode, [string]$Summary) }
    function Get-DashboardRunSummary { param([Parameter(ValueFromPipeline)]$OutputLines) end { '' } }
}
Start-DashboardRun -Key "blog-weekly-draft" -LogPath $logFile | Out-Null
try {
    $output = $promptText | & $claudeExe -p --permission-mode acceptEdits ...
    $output | Out-File -FilePath $logFile -Append -Encoding utf8
    Stop-DashboardRun -Status "succeeded" -Summary ($output | Get-DashboardRunSummary)
}
catch {
    "ERROR: $($_.Exception.Message)" | Out-File -FilePath $logFile -Append -Encoding utf8
    Stop-DashboardRun -Status "failed" -ExitCode 1 -Summary $_.Exception.Message
}
```

`-Key` に渡す値は `config/projects.toml` の `[[automation]]` に書いた `key`。
**登録していない key を送っても 404 になり、実行記録は残らない。**

> **`dashboard_client.ps1` は必ず UTF-8 BOM 付きで保存すること。**
> Windows PowerShell 5.1 は BOM の無いファイルを ANSI（日本語環境では CP932）として読む。
> 日本語コメントが化けるとブロックコメントの終端 `#>` が壊れ、`Start-DashboardRun` /
> `Stop-DashboardRun` が**パースエラーも出さずに未定義になる**。タスクスケジューラは
> `powershell.exe`（5.1）で起動するため、BOM を落とすと実行記録が静かに失われる。
> 上のガードはこの場合でもパイプラインを止めないためのもの。

登録済みの key は次で確認できる。

```powershell
docker compose -f compose.yaml exec api python manage.py seed_initial_data --dry-run
```

### 設計上の保証

**ダッシュボードが停止していてもパイプラインは止まらない。**
`dashboard_client.ps1` の関数はいかなる場合も例外を投げず、タイムアウトは5秒。
到達不能・APIキー未設定・未登録キーのいずれでも、警告すら出さずに処理を続行する。

`$env:DASHBOARD_CLIENT_VERBOSE = "1"` を設定すると送信の成否がコンソールに出る（デバッグ用）。

### 無人パイプラインからタスクを読み書きさせる

`dashboard_client.ps1` が送るのは**実行記録（Run）だけ**。パイプライン内のエージェントに
タスクそのものを読み書きさせるには、**`--allowedTools` に dashboard の MCP ツールを
明示的に追加する**必要がある。MCP サーバーをユーザースコープで登録していても、
`--allowedTools` に無いツールは遮断される。

```powershell
$allowedTools = "Bash,Read,Edit,Write,Glob,Grep,"
$allowedTools += "mcp__dashboard__get_project,mcp__dashboard__list_tasks,"
$allowedTools += "mcp__dashboard__create_task,mcp__dashboard__update_task,"
$allowedTools += "mcp__dashboard__report_session"
```

プロンプト側には、開始時に `get_project` を、終了時に `update_task` と `report_session` を
呼ぶよう書いておく。

> **`cwd` ではなく `slug` を明示すること。** 無人パイプラインは
> `Set-Location` でリポジトリの親などへ移動してから起動することが多く、
> その場合 `get_project(cwd=…)` は `root_path` の前方一致に失敗する。
> 対話セッションと違い、解決できなかったときに聞き返す相手がいない。

### `RESULT:` 行による要約

パイプラインのプロンプトに「処理結果を `RESULT: ...` の形式で1行出力する」と書いておくと、
`Get-DashboardRunSummary` がその行を拾ってダッシュボードの実行履歴に表示する。
該当行が無ければ空のまま記録されるだけで、エラーにはならない。

---

## Discord に通知する（任意）

`discord-bot` サービスが、次の3種類を Discord のチャンネルへ投稿する。タスクへの書き込みはしない（API へ書くのは、設定画面に出す自分の接続状態だけ）。

| いつ | 内容 |
|------|------|
| タスクが「本人待ち」になったとき（60秒以内） | タスクキー、タイトル、PJ名、同時に書かれた判断事項のメモ |
| 自動実行が失敗で終わったとき（60秒以内） | 自動実行名、終了時刻、終了コード、要約、ログのパス |
| 毎朝 8:00（設定画面で変更可） | 判断待ちの一覧、人間が対応するタスク、PJ別の未処理件数、直近24時間の自動実行の成否 |

bot は Discord へ外向きに接続し、ダッシュボードの API へは Compose の内部ネットワーク
（`http://api:8000`）で `discord` スコープのキーを使って読みに行く。**ダッシュボードを
インターネットへ公開する必要はない。** 成功した自動実行は毎日のバックアップなどで数が多いため、
個別には通知せず朝のまとめに件数だけ出す。

### 1. Discord 側の準備

**詳しい手順（サーバーの用意、bot の作成と招待、ID の調べ方、スマホへの通知、うまくいかないとき）は
[docs/discord-setup.md](docs/discord-setup.md) にある。** 要点は次の3つ。

1. [Developer Portal](https://discord.com/developers/applications) でアプリを作り、Bot のトークンを発行する。
   **Privileged Gateway Intents はすべてオフのままでよい。**
2. `https://discord.com/oauth2/authorize?client_id=<Application ID>&scope=bot&permissions=3072`
   （権限は `View Channels` と `Send Messages` だけ）を開き、対象のサーバーへ招待する。
3. Discord の設定 → 詳細設定 → **開発者モード** をオンにし、通知先チャンネルを右クリックして
   「チャンネルIDをコピー」する。

### 2. bot を起動する

`.env` には、bot がダッシュボードの API に接続するための値だけを書く。
`discord` スコープのキーは画面の「設定 → APIキー」か、次のコマンドで発行する。

```powershell
docker compose -f compose.yaml exec api python manage.py create_api_key --name discord-bot --scope discord
```

```dotenv
COMPOSE_PROFILES=discord
DASHBOARD_DISCORD_API_KEY=<発行した discord キー>
```

```powershell
docker compose -f compose.yaml up -d --build discord-bot
```

`COMPOSE_PROFILES=discord` を書くと、`docker compose up` で bot も一緒に起動する。
書かなければ bot は起動しない（既存の運用には影響しない）。

### 3. 設定画面で入力する

画面の「設定 → Discord bot」で、Bot トークンと通知チャンネル ID を入力して保存する。
任意で、メンションするユーザー ID・朝のまとめの時刻・確認間隔も変えられる。
「通知の種類と対象」では、判断待ち・失敗・朝のまとめを種類ごとに切り替え、通知するプロジェクトを絞り込める。

- bot は15秒ごとに設定を読み直す。**保存すれば bot を作り直す必要はない**（トークンを変えたときは bot が自分で接続し直す）
- トークンは保存後に画面へ表示しない（末尾4文字だけ）。値は DB に保存されるため、日次バックアップにも含まれる
- 「bot の状態」に、接続済み・設定待ち・トークンが無効・チャンネルに投稿できない、などが出る
- 「テスト送信」を押すと、保存済みの設定でチャンネルへテストメッセージを1件送る

> 以前 `.env` に書いていた `DISCORD_BOT_TOKEN` / `DISCORD_CHANNEL_ID` / `DISCORD_MENTION_USER_ID` /
> `DISCORD_DAILY_SUMMARY_TIME` / `DISCORD_POLL_INTERVAL_SEC` は、この変更のマイグレーション
> （`core.0004`）が初回の起動時に1回だけ設定画面の保存先へ取り込む。取り込んだ後は使われないので、
> `.env` から消してよい。

### 4. 確認

```powershell
# API への疎通と設定の確認（Discord には投稿しない）
docker compose -f compose.yaml run --rm --no-deps discord-bot python -m bot check

# 朝のまとめを今すぐ1回送る（投稿の確認用）
docker compose -f compose.yaml run --rm --no-deps discord-bot python -m bot send-summary

docker compose -f compose.yaml logs -f discord-bot
```

初回起動時は過去の履歴を流さず、起動した時点から購読を始める。どこまで通知したかは
名前付きボリューム `discord_bot_state` の `state.json` に残るため、再起動しても重複や取りこぼしは出ない。
通知を種類ごとにオフにしている間も既読の位置は進むため、オンに戻しても過去の分はまとめて流れない。

---

## ローカルリポジトリの状態を集める（任意）

ホームの「リポジトリ」欄に、登録したローカル Git リポジトリの状態を一覧で出す。
ブランチ、未コミットの変更（未追跡を含む）、未 push のコミット、リモートより遅れている数、
最終コミットを表示し、1つのプロジェクトに資料フォルダとコードのリポジトリを両方ひもづけられる。
MCP の `get_project` にも、そのプロジェクトのリポジトリが `repositories` として返る。

API はコンテナの中にあり、ホストのファイルは見えない。そこでホスト側の
`scripts/collect_repo_status.ps1` が `git status` / `git log` を読んで API へ送る。
**読み取りだけで、リポジトリには何も書き込まない**（`--no-optional-locks` で index の更新もしない。
`fetch` もしないので、「遅れ」は最後に fetch した時点の値）。

### 1. 対象を登録する

画面の「設定 → 監視するリポジトリ」で、フォルダの絶対パス・表示名・ひもづけるプロジェクトを登録する。
収集を止める（一覧から外す）・パスの変更・登録の削除もここで行える。登録を削除しても、フォルダには何もしない。

`config/projects.toml` に `[[repository]]` を書いて一括で登録することもできる。
ただし `seed_initial_data` は toml に書いた項目を画面での変更より優先して上書きする。

```toml
[[repository]]
path = 'C:\Users\you\src\my-app'
project = "my-app"   # 任意。ひもづけるプロジェクトの slug
# name = "my-app"    # 任意。省略時はフォルダ名
# is_active = false  # 一覧から外すとき
```

```powershell
docker compose -f compose.yaml exec api python manage.py seed_initial_data
```

### 2. 定期収集を登録する

自動実行パイプラインと同じ `DASHBOARD_API_KEY_PIPELINE`（ユーザー環境変数）を使う。

```powershell
.\scripts\collect_repo_status.ps1                 # 1回だけ手で実行して確認
.\scripts\register-repo-status-task.ps1           # 15分ごとの実行をタスクスケジューラへ登録
.\scripts\register-repo-status-task.ps1 -Unregister
```

コンソールが一瞬開かないよう、`conhost --headless` 経由で起動する（Windows 11）。
直近1回分のログは `automation/repo-status/logs/last_run.log` に残る。
画面では、45分以上届いていないリポジトリに「収集が古い」と出る。

---

## バックアップ

**DB が正本なので、バックアップは必須。** Markdown と違いファイルとして残らない。

```powershell
.\scripts\backup.ps1
```

`backups/` に `dashboard_YYYYMMDD_HHMMSS.sql.gz` を作り、古いものを削除する。残す世代数は
画面の「設定 → バックアップ」で変えられる（既定 7。`-Keep` を付けて実行したときはその値が優先。
`DASHBOARD_API_KEY_PIPELINE` が無いなどで設定を読めないときは 7）。
タスクスケジューラで日次実行することを推奨。

復元（DB を作り直してから流し込む）:

```powershell
$backup = "backups\dashboard_20260831_030000.sql.gz"

# 1. API と bot を止め、DB を空にする
docker compose -f compose.yaml stop discord-bot api
docker compose -f compose.yaml exec -T db dropdb -U dashboard dashboard
docker compose -f compose.yaml exec -T db createdb -U dashboard dashboard

# 2. バックアップをコンテナへコピーし、コンテナの中で展開して流し込む
docker compose -f compose.yaml cp $backup db:/tmp/restore.sql.gz
docker compose -f compose.yaml exec -T db sh -c "gunzip -c /tmp/restore.sql.gz | psql -v ON_ERROR_STOP=1 -U dashboard -d dashboard && rm /tmp/restore.sql.gz"

# 3. 起動し直す
docker compose -f compose.yaml up -d
```

> ダンプを PowerShell のパイプ（`|` や `Get-Content`）に通さないこと。PowerShell は出力を
> コンソールの文字コード（日本語環境では CP932）で文字列にするため、日本語がすべて化ける。
> バックアップも復元も、ファイルは `docker compose cp` でバイト列のまま受け渡す。

---

## 開発

### 開発モードで起動

```powershell
docker compose up -d --build
```

`-f` を付けないと `compose.override.yaml` が自動でマージされ、次が有効になる。

- `DJANGO_DEBUG=True`
- `uvicorn --reload`（コード変更が即反映）
- `./api` をコンテナへバインドマウント
- Vite dev server と HMR（`./web` をバインドマウント）
- ホストから `127.0.0.1:8771`（api）と `127.0.0.1:55432`（db）へ直接アクセス可能

> **注意**: バインドマウントされているため、**コンテナ内でファイルを書き換えるとホスト側にも反映される**。

### テスト

PostgreSQL が必要。開発モードで db を起動しておく。

```powershell
cd api
$env:DATABASE_URL = "postgresql://dashboard:<パスワード>@127.0.0.1:55432/dashboard"
$env:DJANGO_SECRET_KEY = "test"
uv run pytest
```

### マイグレーション

モデルを変更したら差分を確認する。

```powershell
docker compose exec api python manage.py makemigrations
```

CI 的に検証するなら `makemigrations --check --dry-run` が `No changes detected` を返すこと。

### 依存関係

`api/pyproject.toml` を変更したら、**必ず lock を再生成する**。

```powershell
docker run --rm -v "${PWD}\api:/w" -w /w python:3.12-slim sh -c "pip install uv && uv lock"
```

`uv.lock` は `uv sync --locked` が使うため、**pyproject と食い違うとビルドが失敗する**。
手書きで編集してはいけない（ハッシュと配布物 URL が必要）。

### Web の依存関係とOpenAPI型

API型は手書きせず、起動中のAPIが返すOpenAPIスキーマから生成する。

```powershell
cd web
npm install
npm run generate:api
npm run build
```

`npm run generate:api` は `http://127.0.0.1:8770/api/schema/` を読み、
`web/src/api/schema.d.ts` を更新する。APIのシリアライザやURLを変更したときは必ず再生成する。
Dockerの本番ビルドはこの生成物が無い場合に失敗する。API変更後の再生成は自動ではないため、
スキーマに関わる変更と同じコミットで生成物も更新する。
`package-lock.json` は `npm install` で生成し、依存更新時に合わせて更新する。

---

## トラブルシューティング

### `bind: An attempt was made to access a socket in a way forbidden by its access permissions`

そのポートが既に使われている。このプロジェクトで使うポートは次のとおり。

| ポート | 用途 |
|--------|------|
| 8770 | proxy（本番・開発とも） |
| 8771 | api への直接アクセス（開発時のみ） |
| 55432 | db への直接アクセス（開発時のみ） |

一般的な 8080 / 8000 / 5432 を避けてあるが、衝突したら誰が掴んでいるか確認する。

```powershell
Get-NetTCPConnection -LocalPort 8770 -State Listen |
  ForEach-Object { Get-Process -Id $_.OwningProcess }
```

変更する場合は `.env` の `DASHBOARD_PORT`・`DASHBOARD_URL`・`CORS_ALLOWED_ORIGINS`・
`MCP_ALLOWED_HOSTS`・`MCP_ALLOWED_ORIGINS` の `8770` を**すべて**揃えて `up -d` し直す
（`.env` を作る前なら `scripts/setup.ps1 -Port <番号>` で揃った状態で作られる）。
ホスト側のスクリプト用に、ユーザー環境変数 `DASHBOARD_URL` も新しい URL にする。

### MCP が `421 Misdirected Request` を返す

MCP SDK の DNS リバインディング対策により、許可されていない `Host` ヘッダが拒否されている。
`.env` の `MCP_ALLOWED_HOSTS` に、実際に使っているホスト名とポートの組み合わせを追加する。
ポート付き・ポート無しの両方を入れておくと安全。

```
MCP_ALLOWED_HOSTS=127.0.0.1,127.0.0.1:8770,localhost,localhost:8770,api,api:8000
```

**この保護を無効化しないこと。** 許可リストで解決する。

### `password authentication failed for user "dashboard"`

`.env` の `POSTGRES_PASSWORD` を変更したが、**古いパスワードで初期化されたボリュームが残っている**。
PostgreSQL はボリュームの初回作成時にしかパスワードを設定しない。

データを捨ててよいなら作り直す。

```powershell
docker compose -f compose.yaml down -v      # ⚠ 全データが消える
docker compose -f compose.yaml up -d
```

データを残したい場合は、`.env` を元のパスワードに戻すか、コンテナ内で `ALTER USER` する。

`DATABASE_URL` の中にもパスワードが埋まっている。**2箇所とも揃っているか確認すること。**

### api を作り直した後、画面や API が `502 Bad Gateway` になる

nginx（proxy）は起動時に api コンテナのアドレスを覚えるため、api だけを作り直すと古いアドレスへ送り続ける。
proxy を再起動する。

```powershell
docker compose -f compose.yaml restart proxy
```

### Admin にログインできない

`createsuperuser`（セットアップ手順4）を実行したか確認する。

### エージェントがツールを呼んでくれない

まずログで確認する。呼ばれていれば1回ごとに記録が残る。

```powershell
docker compose -f compose.yaml logs api | Select-String "mcp_tool_call"
```

まったく出ていなければ、MCP の登録か指示ファイルの記載が効いていない。
`claude mcp list` で接続を確認し、`~/.claude/CLAUDE.md` の記載を見直す。

---

## 既知の制限

- **中断したパイプラインの実行記録が `running` のまま残る。** `Stop-DashboardRun` が呼ばれる前に
  PC がシャットダウンした場合など。現状は Admin から手動で修正する
- `due_at` / `tags` / `parent` は API では更新できるが、MCP ツールからは変更できない
- 全文検索は未実装（`list_tasks(query=)` はタイトルの部分一致のみ）
