import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("projects", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Automation",
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
                ("key", models.CharField(max_length=64, unique=True)),
                ("scheduled_task_name", models.CharField(blank=True, max_length=255)),
                ("schedule_human", models.CharField(blank=True, max_length=120)),
                ("script_path", models.TextField(blank=True)),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("active", "稼働中"),
                            ("paused", "停止中"),
                        ],
                        default="active",
                        max_length=16,
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="automations",
                        to="projects.project",
                    ),
                ),
            ],
            options={
                "verbose_name": "自動化",
                "verbose_name_plural": "自動化",
                "ordering": ["project__sort_order", "key"],
            },
        ),
        migrations.CreateModel(
            name="Run",
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
                ("run_key", models.CharField(max_length=128, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("running", "実行中"),
                            ("succeeded", "成功"),
                            ("failed", "失敗"),
                        ],
                        default="running",
                        max_length=16,
                    ),
                ),
                ("trigger", models.CharField(max_length=32)),
                ("started_at", models.DateTimeField()),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("duration_sec", models.PositiveIntegerField(blank=True, null=True)),
                ("exit_code", models.IntegerField(blank=True, null=True)),
                ("log_path", models.TextField(blank=True)),
                ("summary", models.TextField(blank=True)),
                ("metrics", models.JSONField(blank=True, default=dict)),
                (
                    "automation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="runs",
                        to="automations.automation",
                    ),
                ),
            ],
            options={
                "verbose_name": "実行記録",
                "verbose_name_plural": "実行記録",
                "ordering": ["-started_at"],
                "indexes": [
                    models.Index(
                        fields=["status", "-started_at"],
                        name="run_status_started_idx",
                    )
                ],
            },
        ),
    ]
