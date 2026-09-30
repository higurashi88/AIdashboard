# エージェント指示ファイルのテンプレート

Claude Code / Codex がダッシュボードのツールを呼ぶかどうかは、**指示ファイルの記述で決まる**。
MCP サーバーを登録しただけでは呼ばれない。ここが実質的な設定ファイルになる。

## 方針

手順を各プロジェクトにコピーすると、ツール仕様を変えたときに全プロジェクトの指示ファイルを
直して回ることになる。そこで**共通部を1箇所に置き、各プロジェクトには1行だけ**置く。

| ファイル | 内容 | 更新頻度 |
|----------|------|---------|
| `~/.claude/CLAUDE.md` | 手順の本体（下記①） | ツール仕様の変更時のみ |
| 各プロジェクトの `CLAUDE.md` / `AGENTS.md` | slug の明示1行（下記②） | プロジェクト追加時に1行 |
| パイプライン用プロンプト | 対話セッションと手順が違う場合のみ | 個別 |

---

## ① `~/.claude/CLAUDE.md` に追記する（一度だけ）

> **下のコードブロックの中身だけ**をコピーしてください。
> 先頭と末尾の ``` は範囲を示す記号であり、ファイルに含めません。
> この節より下（②以降）は**あなたが読むための手順**なので、貼り付けないでください。

```markdown
## タスク管理（ダッシュボード）

作業対象のプロジェクトがダッシュボードに登録されている場合、タスクの正本は MCP サーバー
`dashboard` にある。Markdown のタスクファイルは使わない。

### 開始時
1. `get_project(cwd="<現在の作業ディレクトリ>")` を呼び、未処理タスクと判断待ちを確認する。
   プロジェクトが解決できなければ `list_projects()` で確認する。
   **未登録のプロジェクトなら本節は適用せず、ダッシュボードには一切触れない。**
   登録を促したりもしない（登録するかどうかは本人が決める）。
2. 依頼が既存タスクに該当すればその `key`（例 `APP-12`）を使う。
   該当が無ければ `create_task` で登録してから着手する。
   登録前に `list_tasks(query=…)` で重複を確認する。

### 作業中
- 着手したら `update_task(key, status="in_progress")`。
- 方針変更や重要な発見は `update_task(key, note="…")` で残す。**1〜2文で簡潔に。**
  長い経緯はプロジェクトの Markdown 資料に書く。

### 完了時
- 完了したら `update_task(key, status="done", note="何をしたか")`。
- 本人の判断・確認・承認が必要になったら `update_task(key, status="awaiting_user",
  note="何を判断してほしいか")` とし、**自分では実行しない**。
- セッションの最後に `report_session(project, "作業内容の要約", [触れたkey])` を呼ぶ。

ツール呼び出しが失敗しても作業は続行し、最後に失敗した旨を報告する。
```

## ② 各プロジェクトの `CLAUDE.md` / `AGENTS.md` に追記する（1行）

> ここから下は `~/.claude/CLAUDE.md` には入れません。

```markdown
タスク管理はダッシュボードで行う（slug: `my-app`）。手順は `~/.claude/CLAUDE.md` を参照。
```

`get_project` は `cwd` からプロジェクトを解決できるため、この1行は**確認用の明示**であって、
書き忘れても動作する。Codex 向けには同じ1行を `AGENTS.md` に置く。

> 自分の環境の slug 一覧と移行手順は、非公開のメモに分けて管理するとよい。

---

## 呼ばれているかの確認

指示を書いても実際に呼ばれるとは限らない。**必ずログで確認すること。**

```powershell
docker compose -f compose.yaml logs api | Select-String "mcp_tool_call"
```

1回の呼び出しにつき、ツール名・引数・成否・所要ミリ秒が1行の JSON で残る。

```json
{"levelname": "INFO", "name": "apps.mcp.tools", "message": "mcp_tool_call",
 "mcp_tool": "get_project", "mcp_arguments": {"slug": null, "cwd": "C:\src\my-app"},
 "mcp_success": true, "mcp_duration_ms": 9.68}
```

まったく出ていなければ、MCP の登録か指示ファイルの記載が効いていない。
`get_project` だけ出て `report_session` が出ないなら、終了時の記載が弱い。

**呼ばれ方を見てから指示文を調整する**のが、この仕組みを定着させる唯一の方法になる。

---

## 無人パイプラインの場合

タスクスケジューラ等から `claude -p` で起動する無人パイプラインでは、上の①②に加えて
2点の追加が要る。

1. **`--allowedTools` に dashboard のツールを明示する。** MCP サーバーを登録していても、
   `--allowedTools` に無いツールは遮断される。

   ```
   mcp__dashboard__get_project,mcp__dashboard__list_tasks,
   mcp__dashboard__create_task,mcp__dashboard__update_task,mcp__dashboard__report_session
   ```

2. **プロンプトで `get_project(slug="…")` と slug を明示する。** 無人パイプラインは
   作業ディレクトリをプロジェクトルート以外に移してから起動することが多く、
   `cwd` での解決に失敗する。対話セッションと違い、失敗しても聞き返す相手がいない。

終了時は `update_task` と `report_session` を呼ばせる。本人の判断が要るものは
`status="awaiting_user"` とし、エージェント自身には実行させないこと。
