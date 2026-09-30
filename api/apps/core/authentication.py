import hashlib
import os
from dataclasses import dataclass

from django.core.cache import cache
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed, Throttled

from apps.core.models import ApiKey


@dataclass(frozen=True)
class ApiKeyPrincipal:
    api_key: ApiKey

    @property
    def id(self):
        return self.api_key.pk

    @property
    def pk(self):
        # DRF の UserRateThrottle が request.user.pk でキャッシュキーを作るため必要。
        # 無いと認証済みリクエストのスロットリングで AttributeError になる。
        return self.api_key.pk

    @property
    def name(self):
        return self.api_key.name

    @property
    def scope(self):
        return self.api_key.scope

    @property
    def is_authenticated(self):
        return True


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        # nginx が付与する。最も左が元のクライアント。
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


class ApiKeyAuthentication(BaseAuthentication):
    """`Authorization: Api-Key <key>` を検証する。

    DRF の throttle は認証成功後にしか走らないため、
    APIキーの総当たりはここで直接抑止する（失敗回数をIP単位で数える）。

    注意: 既定のキャッシュ（LocMemCache）はプロセスごとに独立しているため、
    実効的な上限は API_KEY_FAILURE_LIMIT × ワーカー数になる。
    ローカル運用では十分だが、外部公開する場合は共有キャッシュ（Redis 等）を
    設定するか、ワーカー数を考慮して上限を下げること。
    """

    keyword = b"api-key"

    @property
    def failure_limit(self):
        return int(os.getenv("API_KEY_FAILURE_LIMIT", "10"))

    @property
    def failure_window(self):
        return int(os.getenv("API_KEY_FAILURE_WINDOW_SEC", "300"))

    def failure_cache_key(self, request):
        return f"apikey-failures:{client_ip(request)}"

    def guard_brute_force(self, request):
        """上限を超えていれば 429 を返す。認証を試みる前に呼ぶ。"""
        count = cache.get(self.failure_cache_key(request), 0)
        if count >= self.failure_limit:
            raise Throttled(
                wait=self.failure_window,
                detail=(
                    "APIキーの認証失敗が続いたため、一時的にブロックしています。"
                    f"{self.failure_window}秒ほど待ってから再試行してください。"
                ),
            )

    def record_failure(self, request):
        key = self.failure_cache_key(request)
        try:
            # add は既存キーがあれば何もしない。TTL を延ばさずに窓を固定するため。
            cache.add(key, 0, self.failure_window)
            cache.incr(key)
        except ValueError:
            # incr の直前に TTL 切れでキーが消えた場合
            cache.set(key, 1, self.failure_window)

    def reject(self, request, message):
        self.record_failure(request)
        raise AuthenticationFailed(message)

    def authenticate(self, request):
        authorization = get_authorization_header(request).split()
        if not authorization:
            return None
        if authorization[0].lower() != self.keyword:
            return None

        self.guard_brute_force(request)

        if len(authorization) != 2:
            self.reject(request, "Authorization header must be: Api-Key <key>")

        try:
            raw_key = authorization[1].decode("ascii")
        except UnicodeDecodeError:
            self.reject(request, "The API key must contain ASCII characters only")

        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        try:
            api_key = ApiKey.objects.get(key_hash=key_hash, is_active=True)
        except ApiKey.DoesNotExist:
            self.reject(request, "Invalid or inactive API key")

        # 正しいキーが通ったら、そのIPの失敗カウントは解除する
        cache.delete(self.failure_cache_key(request))

        now = timezone.now()
        ApiKey.objects.filter(pk=api_key.pk).update(last_used_at=now)
        api_key.last_used_at = now
        return ApiKeyPrincipal(api_key), api_key

    def authenticate_header(self, request):
        return "Api-Key"
