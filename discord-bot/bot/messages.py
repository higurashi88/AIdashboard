"""ダッシュボードのデータを Discord に投稿する文面へ変換する（副作用なし）。"""

from dataclasses import dataclass
from datetime import datetime


DISCORD_MESSAGE_LIMIT = 2000
NOTE_LIMIT = 900
WEEKDAYS = "月火水木金土日"
AWAITING_USER = "awaiting_user"


@dataclass
class AwaitingNotice:
    task_key: str
    title: str
    project_name: str
    note: str | None = None
    project: str | None = None


def truncate(text, limit):
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def quote(text):
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def _mention(user_id):
    return f"<@{user_id}> " if user_id else ""


def _became_awaiting(event):
    payload = event.get("payload") or {}
    if event["event_type"] == "status_changed":
        return payload.get("to") == AWAITING_USER
    if event["event_type"] == "created":
        return payload.get("status") == AWAITING_USER
    return False


def awaiting_notices(events):
    """イベント列から「本人の判断待ちになったタスク」を取り出す。

    状態変更と同じ更新で書かれたメモ（note）を判断事項として添える。
    まとめて読んだ間に判断待ちでなくなったタスクは通知しない。
    """
    notices = {}
    for event in events:
        key = event["task_key"]
        if _became_awaiting(event):
            notices[key] = AwaitingNotice(
                task_key=key,
                title=event["task_title"],
                project_name=event["project_name"],
                project=event.get("project"),
            )
        elif event["event_type"] == "note" and key in notices:
            notices[key].note = event["body"]
    current_status = {event["task_key"]: event["task_status"] for event in events}
    return [
        notice
        for key, notice in notices.items()
        if current_status.get(key) == AWAITING_USER
    ]


def _local(value, time_zone):
    if not value:
        return None
    return datetime.fromisoformat(value).astimezone(time_zone)


def _short_datetime(value, time_zone):
    local = _local(value, time_zone)
    return f"{local.month}/{local.day} {local:%H:%M}" if local else "不明"


def format_awaiting(notice, mention_user_id=None):
    lines = [
        f"{_mention(mention_user_id)}🙋 **判断待ち** `{notice.task_key}` {notice.title}",
        f"PJ：{notice.project_name}",
    ]
    if notice.note:
        lines.append(quote(truncate(notice.note, NOTE_LIMIT)))
    return truncate("\n".join(lines), DISCORD_MESSAGE_LIMIT)


def format_failed_run(run, time_zone, mention_user_id=None):
    name = run.get("automation_name") or run["automation_key"]
    details = [f"終了：{_short_datetime(run.get('ended_at'), time_zone)}"]
    if run.get("exit_code") is not None:
        details.append(f"終了コード：{run['exit_code']}")
    lines = [
        f"{_mention(mention_user_id)}❌ **自動実行が失敗** {name}（{run['project']}）",
        "　".join(details),
    ]
    if run.get("summary"):
        lines.append(quote(truncate(run["summary"], NOTE_LIMIT)))
    if run.get("log_path"):
        lines.append(f"ログ：`{run['log_path']}`")
    return truncate("\n".join(lines), DISCORD_MESSAGE_LIMIT)


def _task_lines(tasks, limit, project_names):
    lines = [
        f"・`{task['key']}` {truncate(task['title'], 60)}"
        f"（{project_names.get(task['project'], task['project'])}）"
        for task in tasks[:limit]
    ]
    if len(tasks) > limit:
        lines.append(f"・ほか {len(tasks) - limit} 件")
    return lines


def format_daily_summary(summary, runs, now, time_zone):
    today = now.astimezone(time_zone)
    project_names = {
        project["slug"]: project["name"] for project in summary.get("projects") or []
    }
    sections = [f"☀️ **{today.month}/{today.day}（{WEEKDAYS[today.weekday()]}）のダッシュボード**"]

    awaiting = summary.get("awaiting_user") or []
    if awaiting:
        sections.append("\n".join([f"**判断待ち {len(awaiting)}件**", *_task_lines(awaiting, 10, project_names)]))
    else:
        sections.append("**判断待ち** なし")

    human_tasks = summary.get("human_tasks") or []
    if human_tasks:
        sections.append(
            "\n".join([f"**人間が対応するタスク {len(human_tasks)}件**", *_task_lines(human_tasks, 5, project_names)])
        )

    projects = [project for project in summary.get("projects") or [] if project["open_tasks"]]
    if projects:
        sections.append(
            "\n".join(
                ["**PJ別（未処理 / 判断待ち）**"]
                + [
                    f"・{project['name']}　{project['open_tasks']} / {project['awaiting_user']}"
                    for project in projects
                ]
            )
        )

    succeeded = [run for run in runs if run["status"] == "succeeded"]
    failed = [run for run in runs if run["status"] == "failed"]
    run_lines = [f"**直近24時間の自動実行** 成功 {len(succeeded)}・失敗 {len(failed)}"]
    for run in failed[:5]:
        name = run.get("automation_name") or run["automation_key"]
        summary_text = truncate(run.get("summary"), 80)
        suffix = f"：{summary_text}" if summary_text else ""
        run_lines.append(
            f"・❌ {name}（{_short_datetime(run.get('ended_at'), time_zone)}）{suffix}"
        )
    sections.append("\n".join(run_lines))

    return truncate("\n\n".join(sections), DISCORD_MESSAGE_LIMIT)


def _on_off(value):
    return "ON" if value else "OFF"


def format_test_message(mention_user_id=None, options=None):
    lines = [
        f"{_mention(mention_user_id)}✅ **テスト通知** ダッシュボードの設定画面から送信しました。",
    ]
    if options is not None:
        lines.append(
            f"判断待ち {_on_off(options.awaiting_user)}／"
            f"自動実行の失敗 {_on_off(options.failed_runs)}／"
            f"朝のまとめ {_on_off(options.daily_summary)}"
        )
        target = (
            "全プロジェクト"
            if not options.projects
            else "、".join(sorted(options.projects))
        )
        lines.append(f"対象：{target}")
    return truncate("\n".join(lines), DISCORD_MESSAGE_LIMIT)
