import uuid

import django.contrib.postgres.fields
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("dashboard_sessions", "0001_initial"),
        ("projects", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Task",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("number", models.PositiveIntegerField()),
                ("key", models.CharField(editable=False, max_length=24, unique=True)),
                ("title", models.CharField(max_length=255)),
                ("detail", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("backlog", "バックログ"),
                            ("todo", "未着手"),
                            ("in_progress", "作業中"),
                            ("awaiting_user", "本人待ち"),
                            ("blocked", "ブロック中"),
                            ("done", "完了"),
                            ("cancelled", "取りやめ"),
                        ],
                        default="todo",
                        max_length=16,
                    ),
                ),
                (
                    "priority",
                    models.PositiveSmallIntegerField(
                        choices=[(0, "なし"), (1, "低"), (2, "中"), (3, "高")],
                        default=0,
                    ),
                ),
                (
                    "created_by",
                    models.CharField(
                        choices=[
                            ("human", "Human"),
                            ("claude_code", "Claude Code"),
                            ("codex", "Codex"),
                            ("automation", "Automation"),
                        ],
                        default="human",
                        max_length=16,
                    ),
                ),
                ("due_at", models.DateTimeField(blank=True, null=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "tags",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=64),
                        blank=True,
                        default=list,
                        size=None,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "origin_session",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_tasks",
                        to="dashboard_sessions.session",
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="subtasks",
                        to="tasks.task",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tasks",
                        to="projects.project",
                    ),
                ),
            ],
            options={
                "verbose_name": "タスク",
                "verbose_name_plural": "タスク",
                "ordering": ["-priority", "-updated_at"],
                "indexes": [
                    models.Index(
                        fields=["status", "-updated_at"],
                        name="task_status_updated_idx",
                    ),
                    models.Index(
                        fields=["project", "status"],
                        name="task_project_status_idx",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="TaskEvent",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("created", "作成"),
                            ("status_changed", "ステータス変更"),
                            ("note", "メモ"),
                            ("edited", "編集"),
                        ],
                        max_length=24,
                    ),
                ),
                (
                    "actor",
                    models.CharField(
                        choices=[
                            ("human", "Human"),
                            ("claude_code", "Claude Code"),
                            ("codex", "Codex"),
                            ("automation", "Automation"),
                        ],
                        max_length=16,
                    ),
                ),
                ("body", models.TextField(blank=True)),
                ("occurred_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("payload", models.JSONField(blank=True, default=dict)),
                (
                    "session",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="task_events",
                        to="dashboard_sessions.session",
                    ),
                ),
                (
                    "task",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="tasks.task",
                    ),
                ),
            ],
            options={
                "verbose_name": "タスクイベント",
                "verbose_name_plural": "タスクイベント",
                "ordering": ["-occurred_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["task", "-occurred_at"],
                        name="task_event_task_at_idx",
                    ),
                    models.Index(fields=["-occurred_at"], name="task_event_at_idx"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="task",
            constraint=models.UniqueConstraint(
                fields=("project", "number"),
                name="task_project_number_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="task",
            constraint=models.CheckConstraint(
                condition=models.Q(("priority__gte", 0), ("priority__lte", 3)),
                name="task_priority_between_0_3",
            ),
        ),
    ]
