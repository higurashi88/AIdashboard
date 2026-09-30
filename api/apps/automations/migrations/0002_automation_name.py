from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("automations", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="automation",
            name="name",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
    ]
