import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("automations", "0001_initial"),
        ("projects", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Session",
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
                ("external_id", models.CharField(blank=True, max_length=128, null=True, unique=True)),
                (
                    "agent",
                    models.CharField(
                        choices=[
                            ("claude_code", "Claude Code"),
                            ("codex", "Codex"),
                            ("human", "Human"),
                        ],
                        default="claude_code",
                        max_length=16,
                    ),
                ),
                ("started_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("summary", models.TextField(blank=True)),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sessions",
                        to="projects.project",
                    ),
                ),
                (
                    "run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sessions",
                        to="automations.run",
                    ),
                ),
            ],
            options={
                "verbose_name": "セッション",
                "verbose_name_plural": "セッション",
                "ordering": ["-started_at"],
                "indexes": [
                    models.Index(
                        fields=["project", "-started_at"],
                        name="session_project_started_idx",
                    )
                ],
            },
        ),
    ]
