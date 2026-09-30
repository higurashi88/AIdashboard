import hashlib
import json

from asgiref.sync import sync_to_async
from django.db import connections
from django.utils import timezone

from apps.core.models import ApiKey


class McpAuthenticationError(Exception):
    status_code = 401
    error_code = -32001


class McpScopeError(McpAuthenticationError):
    status_code = 403
    error_code = -32003


def _authenticate_mcp_headers(headers):
    authorization = None
    for name, value in headers:
        if name.lower() == b"authorization":
            authorization = value
            break
    if authorization is None:
        raise McpAuthenticationError(
            "MCP認証が必要です。Authorization: Api-Key <KEY> を指定してください。"
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != b"api-key":
        raise McpAuthenticationError(
            "認証ヘッダの形式が不正です。Authorization: Api-Key <KEY> を指定してください。"
        )
    try:
        raw_key = parts[1].decode("ascii")
    except UnicodeDecodeError as exc:
        raise McpAuthenticationError(
            "APIキーにはASCII文字だけを使用してください。"
        ) from exc

    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    try:
        api_key = ApiKey.objects.get(key_hash=key_hash, is_active=True)
    except ApiKey.DoesNotExist as exc:
        raise McpAuthenticationError(
            "APIキーが無効または停止中です。MCP用キーを確認してください。"
        ) from exc
    if api_key.scope != ApiKey.Scope.MCP:
        raise McpScopeError(
            "このAPIキーはMCPスコープではありません。mcpスコープのキーを使用してください。"
        )

    now = timezone.now()
    ApiKey.objects.filter(pk=api_key.pk).update(last_used_at=now)
    api_key.last_used_at = now
    return api_key


def authenticate_mcp_headers(headers):
    try:
        return _authenticate_mcp_headers(headers)
    finally:
        # MCP runs ORM work in a dedicated sync thread, outside Django's request cleanup.
        connections.close_all()


class McpApiKeyMiddleware:
    def __init__(self, application):
        self.application = application

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.application(scope, receive, send)
            return
        try:
            await sync_to_async(
                authenticate_mcp_headers,
                thread_sensitive=True,
            )(scope.get("headers", []))
        except McpAuthenticationError as exc:
            await self._send_error(send, exc)
            return
        await self.application(scope, receive, send)

    @staticmethod
    async def _send_error(send, exc):
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": exc.error_code,
                    "message": str(exc),
                },
            },
            ensure_ascii=False,
        ).encode("utf-8")
        headers = [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"content-length", str(len(body)).encode("ascii")),
            (b"cache-control", b"no-store"),
        ]
        if exc.status_code == 401:
            headers.append((b"www-authenticate", b"Api-Key"))
        await send(
            {
                "type": "http.response.start",
                "status": exc.status_code,
                "headers": headers,
            }
        )
        await send({"type": "http.response.body", "body": body})
