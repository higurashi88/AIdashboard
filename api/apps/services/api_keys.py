import hashlib
import secrets

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.models import ApiKey


@transaction.atomic
def create_api_key(name, scope):
    if scope not in ApiKey.Scope.values:
        raise ValidationError({"scope": f"Unknown API key scope: {scope}"})
    raw_key = f"pdb_{secrets.token_urlsafe(32)}"
    api_key = ApiKey(
        name=name,
        key_hash=hashlib.sha256(raw_key.encode("utf-8")).hexdigest(),
        prefix=raw_key[:8],
        scope=scope,
    )
    api_key.full_clean()
    api_key.save(force_insert=True)
    return api_key, raw_key


class ApiKeyResolutionError(Exception):
    pass


def list_api_keys():
    return list(ApiKey.objects.order_by("-is_active", "scope", "name", "created_at"))


@transaction.atomic
def update_api_key(key_id, current_key_id=None, **changes):
    try:
        api_key = ApiKey.objects.select_for_update().get(pk=key_id)
    except (ApiKey.DoesNotExist, ValidationError) as exc:
        raise ApiKeyResolutionError(f"API key could not be resolved: {key_id}") from exc
    if changes.get("is_active") is False and current_key_id is not None and api_key.pk == current_key_id:
        # 画面が使っているキー（DASHBOARD_WEB_API_KEY）を止めると、画面ごと使えなくなる
        raise ValidationError(
            {"is_active": "この画面が使っているキーは無効化できません（.env の DASHBOARD_WEB_API_KEY）"}
        )
    if "name" in changes:
        name = str(changes["name"]).strip()
        if not name:
            raise ValidationError({"name": "名前を入力してください"})
        api_key.name = name
    if "is_active" in changes:
        api_key.is_active = changes["is_active"]
    api_key.full_clean()
    api_key.save(update_fields=["name", "is_active"])
    return api_key
