from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "共通"

    def ready(self):
        from apps.core import schema  # noqa: F401
