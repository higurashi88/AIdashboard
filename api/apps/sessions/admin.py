from django.contrib import admin

from apps.sessions.models import Session


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("id", "external_id", "agent", "project", "run", "started_at", "ended_at")
    list_filter = ("agent", "project")
    search_fields = ("external_id", "summary")
    autocomplete_fields = ("project", "run", "tasks")
    date_hierarchy = "started_at"
