"""Discord bot の設定を .env（コンテナの環境変数）から設定画面の保存先へ1回だけ取り込む。

これまで discord-bot は .env の DISCORD_* を直接読んでいた。設定画面へ移すときに
入れ直さなくて済むよう、api コンテナに渡っている同じ値を初回の migrate で取り込む。
既に保存済みのキーは上書きしない。環境変数が無ければ何もしない（テスト DB など）。
"""

import os

from django.db import migrations


ENV_TO_KEY = {
    "DISCORD_BOT_TOKEN": "discord.bot_token",
    "DISCORD_CHANNEL_ID": "discord.channel_id",
    "DISCORD_MENTION_USER_ID": "discord.mention_user_id",
    "DISCORD_DAILY_SUMMARY_TIME": "discord.daily_summary_time",
    "DISCORD_POLL_INTERVAL_SEC": "discord.poll_interval_sec",
}


def import_from_env(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")
    for env_name, key in ENV_TO_KEY.items():
        raw = os.environ.get(env_name, "").strip()
        if not raw:
            continue
        value = raw
        if key == "discord.poll_interval_sec":
            if not raw.isdigit():
                continue
            value = max(int(raw), 10)
        AppSetting.objects.get_or_create(key=key, defaults={"value": value})


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_app_settings"),
    ]

    operations = [
        migrations.RunPython(import_from_env, migrations.RunPython.noop),
    ]
