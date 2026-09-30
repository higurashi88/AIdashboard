import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ApiKey",
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
                ("name", models.CharField(max_length=120)),
                ("key_hash", models.CharField(editable=False, max_length=64, unique=True)),
                ("prefix", models.CharField(db_index=True, editable=False, max_length=8)),
                (
                    "scope",
                    models.CharField(
                        choices=[("mcp", "MCP"), ("pipeline", "Pipeline"), ("web", "Web")],
                        max_length=16,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "APIキー",
                "verbose_name_plural": "APIキー",
                "ordering": ["name", "created_at"],
            },
        ),
    ]
