from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard_sessions", "0001_initial"),
        ("tasks", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="session",
            name="tasks",
            field=models.ManyToManyField(
                blank=True,
                related_name="sessions",
                to="tasks.task",
            ),
        ),
    ]
