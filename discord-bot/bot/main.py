import argparse
import asyncio
import logging
import sys
import time

import discord
from discord.ext import tasks

from bot.api import DashboardApi
from bot.config import ConfigError, load_bootstrap, parse_bot_config
from bot.service import NotificationService
from bot.state import StateStore


logger = logging.getLogger("bot")

# 判断事項のメモなどに @everyone が書かれていても全員へ通知しない。
ALLOWED_MENTIONS = discord.AllowedMentions(
    everyone=False,
    roles=False,
    users=True,
    replied_user=False,
)

# Discord への接続が想定外の理由で切れたときに、つなぎ直すまで待つ秒数
RECONNECT_DELAY_SEC = 30


async def load_config(api):
    """設定画面の値を読む。

    戻り値: (BotConfig または None, 接続できない理由)。理由が空なら接続してよい。
    """
    try:
        data = await api.bot_config()
    except Exception as exc:
        return None, f"ダッシュボードから設定を読めませんでした: {exc}"
    try:
        config = parse_bot_config(data)
    except ConfigError as exc:
        return None, f"設定画面の値が正しくありません: {exc}"
    missing = config.missing()
    if missing:
        return config, f"設定画面で未入力の項目があります: {'、'.join(missing)}"
    return config, ""


class StatusReporter:
    """接続状態を設定画面へ報告する。報告に失敗しても通知は止めない。"""

    def __init__(self, api):
        self.api = api
        self._last = None

    async def report(self, state, detail="", bot_user="", test_handled_at="", test_error=""):
        if (state, detail) != self._last:
            log = logger.warning if state in {"waiting_config", "login_failed", "channel_error", "error"} else logger.info
            log("状態: %s %s", state, detail)
            self._last = (state, detail)
        try:
            await self.api.report_status(
                state,
                detail=detail,
                bot_user=bot_user,
                test_handled_at=test_handled_at,
                test_error=test_error,
            )
        except Exception as exc:
            logger.warning("接続状態を報告できませんでした: %s", exc)


class DashboardBot(discord.Client):
    """ダッシュボードの変化を Discord に投稿する bot（タスクの書き込みはしない）。

    設定画面の変更は config_loop で読み直す。トークンが変わったときだけ接続を閉じ、
    呼び出し元（run_forever）が新しいトークンでつなぎ直す。
    """

    def __init__(self, config, api, store, reporter, refresh_sec):
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(intents=intents, allowed_mentions=ALLOWED_MENTIONS)
        self.config = config
        self.api = api
        self.reporter = reporter
        self.service = NotificationService(
            api=api,
            store=store,
            send=self.send_to_channel,
            time_zone=config.time_zone,
            mention_user_id=config.mention_user_id,
            options=config.notifications,
        )
        self.poll_loop = tasks.loop(seconds=config.poll_interval_sec)(self._poll)
        self.summary_loop = tasks.loop(time=config.summary_time)(self._daily_summary)
        self.config_loop = tasks.loop(seconds=refresh_sec)(self._refresh_config)
        self._channel = None
        self.channel_problem = ""
        self.restart_reason = ""

    async def setup_hook(self):
        self.poll_loop.start()
        self.summary_loop.start()
        self.config_loop.start()

    async def close(self):
        self.poll_loop.cancel()
        self.summary_loop.cancel()
        # 自分自身の中から close を呼ぶことがあるため、config_loop は cancel せず止めるだけ
        self.config_loop.stop()
        await super().close()

    async def on_ready(self):
        logger.info("Discord に接続しました: %s", self.user)
        await self._check_channel()
        await self._report()

    async def _resolve_channel(self):
        channel_id = self.config.channel_id
        channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)
        if not hasattr(channel, "send"):
            raise ValueError("テキストチャンネルではありません")
        return channel

    async def _check_channel(self):
        try:
            self._channel = await self._resolve_channel()
            self.channel_problem = ""
        except (discord.DiscordException, ValueError) as exc:
            self._channel = None
            self.channel_problem = (
                f"チャンネル {self.config.channel_id} に投稿できません"
                f"（ID が正しいか、bot をサーバーに招待したかを確認）: {exc}"
            )

    async def send_to_channel(self, content):
        if self._channel is None:
            self._channel = await self._resolve_channel()
        await self._channel.send(content)

    async def _report(self, **test_result):
        user = str(self.user) if self.user else ""
        if self.channel_problem:
            await self.reporter.report("channel_error", self.channel_problem, user, **test_result)
        else:
            await self.reporter.report("connected", "", user, **test_result)

    async def _poll(self):
        await self.wait_until_ready()
        await self.service.poll()

    async def _daily_summary(self):
        await self.wait_until_ready()
        try:
            await self.service.daily_summary()
        except Exception:
            logger.exception("朝のまとめの送信に失敗しました")

    async def _refresh_config(self):
        await self.wait_until_ready()
        try:
            config, problem = await load_config(self.api)
            if config is None:
                # API が一時的に止まっているだけなら、今の設定のまま動き続ける
                logger.warning("%s（今の設定のまま続けます）", problem)
                return
            if problem or config.token != self.config.token:
                self.restart_reason = problem or "Bot トークンが変わったため接続し直します"
                logger.info(self.restart_reason)
                await self.close()
                return
            await self._apply(config)
            test_result = {}
            handled = await self.service.handle_test_request(config.test_requested_at)
            if handled is not None:
                test_result = {"test_handled_at": handled[0], "test_error": handled[1]}
            await self._report(**test_result)
        except Exception:
            logger.exception("設定の読み直しに失敗しました")

    async def _apply(self, config):
        previous = self.config
        self.config = config
        self.service.apply(config)
        if config.poll_interval_sec != previous.poll_interval_sec:
            self.poll_loop.change_interval(seconds=config.poll_interval_sec)
            logger.info("確認間隔を %s 秒にしました", config.poll_interval_sec)
        if config.summary_time != previous.summary_time:
            self.summary_loop.change_interval(time=config.summary_time)
            logger.info("朝のまとめの時刻を %s にしました", config.summary_time.strftime("%H:%M"))
        if config.channel_id != previous.channel_id or self.channel_problem:
            self._channel = None
            await self._check_channel()


def _mark_test_unavailable(store, config, reason):
    """接続していない間に押されたテスト送信に、送れなかった理由を返す。"""
    requested_at = config.test_requested_at if config else None
    if not requested_at:
        return {}
    state = store.load()
    if state.last_test_request == requested_at:
        return {}
    state.last_test_request = requested_at
    store.save(state)
    return {"test_handled_at": requested_at, "test_error": f"bot が Discord に接続していません: {reason}"}


async def run_forever(bootstrap):
    """設定を読み、Discord への接続を張り直しながら動き続ける。"""
    api = DashboardApi(bootstrap.api_url, bootstrap.api_key)
    reporter = StatusReporter(api)
    store = StateStore(bootstrap.state_path)
    rejected_token = None
    try:
        while True:
            config, problem = await load_config(api)
            if config is not None and not problem and config.token == rejected_token:
                problem = "Bot トークンが Discord に拒否されました。設定画面で入れ直してください"
                state = "login_failed"
            else:
                state = "waiting_config"
            if problem:
                if config is not None:
                    await reporter.report(state, problem, **_mark_test_unavailable(store, config, problem))
                else:
                    logger.warning(problem)
                await asyncio.sleep(bootstrap.config_refresh_sec)
                continue

            rejected_token = None
            await reporter.report("connecting")
            client = DashboardBot(config, api, store, reporter, bootstrap.config_refresh_sec)
            try:
                async with client:
                    await client.start(config.token)
            except discord.LoginFailure:
                rejected_token = config.token
                continue
            except Exception as exc:
                logger.exception("Discord への接続でエラーが起きました")
                await reporter.report("error", f"Discord への接続でエラーが起きました: {exc}")
                await asyncio.sleep(RECONNECT_DELAY_SEC)
                continue
            logger.info("接続を閉じました: %s", client.restart_reason or "終了")
    finally:
        await api.aclose()


async def check(bootstrap):
    """Discord には接続せず、設定とダッシュボード API への疎通だけを確認する。"""
    api = DashboardApi(bootstrap.api_url, bootstrap.api_key)
    try:
        config, problem = await load_config(api)
        if config is None:
            print(problem)
            return 1
        feed = await api.events()
        summary = await api.summary()
    finally:
        await api.aclose()
    print(f"API OK: 最新イベントID={feed['next_after']} 判断待ち={len(summary['awaiting_user'])}件")
    if problem:
        print(problem)
        return 1
    print(f"設定 OK: チャンネル={config.channel_id} 朝のまとめ={config.summary_time:%H:%M}")
    return 0


async def send_summary_now(bootstrap):
    """朝のまとめを今すぐ1回だけ送る（動作確認用）。"""
    api = DashboardApi(bootstrap.api_url, bootstrap.api_key)
    client = discord.Client(intents=discord.Intents.none(), allowed_mentions=ALLOWED_MENTIONS)
    try:
        config, problem = await load_config(api)
        if problem:
            print(problem)
            return 2
        await client.login(config.token)
        channel = await client.fetch_channel(config.channel_id)
        service = NotificationService(
            api=api,
            store=StateStore(bootstrap.state_path),
            send=channel.send,
            time_zone=config.time_zone,
            options=config.notifications,
        )
        await service.daily_summary(force=True)
    finally:
        await api.aclose()
        await client.close()
    print("朝のまとめを送信しました")
    return 0


def main(argv=None):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # 設定を15秒ごとに読み直すため、リクエストごとのログはログを埋めるだけになる
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(prog="python -m bot")
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["run", "check", "send-summary"],
        help="run=常駐（既定） / check=API疎通と設定の確認 / send-summary=まとめを今すぐ送信",
    )
    args = parser.parse_args(argv)

    try:
        bootstrap = load_bootstrap()
    except ConfigError as exc:
        logger.error("設定が正しくありません: %s", exc)
        return 2

    missing = bootstrap.missing()
    if missing:
        logger.error(
            "未設定の環境変数があります: %s（.env に設定して discord-bot を作り直してください）",
            ", ".join(missing),
        )
        if args.command != "run":
            return 2
        # 再起動ループでログを埋めないよう、設定されるまで止まったままにする。
        while True:
            time.sleep(3600)

    if args.command == "check":
        return asyncio.run(check(bootstrap))
    if args.command == "send-summary":
        return asyncio.run(send_summary_now(bootstrap))

    asyncio.run(run_forever(bootstrap))
    return 0


if __name__ == "__main__":
    sys.exit(main())
