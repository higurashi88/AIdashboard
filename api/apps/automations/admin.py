from django.contrib import admin

from apps.automations.models import Automation, Run


@admin.register(Automation)
class AutomationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "key",
        "project",
        "schedule_human",
        "state",
        "scheduled_task_name",
    )
    list_filter = ("state", "project")
    search_fields = ("name", "key", "scheduled_task_name", "script_path")
    autocomplete_fields = ("project",)


@admin.register(Run)
class RunAdmin(admin.ModelAdmin):
    list_display = (
        "run_key",
        "automation",
        "status",
        "trigger",
        "started_at",
        "duration_sec",
        "exit_code",
    )
    list_filter = ("status", "trigger", "automation")
    search_fields = ("run_key", "summary", "log_path")
    autocomplete_fields = ("automation",)
    date_hierarchy = "started_at"
