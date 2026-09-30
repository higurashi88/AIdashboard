import uuid

from django.db import models


class ApiKey(models.Model):
    class Scope(models.TextChoices):
        MCP = "mcp", "MCP"
        PIPELINE = "pipeline", "Pipeline"
        WEB = "web", "Web"
        DISCORD = "discord", "Discord"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    key_hash = models.CharField(max_length=64, unique=True, editable=False)
    prefix = models.CharField(max_length=8, db_index=True, editable=False)
    scope = models.CharField(max_length=16, choices=Scope.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name", "created_at"]
        verbose_name = "APIキー"
        verbose_name_plural = "APIキー"

    def __str__(self):
        return f"{self.name} ({self.prefix}..., {self.scope})"


class AppSetting(models.Model):
    """画面から編集する設定値（キーごとに1行）。

    どのキーがあり、どう検証するかは apps/services/app_settings.py の定義が決める。
    起動やセキュリティ境界に関わる値（DB 接続・SECRET_KEY・許可ホストなど）はここに置かず、.env に残す。
    """

    key = models.CharField(max_length=64, primary_key=True)
    value = models.JSONField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]
        verbose_name = "設定"
        verbose_name_plural = "設定"

    def __str__(self):
        return self.key
