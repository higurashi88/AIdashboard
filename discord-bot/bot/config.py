"""bot の設定。

- 起動に必要な最小限（API の場所とキー、状態ファイル）だけを環境変数から読む。
- Discord のトークン・チャンネル・通知の ON/OFF などは、ダッシュボードの設定画面で保存した値を
  API（GET /discord/config/）から読む。bot は定期的に読み直し、作り直さなくても反映する。
"""

import os
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_API_URL = "http://api:8000/api/v1"
DEFAULT_TIME_ZONE = "Asia/Tokyo"
DEFAULT_SUMMARY_TIME = "08:00"
DEFAULT_POLL_INTERVAL_SEC = 60
MIN_POLL_INTERVAL_SEC = 10
DEFAULT_STATE_PATH = "/data/state.json"
# 設定画面の変更を読み直す間隔（テスト送信の依頼もこの間隔で拾う）
DEFAULT_CONFIG_REFRESH_SEC = 15


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Bootstrap:
    """環境変数から読む、起動に必要な値。"""

    api_url: str
    api_key: str
    state_path: Path
    config_refresh_sec: int

    def missing(self):
        return [] if self.api_key else ["DASHBOARD_DISCORD_API_KEY"]


def load_bootstrap(env=None):
    env = os.environ if env is None else env
    refresh = env.get("DISCORD_CONFIG_REFRESH_SEC", "").strip()
    if refresh and not refresh.isdigit():
        raise ConfigError("DISCORD_CONFIG_REFRESH_SEC は秒数（整数）で指定してください")
    return Bootstrap(
        api_url=(env.get("DASHBOARD_API_URL", "").strip() or DEFAULT_API_URL).rstrip("/"),
        api_key=env.get("DASHBOARD_DISCORD_API_KEY", "").strip(),
        state_path=Path(env.get("DISCORD_STATE_PATH", "").strip() or DEFAULT_STATE_PATH),
        config_refresh_sec=max(int(refresh or DEFAULT_CONFIG_REFRESH_SEC), 5),
    )


@dataclass(frozen=True)
class NotificationOptions:
    awaiting_user: bool = True
    failed_runs: bool = True
    daily_summary: bool = True
    # 空なら全プロジェクト
    projects: frozenset = field(default_factory=frozenset)

    def includes(self, project_slug):
        return not self.projects or project_slug in self.projects


@dataclass(frozen=True)
class BotConfig:
    """設定画面で保存した値（API から読む）。"""

    token: str
    channel_id: int | None
    mention_user_id: int | None
    poll_interval_sec: int
    time_zone: ZoneInfo
    summary_time: time
    notifications: NotificationOptions
    test_requested_at: str | None = None

    def missing(self):
        """接続に必須で、まだ設定画面で入力されていない項目名を返す。"""
        missing = []
        if not self.token:
            missing.append("Bot トークン")
        if self.channel_id is None:
            missing.append("通知チャンネル ID")
        return missing


def _optional_id(value, label):
    value = str(value or "").strip()
    if not value:
        return None
    if not value.isdigit():
        raise ConfigError(f"{label} は数字の ID で指定してください（現在: {value!r}）")
    return int(value)


def _time_zone(name):
    try:
        return ZoneInfo(str(name or "").strip() or DEFAULT_TIME_ZONE)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError(f"タイムゾーンが正しくありません（現在: {name!r}）") from exc


def _summary_time(value, time_zone):
    value = str(value or "").strip() or DEFAULT_SUMMARY_TIME
    try:
        hour, minute = (int(part) for part in value.split(":"))
        return time(hour=hour, minute=minute, tzinfo=time_zone)
    except ValueError as exc:
        raise ConfigError(
            f"朝のまとめの時刻は HH:MM 形式で指定してください（現在: {value!r}）"
        ) from exc


def _poll_interval(value):
    try:
        seconds = int(value if value not in (None, "") else DEFAULT_POLL_INTERVAL_SEC)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"確認間隔は秒数で指定してください（現在: {value!r}）") from exc
    return max(seconds, MIN_POLL_INTERVAL_SEC)


def parse_bot_config(data):
    """GET /discord/config/ の応答を BotConfig にする。"""
    time_zone = _time_zone(data.get("time_zone"))
    notifications = data.get("notifications") or {}
    return BotConfig(
        token=str(data.get("bot_token") or "").strip(),
        channel_id=_optional_id(data.get("channel_id"), "通知チャンネル ID"),
        mention_user_id=_optional_id(data.get("mention_user_id"), "メンションするユーザー ID"),
        poll_interval_sec=_poll_interval(data.get("poll_interval_sec")),
        time_zone=time_zone,
        summary_time=_summary_time(data.get("daily_summary_time"), time_zone),
        notifications=NotificationOptions(
            awaiting_user=bool(notifications.get("awaiting_user", True)),
            failed_runs=bool(notifications.get("failed_runs", True)),
            daily_summary=bool(notifications.get("daily_summary", True)),
            projects=frozenset(notifications.get("projects") or ()),
        ),
        test_requested_at=data.get("test_requested_at") or None,
    )
