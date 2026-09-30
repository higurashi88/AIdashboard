import uuid

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Project",
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
                ("slug", models.SlugField(max_length=64, unique=True)),
                (
                    "code",
                    models.CharField(
                        max_length=12,
                        unique=True,
                        validators=[
                            django.core.validators.RegexValidator(
                                "^[A-Z0-9]+$",
                                "半角英大文字と数字で入力してください",
                            )
                        ],
                    ),
                ),
                ("name", models.CharField(max_length=120)),
                ("root_path", models.TextField()),
                ("summary", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("archived_at", models.DateTimeField(blank=True, null=True)),
                ("sort_order", models.SmallIntegerField(default=0)),
                ("is_pinned", models.BooleanField(default=False)),
                (
                    "color",
                    models.CharField(
                        default="#64748B",
                        max_length=7,
                        validators=[
                            django.core.validators.RegexValidator(
                                "^#[0-9A-Fa-f]{6}$",
                                "#RRGGBB形式で入力してください",
                            )
                        ],
                    ),
                ),
                ("extra", models.JSONField(blank=True, default=dict)),
                ("next_task_number", models.PositiveIntegerField(default=1)),
            ],
            options={
                "verbose_name": "プロジェクト",
                "verbose_name_plural": "プロジェクト",
                "ordering": ["sort_order", "name"],
            },
        ),
        migrations.AddConstraint(
            model_name="project",
            constraint=models.CheckConstraint(
                condition=models.Q(("next_task_number__gte", 1)),
                name="project_next_task_number_gte_1",
            ),
        ),
    ]
