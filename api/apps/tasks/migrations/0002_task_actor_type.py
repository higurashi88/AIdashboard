from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tasks", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="actor_type",
            field=models.CharField(
                choices=[("agent", "AI"), ("human", "人間")],
                default="agent",
                max_length=16,
            ),
        ),
    ]
