"""画面から編集する設定値の読み書き。

値は AppSetting（キーごとに1行）に保存し、未保存のキーは DEFAULTS の値を返す。
入力の検証は API のシリアライザで行い、ここでは保存と組み立てだけを受け持つ。
"""

from django.conf import settings as django_settings
from django.db import transaction
from django.utils import timezone

from apps.core.models import AppSetting


DISCORD_BOT_TOKEN = "discord.bot_token"
DISCORD_CHANNEL_ID = "discord.channel_id"
DISCORD_MENTION_USER_ID = "discord.mention_user_id"
DISCORD_DAILY_SUMMARY_TIME = "discord.daily_summary_time"
DISCORD_POLL_INTERVAL_SEC = "discord.poll_interval_sec"
NOTIFY_AWAITING_USER = "notify.awaiting_user"
NOTIFY_FAILED_RUNS = "notify.failed_runs"
NOTIFY_DAILY_SUMMARY = "notify.daily_summary"
NOTIFY_PROJECTS = "notify.projects"
BACKUP_KEEP = "backup.keep"

# 画面からは編集しない内部の値（bot との受け渡し用）
DISCORD_STATUS = "discord.status"
DISCORD_TEST_REQUESTED_AT = "discord.test_requested_at"

DEFAULTS = {
    DISCORD_BOT_TOKEN: "",
    DISCORD_CHANNEL_ID: "",
    DISCORD_MENTION_USER_ID: "",
    DISCORD_DAILY_SUMMARY_TIME: "08:00",
    DISCORD_POLL_INTERVAL_SEC: 60,
    NOTIFY_AWAITING_USER: True,
    NOTIFY_FAILED_RUNS: True,
    NOTIFY_DAILY_SUMMARY: True,
    # 空なら全プロジェクトを通知する
    NOTIFY_PROJECTS: [],
    BACKUP_KEEP: 7,
    DISCORD_STATUS: None,
    DISCORD_TEST_REQUESTED_AT: None,
}

# API のグループ名・項目名と保存キーの対応
GROUPS = {
    "discord": {
        "bot_token": DISCORD_BOT_TOKEN,
        "channel_id": DISCORD_CHANNEL_ID,
        "mention_user_id": DISCORD_MENTION_USER_ID,
        "daily_summary_time": DISCORD_DAILY_SUMMARY_TIME,
        "poll_interval_sec": DISCORD_POLL_INTERVAL_SEC,
    },
    "notifications": {
        "awaiting_user": NOTIFY_AWAITING_USER,
        "failed_runs": NOTIFY_FAILED_RUNS,
        "daily_summary": NOTIFY_DAILY_SUMMARY,
        "projects": NOTIFY_PROJECTS,
    },
    "backup": {
        "keep": BACKUP_KEEP,
    },
}

# 画面に表示するトークンの末尾の文字数
SECRET_HINT_LENGTH = 4


def get_values(keys=None):
    keys = list(DEFAULTS) if keys is None else list(keys)
    values = {key: DEFAULTS[key] for key in keys}
    for setting in AppSetting.objects.filter(key__in=keys):
        values[setting.key] = setting.value
    return values


def get_value(key):
    return get_values([key])[key]


def _latest_updated_at(keys):
    return (
        AppSetting.objects.filter(key__in=keys)
        .order_by("-updated_at")
        .values_list("updated_at", flat=True)
        .first()
    )


@transaction.atomic
def set_values(values):
    unknown = set(values) - set(DEFAULTS)
    if unknown:
        raise KeyError(f"Unknown setting keys: {', '.join(sorted(unknown))}")
    for key, value in values.items():
        AppSetting.objects.update_or_create(key=key, defaults={"value": value})


def update_groups(changes):
    """{"discord": {"channel_id": "..."}, ...} の形の変更を保存する（省略した項目は変えない）。"""
    flat = {}
    for group, fields in changes.items():
        for field, value in fields.items():
            flat[GROUPS[group][field]] = value
    set_values(flat)


def _secret_hint(value):
    value = value or ""
    if not value:
        return ""
    return value[-SECRET_HINT_LENGTH:]


def settings_for_web():
    values = get_values()
    token = values[DISCORD_BOT_TOKEN]
    editable_keys = [key for group in GROUPS.values() for key in group.values()]
    return {
        "discord": {
            "bot_token_set": bool(token),
            "bot_token_hint": _secret_hint(token),
            "channel_id": values[DISCORD_CHANNEL_ID],
            "mention_user_id": values[DISCORD_MENTION_USER_ID],
            "daily_summary_time": values[DISCORD_DAILY_SUMMARY_TIME],
            "poll_interval_sec": values[DISCORD_POLL_INTERVAL_SEC],
        },
        "notifications": {
            "awaiting_user": values[NOTIFY_AWAITING_USER],
            "failed_runs": values[NOTIFY_FAILED_RUNS],
            "daily_summary": values[NOTIFY_DAILY_SUMMARY],
            "projects": values[NOTIFY_PROJECTS],
        },
        "backup": {
            "keep": values[BACKUP_KEEP],
        },
        "discord_status": discord_status(values),
        "time_zone": django_settings.TIME_ZONE,
        "updated_at": _latest_updated_at(editable_keys),
    }


def discord_status(values=None):
    values = values or get_values([DISCORD_STATUS, DISCORD_TEST_REQUESTED_AT])
    status = values[DISCORD_STATUS] or {}
    return {
        "state": status.get("state", "unknown"),
        "detail": status.get("detail", ""),
        "bot_user": status.get("bot_user", ""),
        "reported_at": status.get("reported_at"),
        "test_requested_at": values[DISCORD_TEST_REQUESTED_AT],
        "test_handled_at": status.get("test_handled_at"),
        "test_error": status.get("test_error", ""),
    }


def discord_config_for_bot():
    values = get_values()
    return {
        "bot_token": values[DISCORD_BOT_TOKEN],
        "channel_id": values[DISCORD_CHANNEL_ID],
        "mention_user_id": values[DISCORD_MENTION_USER_ID],
        "daily_summary_time": values[DISCORD_DAILY_SUMMARY_TIME],
        "poll_interval_sec": values[DISCORD_POLL_INTERVAL_SEC],
        "time_zone": django_settings.TIME_ZONE,
        "notifications": {
            "awaiting_user": values[NOTIFY_AWAITING_USER],
            "failed_runs": values[NOTIFY_FAILED_RUNS],
            "daily_summary": values[NOTIFY_DAILY_SUMMARY],
            "projects": values[NOTIFY_PROJECTS],
        },
        "test_requested_at": values[DISCORD_TEST_REQUESTED_AT],
    }


def record_discord_status(state, detail="", bot_user="", test_handled_at=None, test_error=""):
    previous = get_value(DISCORD_STATUS) or {}
    status = {
        "state": state,
        "detail": detail,
        "bot_user": bot_user,
        "reported_at": timezone.now().isoformat(),
        # テスト送信の結果は、次のテストを処理するまで残す
        "test_handled_at": previous.get("test_handled_at"),
        "test_error": previous.get("test_error", ""),
    }
    if test_handled_at:
        # bot は処理したテスト依頼の test_requested_at をそのまま返す。画面は一致で完了を判定する。
        status["test_handled_at"] = test_handled_at
        status["test_error"] = test_error
    set_values({DISCORD_STATUS: status})
    return discord_status()


def request_discord_test():
    set_values({DISCORD_TEST_REQUESTED_AT: timezone.now().isoformat()})
    return discord_status()
