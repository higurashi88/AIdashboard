import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from bot.service import NotificationService
from bot.state import MAX_NOTIFIED_RUNS, State, StateStore


TOKYO = ZoneInfo("Asia/Tokyo")
NOW = datetime(2026, 9, 24, 0, 0, tzinfo=timezone.utc)  # 日本時間 9:00


def event(event_id, key, event_type, status="awaiting_user", payload=None, body=""):
    return {
        "id": event_id,
        "task_key": key,
        "task_title": f"{key} のタイトル",
        "task_status": status,
        "project": "sample",
        "project_name": "サンプルPJ",
        "event_type": event_type,
        "actor": "claude_code",
        "body": body,
        "occurred_at": "2026-09-24T09:00:00+09:00",
        "payload": payload or {},
    }


def failed_run(run_key, ended_at):
    return {
        "run_key": run_key,
        "automation_key": "sample-automation",
        "automation_name": "サンプル自動実行",
        "project": "sample",
        "status": "failed",
        "ended_at": ended_at.isoformat(),
        "exit_code": 1,
        "summary": "テストに失敗",
        "log_path": r"E:\logs\run.log",
    }


class FakeApi:
    def __init__(self):
        self.feed = []
        self.latest = 0
        self.failed_runs = []
        self.all_runs = []
        self.summary_payload = {"awaiting_user": [], "human_tasks": [], "projects": []}
        self.run_queries = []
        self.fail_events = False

    async def events(self, after=None, limit=100):
        if self.fail_events:
            raise RuntimeError("api down")
        if after is None:
            return {"results": [], "next_after": self.latest}
        results = [item for item in self.feed if item["id"] > after][:limit]
        return {"results": results, "next_after": results[-1]["id"] if results else after}

    async def runs(self, ended_after, status=None):
        self.run_queries.append((ended_after, status))
        source = self.failed_runs if status == "failed" else self.all_runs
        return [run for run in source if datetime.fromisoformat(run["ended_at"]) > ended_after]

    async def summary(self):
        return self.summary_payload


class Harness:
    def __init__(self, tmp_path, now=NOW):
        self.api = FakeApi()
        self.sent = []
        self.now = now
        self.store = StateStore(tmp_path / "state.json")

    async def _send(self, content):
        self.sent.append(content)

    def service(self, mention_user_id=None):
        return NotificationService(
            api=self.api,
            store=self.store,
            send=self._send,
            time_zone=TOKYO,
            mention_user_id=mention_user_id,
            clock=lambda: self.now,
        )


def run(coro):
    return asyncio.run(coro)


def test_first_poll_starts_from_now_without_sending_history(tmp_path):
    harness = Harness(tmp_path)
    harness.api.latest = 42
    harness.api.feed = [event(40, "A-1", "status_changed", payload={"to": "awaiting_user"})]

    run(harness.service().poll())

    assert harness.sent == []
    assert harness.store.load().event_cursor == 42
    assert harness.store.load().runs_checked_at == NOW.isoformat()


def test_awaiting_user_transition_is_sent_with_note(tmp_path):
    harness = Harness(tmp_path)
    harness.store.save(State(event_cursor=10, runs_checked_at=NOW.isoformat()))
    harness.api.feed = [
        event(11, "A-1", "status_changed", payload={"from": "todo", "to": "awaiting_user"}),
        event(12, "A-1", "note", body="どちらの案で進めるか決めてください"),
        event(13, "A-2", "status_changed", status="done", payload={"to": "done"}),
    ]

    run(harness.service(mention_user_id=123).poll_events())

    assert len(harness.sent) == 1
    message = harness.sent[0]
    assert message.startswith("<@123> 🙋 **判断待ち** `A-1`")
    assert "PJ：サンプルPJ" in message
    assert "> どちらの案で進めるか決めてください" in message
    assert harness.store.load().event_cursor == 13


def test_task_created_as_awaiting_user_is_sent(tmp_path):
    harness = Harness(tmp_path)
    harness.store.save(State(event_cursor=0))
    harness.api.feed = [event(1, "A-3", "created", payload={"status": "awaiting_user"})]

    run(harness.service().poll_events())

    assert len(harness.sent) == 1
    assert "`A-3`" in harness.sent[0]


def test_task_no_longer_awaiting_is_not_sent(tmp_path):
    harness = Harness(tmp_path)
    harness.store.save(State(event_cursor=0))
    harness.api.feed = [
        event(1, "A-4", "status_changed", status="done", payload={"to": "awaiting_user"}),
        event(2, "A-4", "status_changed", status="done", payload={"to": "done"}),
    ]

    run(harness.service().poll_events())

    assert harness.sent == []


def test_events_are_read_across_pages(tmp_path, monkeypatch):
    monkeypatch.setattr("bot.service.EVENT_PAGE_SIZE", 2)
    harness = Harness(tmp_path)
    harness.store.save(State(event_cursor=0))
    harness.api.feed = [
        event(index, f"A-{index}", "status_changed", payload={"to": "awaiting_user"})
        for index in range(1, 6)
    ]

    run(harness.service().poll_events())

    assert len(harness.sent) == 5
    assert harness.store.load().event_cursor == 5


def test_cursor_is_not_advanced_when_sending_fails(tmp_path):
    harness = Harness(tmp_path)
    harness.store.save(State(event_cursor=0))
    harness.api.feed = [event(1, "A-1", "status_changed", payload={"to": "awaiting_user"})]
    service = harness.service()

    async def broken_send(content):
        raise RuntimeError("discord down")

    service.send = broken_send
    with pytest.raises(RuntimeError):
        run(service.poll_events())

    assert harness.store.load().event_cursor == 0


def test_failed_runs_are_sent_once(tmp_path):
    harness = Harness(tmp_path)
    checked_at = NOW - timedelta(minutes=1)
    harness.store.save(State(event_cursor=0, runs_checked_at=checked_at.isoformat()))
    harness.api.failed_runs = [
        failed_run("run-new", NOW - timedelta(seconds=30)),
        failed_run("run-overlap", checked_at - timedelta(minutes=2)),
        failed_run("run-old", checked_at - timedelta(hours=1)),
    ]

    service = harness.service()
    run(service.poll_runs())
    run(service.poll_runs())

    assert len(harness.sent) == 2
    assert "run-old" not in "".join(harness.sent)
    assert "❌ **自動実行が失敗** サンプル自動実行（sample）" in harness.sent[0]
    assert "終了コード：1" in harness.sent[0]
    assert "ログ：`E:\\logs\\run.log`" in harness.sent[0]
    assert harness.api.run_queries[0] == (checked_at - timedelta(minutes=5), "failed")


def test_poll_continues_with_runs_when_events_fail(tmp_path):
    harness = Harness(tmp_path)
    harness.store.save(State(event_cursor=0, runs_checked_at=(NOW - timedelta(minutes=1)).isoformat()))
    harness.api.fail_events = True
    harness.api.failed_runs = [failed_run("run-new", NOW - timedelta(seconds=10))]

    run(harness.service().poll())

    assert len(harness.sent) == 1


def test_daily_summary_is_sent_once_per_day(tmp_path):
    harness = Harness(tmp_path)
    harness.api.summary_payload = {
        "awaiting_user": [{"key": "A-1", "title": "決めること", "project": "sample"}],
        "human_tasks": [],
        "projects": [
            {"slug": "sample", "name": "サンプルPJ", "open_tasks": 3, "awaiting_user": 1},
            {"slug": "idle", "name": "静かなPJ", "open_tasks": 0, "awaiting_user": 0},
        ],
    }
    harness.api.all_runs = [
        {**failed_run("run-a", NOW - timedelta(hours=2)), "status": "succeeded"},
        failed_run("run-b", NOW - timedelta(hours=1)),
    ]

    service = harness.service()
    run(service.daily_summary())
    run(service.daily_summary())

    assert len(harness.sent) == 1
    message = harness.sent[0]
    assert message.startswith("☀️ **9/24（木）のダッシュボード**")
    assert "**判断待ち 1件**" in message
    assert "・`A-1` 決めること（サンプルPJ）" in message
    assert "・サンプルPJ　3 / 1" in message
    assert "静かなPJ" not in message
    assert "成功 1・失敗 1" in message
    assert harness.store.load().last_summary_date == "2026-09-24"


def test_forced_daily_summary_ignores_sent_marker(tmp_path):
    harness = Harness(tmp_path)
    harness.store.save(State(event_cursor=7, last_summary_date="2026-09-24"))

    run(harness.service().daily_summary(force=True))

    assert len(harness.sent) == 1
    assert "**判断待ち** なし" in harness.sent[0]
    assert harness.store.load() == State(event_cursor=7, last_summary_date="2026-09-24")


def test_state_store_tolerates_missing_and_corrupt_files(tmp_path):
    store = StateStore(tmp_path / "state.json")
    assert store.load() == State()

    (tmp_path / "state.json").write_text("{broken", encoding="utf-8")
    assert store.load() == State()


def test_notified_runs_are_bounded():
    state = State()
    for index in range(MAX_NOTIFIED_RUNS + 5):
        state.remember_run(f"run-{index}")
    state.remember_run(f"run-{MAX_NOTIFIED_RUNS + 4}")

    assert len(state.notified_runs) == MAX_NOTIFIED_RUNS
    assert state.notified_runs[0] == "run-5"


# --- 設定画面の通知設定 -----------------------------------------------------------

from bot.config import NotificationOptions  # noqa: E402


def test_awaiting_notices_can_be_turned_off_without_backlog(tmp_path):
    harness = Harness(tmp_path)
    harness.store.save(State(event_cursor=0))
    harness.api.feed = [event(1, "A-1", "status_changed", payload={"to": "awaiting_user"})]
    service = harness.service()
    service.options = NotificationOptions(awaiting_user=False)

    run(service.poll_events())

    assert harness.sent == []
    # 切っている間もカーソルは進む（入れ直しても過去分は流れない）
    assert harness.store.load().event_cursor == 1


def test_awaiting_notices_are_filtered_by_project(tmp_path):
    harness = Harness(tmp_path)
    harness.store.save(State(event_cursor=0))
    other = {**event(2, "B-1", "status_changed", payload={"to": "awaiting_user"}), "project": "other"}
    harness.api.feed = [event(1, "A-1", "status_changed", payload={"to": "awaiting_user"}), other]
    service = harness.service()
    service.options = NotificationOptions(projects=frozenset({"other"}))

    run(service.poll_events())

    assert len(harness.sent) == 1
    assert "`B-1`" in harness.sent[0]


def test_failed_runs_can_be_turned_off_and_filtered(tmp_path):
    harness = Harness(tmp_path)
    checked_at = NOW - timedelta(minutes=1)
    harness.store.save(State(event_cursor=0, runs_checked_at=checked_at.isoformat()))
    harness.api.failed_runs = [
        failed_run("run-sample", NOW - timedelta(seconds=30)),
        {**failed_run("run-other", NOW - timedelta(seconds=20)), "project": "other"},
    ]
    service = harness.service()

    service.options = NotificationOptions(failed_runs=False)
    run(service.poll_runs())
    assert harness.sent == []
    assert harness.api.run_queries == []
    assert harness.store.load().runs_checked_at == NOW.isoformat()

    harness.store.save(State(event_cursor=0, runs_checked_at=checked_at.isoformat()))
    service = harness.service()
    service.options = NotificationOptions(projects=frozenset({"other"}))
    run(service.poll_runs())
    assert len(harness.sent) == 1
    assert "（other）" in harness.sent[0]
    # 対象外でも「処理済み」として覚える
    assert set(harness.store.load().notified_runs) == {"run-sample", "run-other"}


def test_daily_summary_can_be_turned_off(tmp_path):
    harness = Harness(tmp_path)
    service = harness.service()
    service.options = NotificationOptions(daily_summary=False)

    run(service.daily_summary())

    assert harness.sent == []
    assert harness.store.load().last_summary_date is None


def test_daily_summary_is_filtered_by_project(tmp_path):
    harness = Harness(tmp_path)
    harness.api.summary_payload = {
        "awaiting_user": [
            {"key": "A-1", "title": "対象", "project": "sample"},
            {"key": "B-1", "title": "対象外", "project": "other"},
        ],
        "human_tasks": [{"key": "B-2", "title": "人の作業", "project": "other"}],
        "projects": [
            {"slug": "sample", "name": "サンプルPJ", "open_tasks": 3, "awaiting_user": 1},
            {"slug": "other", "name": "別PJ", "open_tasks": 2, "awaiting_user": 1},
        ],
    }
    harness.api.all_runs = [
        failed_run("run-a", NOW - timedelta(hours=1)),
        {**failed_run("run-b", NOW - timedelta(hours=1)), "project": "other"},
    ]
    service = harness.service()
    service.options = NotificationOptions(projects=frozenset({"sample"}))

    run(service.daily_summary())

    message = harness.sent[0]
    assert "**判断待ち 1件**" in message
    assert "B-1" not in message and "B-2" not in message
    assert "別PJ" not in message
    assert "成功 0・失敗 1" in message


def test_apply_updates_mention_time_zone_and_options(tmp_path):
    from bot.config import parse_bot_config

    harness = Harness(tmp_path)
    service = harness.service()
    config = parse_bot_config(
        {
            "bot_token": "t",
            "channel_id": "1",
            "mention_user_id": "55",
            "time_zone": "UTC",
            "notifications": {"daily_summary": False},
        }
    )

    service.apply(config)

    assert service.mention_user_id == 55
    assert str(service.time_zone) == "UTC"
    assert service.options.daily_summary is False


def test_test_request_is_sent_once(tmp_path):
    harness = Harness(tmp_path)
    service = harness.service(mention_user_id=7)
    requested_at = (NOW - timedelta(seconds=20)).isoformat()

    first = run(service.handle_test_request(requested_at))
    second = run(service.handle_test_request(requested_at))

    assert first == (requested_at, "")
    assert second is None
    assert len(harness.sent) == 1
    assert harness.sent[0].startswith("<@7> ✅ **テスト通知**")
    assert harness.store.load().last_test_request == requested_at


def test_stale_or_failed_test_request_reports_error(tmp_path):
    harness = Harness(tmp_path)
    service = harness.service()

    stale = (NOW - timedelta(hours=1)).isoformat()
    handled, error = run(service.handle_test_request(stale))
    assert handled == stale and "もう一度" in error
    assert harness.sent == []

    async def broken_send(content):
        raise RuntimeError("Missing Access")

    service.send = broken_send
    fresh = NOW.isoformat()
    handled, error = run(service.handle_test_request(fresh))
    assert handled == fresh and "Missing Access" in error

    assert run(service.handle_test_request(None)) is None
