import uuid

from django.db import models
from django.utils import timezone


class Session(models.Model):
    class Agent(models.TextChoices):
        CLAUDE_CODE = "claude_code", "Claude Code"
        CODEX = "codex", "Codex"
        HUMAN = "human", "Human"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    external_id = models.CharField(max_length=128, unique=True, null=True, blank=True)
    agent = models.CharField(max_length=16, choices=Agent.choices, default=Agent.CLAUDE_CODE)
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
    )
    run = models.ForeignKey(
        "automations.Run",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
    )
    tasks = models.ManyToManyField(
        "tasks.Task",
        blank=True,
        related_name="sessions",
    )
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    summary = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["project", "-started_at"], name="session_project_started_idx")]
        verbose_name = "セッション"
        verbose_name_plural = "セッション"

    def __str__(self):
        return self.external_id or str(self.pk)
