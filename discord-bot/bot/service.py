"""通知の判定と送信順序。Discord には依存せず、send 関数だけを受け取る。"""

import logging
from datetime import datetime, timedelta, timezone

from bot import messages
from bot.config import NotificationOptions


logger = logging.getLogger(__name__)

EVENT_PAGE_SIZE = 100
# 実行記録の終了時刻はパイプライン側（ホストの時計）で入るため、少し重ねて読み直す。
# 重なった分は notified_runs で重複を除く。
RUN_OVERLAP = timedelta(minutes=5)
SUMMARY_RUN_WINDOW = timedelta(hours=24)
# bot が止まっている間に押されたテスト送信を、後から突然送らないための上限
TEST_REQUEST_MAX_AGE = timedelta(minutes=10)


def utcnow():
    return datetime.now(timezone.utc)


class NotificationService:
    def __init__(
        self,
        api,
        store,
        send,
        time_zone,
        mention_user_id=None,
        clock=utcnow,
        options=None,
    ):
        self.api = api
        self.store = store
        self.send = send
        self.time_zone = time_zone
        self.mention_user_id = mention_user_id
        self.options = options or NotificationOptions()
        self.clock = clock
        self.state = store.load()

    def apply(self, config):
        """設定画面の変更を反映する（接続は張り直さない）。"""
        self.time_zone = config.time_zone
        self.mention_user_id = config.mention_user_id
        self.options = config.notifications

    def _save(self):
        self.store.save(self.state)

    async def poll(self):
        """定期実行の1回分。片方が失敗してももう片方は進める。"""
        for step in (self.poll_events, self.poll_runs):
            try:
                await step()
            except Exception:
                logger.exception("%s に失敗しました。次回の確認で再試行します", step.__name__)

    async def poll_events(self):
        if self.state.event_cursor is None:
            feed = await self.api.events()
            self.state.event_cursor = feed["next_after"]
            self._save()
            logger.info("タスクイベントの購読を開始しました（cursor=%s）", self.state.event_cursor)
            return

        while True:
            feed = await self.api.events(after=self.state.event_cursor, limit=EVENT_PAGE_SIZE)
            events = feed["results"]
            if not events:
                return
            # 通知を切っている間もカーソルは進める（入れ直したときに過去分をまとめて流さない）
            if self.options.awaiting_user:
                for notice in messages.awaiting_notices(events):
                    if not self.options.includes(notice.project):
                        continue
                    await self.send(messages.format_awaiting(notice, self.mention_user_id))
            # 送信が済んでからカーソルを進める（途中で落ちたら次回そのページを送り直す）。
            self.state.event_cursor = feed["next_after"]
            self._save()
            if len(events) < EVENT_PAGE_SIZE:
                return

    async def poll_runs(self):
        now = self.clock()
        if self.state.runs_checked_at is None or not self.options.failed_runs:
            if self.state.runs_checked_at is None:
                logger.info("自動実行の失敗の監視を開始しました")
            self.state.runs_checked_at = now.isoformat()
            self._save()
            return

        since = datetime.fromisoformat(self.state.runs_checked_at) - RUN_OVERLAP
        runs = await self.api.runs(ended_after=since, status="failed")
        for run in sorted(runs, key=lambda item: item.get("ended_at") or ""):
            if run["run_key"] in self.state.notified_runs:
                continue
            if self.options.includes(run.get("project")):
                await self.send(
                    messages.format_failed_run(run, self.time_zone, self.mention_user_id)
                )
            self.state.remember_run(run["run_key"])
            self._save()
        self.state.runs_checked_at = now.isoformat()
        self._save()

    def _filter_summary(self, summary, runs):
        if not self.options.projects:
            return summary, runs
        include = self.options.includes
        filtered = {
            **summary,
            "awaiting_user": [t for t in summary.get("awaiting_user") or [] if include(t.get("project"))],
            "human_tasks": [t for t in summary.get("human_tasks") or [] if include(t.get("project"))],
            "projects": [p for p in summary.get("projects") or [] if include(p.get("slug"))],
        }
        return filtered, [run for run in runs if include(run.get("project"))]

    async def daily_summary(self, force=False):
        if not force and not self.options.daily_summary:
            logger.info("朝のまとめは設定でオフになっています")
            return
        now = self.clock()
        today = now.astimezone(self.time_zone).date().isoformat()
        if not force and self.state.last_summary_date == today:
            logger.info("本日の朝のまとめは送信済みです")
            return
        summary = await self.api.summary()
        runs = await self.api.runs(ended_after=now - SUMMARY_RUN_WINDOW)
        summary, runs = self._filter_summary(summary, runs)
        await self.send(messages.format_daily_summary(summary, runs, now, self.time_zone))
        if force:
            # 手動送信（send-summary）は常駐中の bot と状態ファイルを取り合わないよう記録しない。
            return
        self.state.last_summary_date = today
        self._save()

    async def handle_test_request(self, requested_at):
        """設定画面の「テスト送信」を処理する。

        戻り値: 処理した依頼の識別子（requested_at）とエラー文。新しい依頼が無ければ None。
        """
        if not requested_at or requested_at == self.state.last_test_request:
            return None
        self.state.last_test_request = requested_at
        self._save()
        try:
            requested = datetime.fromisoformat(requested_at)
        except ValueError:
            return requested_at, "依頼の時刻を読めませんでした"
        if self.clock() - requested > TEST_REQUEST_MAX_AGE:
            return requested_at, "bot が止まっている間の依頼だったため送信しませんでした。もう一度押してください"
        try:
            await self.send(messages.format_test_message(self.mention_user_id, self.options))
        except Exception as exc:
            logger.exception("テスト送信に失敗しました")
            return requested_at, f"送信に失敗しました: {exc}"
        return requested_at, ""
