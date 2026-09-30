import httpx


# ページ送りの上限。通知用途では数ページで足りるため、暴走だけ防ぐ。
MAX_PAGES = 10


class DashboardApi:
    """ダッシュボード API のクライアント（discord スコープ）。

    書き込むのは bot 自身の接続状態の報告（POST discord/status/）だけ。
    """

    def __init__(self, base_url, api_key, client=None):
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            headers={"Authorization": f"Api-Key {api_key}"},
            timeout=15,
        )

    async def aclose(self):
        await self._client.aclose()

    async def _get(self, path, params=None):
        response = await self._client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    async def bot_config(self):
        return await self._get("discord/config/")

    async def report_status(self, state, detail="", bot_user="", test_handled_at="", test_error=""):
        response = await self._client.post(
            "discord/status/",
            json={
                "state": state,
                "detail": detail[:1000],
                "bot_user": bot_user[:200],
                "test_handled_at": test_handled_at or "",
                "test_error": (test_error or "")[:1000],
            },
        )
        response.raise_for_status()

    async def events(self, after=None, limit=100):
        params = {"limit": limit}
        if after is not None:
            params["after"] = after
        return await self._get("events/", params)

    async def runs(self, ended_after, status=None):
        params = {"ended_after": ended_after.isoformat()}
        if status:
            params["status"] = status
        results = []
        page = await self._get("runs/", params)
        for _ in range(MAX_PAGES):
            results.extend(page["results"])
            if not page.get("next"):
                break
            page = await self._get(page["next"])
        return results

    async def summary(self):
        return await self._get("dashboard/summary/")
