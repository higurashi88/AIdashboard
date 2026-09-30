import uuid

from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Task(models.Model):
    class Status(models.TextChoices):
        BACKLOG = "backlog", "バックログ"
        TODO = "todo", "未着手"
        IN_PROGRESS = "in_progress", "作業中"
        AWAITING_USER = "awaiting_user", "本人待ち"
        BLOCKED = "blocked", "ブロック中"
        DONE = "done", "完了"
        CANCELLED = "cancelled", "取りやめ"

    class Priority(models.IntegerChoices):
        NONE = 0, "なし"
        LOW = 1, "低"
        MEDIUM = 2, "中"
        HIGH = 3, "高"

    class ActorType(models.TextChoices):
        AGENT = "agent", "AI"
        HUMAN = "human", "人間"

    class Actor(models.TextChoices):
        HUMAN = "human", "Human"
        CLAUDE_CODE = "claude_code", "Claude Code"
        CODEX = "codex", "Codex"
        AUTOMATION = "automation", "Automation"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    number = models.PositiveIntegerField()
    key = models.CharField(max_length=24, unique=True, editable=False)
    title = models.CharField(max_length=255)
    detail = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.TODO)
    priority = models.PositiveSmallIntegerField(choices=Priority.choices, default=Priority.NONE)
    actor_type = models.CharField(
        max_length=16,
        choices=ActorType.choices,
        default=ActorType.AGENT,
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subtasks",
    )
    created_by = models.CharField(max_length=16, choices=Actor.choices, default=Actor.HUMAN)
    origin_session = models.ForeignKey(
        "dashboard_sessions.Session",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_tasks",
    )
    due_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    tags = ArrayField(models.CharField(max_length=64), default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-priority", "-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["project", "number"], name="task_project_number_uniq"),
            models.CheckConstraint(
                condition=Q(priority__gte=0, priority__lte=3),
                name="task_priority_between_0_3",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "-updated_at"], name="task_status_updated_idx"),
            models.Index(fields=["project", "status"], name="task_project_status_idx"),
        ]
        verbose_name = "タスク"
        verbose_name_plural = "タスク"

    def __str__(self):
        return f"{self.key}: {self.title}"


class TaskEvent(models.Model):
    class EventType(models.TextChoices):
        CREATED = "created", "作成"
        STATUS_CHANGED = "status_changed", "ステータス変更"
        NOTE = "note", "メモ"
        EDITED = "edited", "編集"

    id = models.BigAutoField(primary_key=True)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="events")
    session = models.ForeignKey(
        "dashboard_sessions.Session",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_events",
    )
    event_type = models.CharField(max_length=24, choices=EventType.choices)
    actor = models.CharField(max_length=16, choices=Task.Actor.choices)
    body = models.TextField(blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(fields=["task", "-occurred_at"], name="task_event_task_at_idx"),
            models.Index(fields=["-occurred_at"], name="task_event_at_idx"),
        ]
        verbose_name = "タスクイベント"
        verbose_name_plural = "タスクイベント"

    def __str__(self):
        return f"{self.task.key} {self.event_type} @ {self.occurred_at.isoformat()}"
