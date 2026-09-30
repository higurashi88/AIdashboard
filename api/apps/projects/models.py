import uuid

from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q


class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=64, unique=True)
    code = models.CharField(
        max_length=12,
        unique=True,
        validators=[RegexValidator(r"^[A-Z0-9]+$", "半角英大文字と数字で入力してください")],
    )
    name = models.CharField(max_length=120)
    root_path = models.TextField()
    summary = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    sort_order = models.SmallIntegerField(default=0)
    is_pinned = models.BooleanField(default=False)
    color = models.CharField(
        max_length=7,
        default="#64748B",
        validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$", "#RRGGBB形式で入力してください")],
    )
    extra = models.JSONField(default=dict, blank=True)
    next_task_number = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(next_task_number__gte=1),
                name="project_next_task_number_gte_1",
            )
        ]
        verbose_name = "プロジェクト"
        verbose_name_plural = "プロジェクト"

    def __str__(self):
        return f"{self.name} ({self.code})"


class Repository(models.Model):
    """ホスト上のローカル Git リポジトリと、その最新の状態。

    状態はホスト側の scripts/collect_repo_status.ps1 が集めて送る。
    API（コンテナ）からホストのファイルは見えないため、ここでは受け取った値を保存するだけ。
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="repositories",
    )
    name = models.CharField(max_length=120)
    path = models.CharField(max_length=500, unique=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.SmallIntegerField(default=0)

    branch = models.CharField(max_length=255, blank=True)
    upstream = models.CharField(max_length=255, blank=True)
    ahead = models.PositiveIntegerField(null=True, blank=True)
    behind = models.PositiveIntegerField(null=True, blank=True)
    changed_files = models.PositiveIntegerField(null=True, blank=True)
    untracked_files = models.PositiveIntegerField(null=True, blank=True)
    last_commit_at = models.DateTimeField(null=True, blank=True)
    last_commit_sha = models.CharField(max_length=64, blank=True)
    last_commit_subject = models.CharField(max_length=500, blank=True)
    status_error = models.TextField(blank=True)
    collected_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "リポジトリ"
        verbose_name_plural = "リポジトリ"

    def __str__(self):
        return f"{self.name} ({self.path})"
