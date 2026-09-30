import uuid

from django.db import models


class Automation(models.Model):
    class State(models.TextChoices):
        ACTIVE = "active", "稼働中"
        PAUSED = "paused", "停止中"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=120, blank=True, default="")
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="automations",
    )
    scheduled_task_name = models.CharField(max_length=255, blank=True)
    schedule_human = models.CharField(max_length=120, blank=True)
    script_path = models.TextField(blank=True)
    state = models.CharField(max_length=16, choices=State.choices, default=State.ACTIVE)

    class Meta:
        ordering = ["project__sort_order", "key"]
        verbose_name = "自動化"
        verbose_name_plural = "自動化"

    def __str__(self):
        return self.key


class Run(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "実行中"
        SUCCEEDED = "succeeded", "成功"
        FAILED = "failed", "失敗"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    automation = models.ForeignKey(
        Automation,
        on_delete=models.CASCADE,
        related_name="runs",
    )
    run_key = models.CharField(max_length=128, unique=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING)
    trigger = models.CharField(max_length=32)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_sec = models.PositiveIntegerField(null=True, blank=True)
    exit_code = models.IntegerField(null=True, blank=True)
    log_path = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    metrics = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["status", "-started_at"], name="run_status_started_idx"),
        ]
        verbose_name = "実行記録"
        verbose_name_plural = "実行記録"

    def __str__(self):
        return self.run_key
