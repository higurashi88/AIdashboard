import asyncio
from datetime import time

import pytest

from bot.config import ConfigError, NotificationOptions, load_bootstrap, parse_bot_config
from bot.main import _mark_test_unavailable, load_config
from bot.messages import AwaitingNotice, DISCORD_MESSAGE_LIMIT, format_awaiting, format_test_message
from bot.state import StateStore


def api_config(**overrides):
    data = {
        "bot_token": "token",
        "channel_id": "123456789012345678",
        "mention_user_id": "",
        "daily_summary_time": "08:00",
        "poll_interval_sec": 60,
        "time_zone": "Asia/Tokyo",
        "notifications": {
            "awaiting_user": True,
            "failed_runs": True,
            "daily_summary": True,
            "projects": [],
        },
        "test_requested_at": None,
    }
    data.update(overrides)
    return data


def test_bootstrap_defaults_and_missing_key():
    bootstrap = load_bootstrap({})

    assert bootstrap.api_url == "http://api:8000/api/v1"
    assert bootstrap.config_refresh_sec == 15
    assert bootstrap.missing() == ["DASHBOARD_DISCORD_API_KEY"]


def test_bootstrap_values_are_parsed():
    bootstrap = load_bootstrap(
        {
            "DASHBOARD_DISCORD_API_KEY": "key",
            "DASHBOARD_API_URL": "http://example/api/v1/",
            "DISCORD_CONFIG_REFRESH_SEC": "1",
        }
    )

    assert bootstrap.missing() == []
    assert bootstrap.api_url == "http://example/api/v1"
    assert bootstrap.config_refresh_sec == 5


def test_bot_config_is_parsed():
    config = parse_bot_config(
        api_config(
            mention_user_id="987",
            daily_summary_time="07:30",
            poll_interval_sec=3,
            notifications={"awaiting_user": False, "projects": ["a", "b"]},
        )
    )

    assert config.missing() == []
    assert config.channel_id == 123456789012345678
    assert config.mention_user_id == 987
    assert config.summary_time.replace(tzinfo=None) == time(7, 30)
    assert str(config.summary_time.tzinfo) == "Asia/Tokyo"
    assert config.poll_interval_sec == 10
    assert config.notifications.awaiting_user is False
    assert config.notifications.failed_runs is True
    assert config.notifications.projects == frozenset({"a", "b"})


def test_bot_config_reports_missing_items():
    config = parse_bot_config(api_config(bot_token="", channel_id=""))

    assert config.missing() == ["Bot トークン", "通知チャンネル ID"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"channel_id": "#general"},
        {"daily_summary_time": "8時"},
        {"poll_interval_sec": "fast"},
        {"time_zone": "Mars/Base"},
    ],
)
def test_invalid_values_raise_config_error(overrides):
    with pytest.raises(ConfigError):
        parse_bot_config(api_config(**overrides))


def test_notification_options_project_filter():
    assert NotificationOptions().includes("anything")
    options = NotificationOptions(projects=frozenset({"a"}))
    assert options.includes("a")
    assert not options.includes("b")


class ConfigApi:
    def __init__(self, data=None, error=None):
        self.data = data
        self.error = error

    async def bot_config(self):
        if self.error:
            raise self.error
        return self.data


def test_load_config_explains_problems():
    config, problem = asyncio.run(load_config(ConfigApi(error=RuntimeError("down"))))
    assert config is None and "読めませんでした" in problem

    config, problem = asyncio.run(load_config(ConfigApi(api_config(channel_id="x"))))
    assert config is None and "正しくありません" in problem

    config, problem = asyncio.run(load_config(ConfigApi(api_config(bot_token=""))))
    assert config is not None and "Bot トークン" in problem

    config, problem = asyncio.run(load_config(ConfigApi(api_config())))
    assert problem == ""


def test_test_request_while_disconnected_is_answered_once(tmp_path):
    store = StateStore(tmp_path / "state.json")
    config = parse_bot_config(api_config(test_requested_at="2026-09-30T10:00:00+09:00"))

    first = _mark_test_unavailable(store, config, "未入力")
    second = _mark_test_unavailable(store, config, "未入力")

    assert first["test_handled_at"] == "2026-09-30T10:00:00+09:00"
    assert "接続していません" in first["test_error"]
    assert second == {}


def test_long_note_is_truncated_to_discord_limit():
    notice = AwaitingNotice("A-1", "title", "PJ", note="長い" * 3000)

    message = format_awaiting(notice)

    assert len(message) <= DISCORD_MESSAGE_LIMIT
    assert message.endswith("…")


def test_test_message_lists_current_options():
    message = format_test_message(
        123, NotificationOptions(failed_runs=False, projects=frozenset({"b", "a"}))
    )

    assert message.startswith("<@123> ✅ **テスト通知**")
    assert "自動実行の失敗 OFF" in message
    assert "対象：a、b" in message
