from django.contrib import admin

from apps.core.models import ApiKey


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ("name", "prefix", "scope", "is_active", "created_at", "last_used_at")
    list_filter = ("scope", "is_active")
    search_fields = ("name", "prefix")
    readonly_fields = ("key_hash", "prefix", "created_at", "last_used_at")

    def has_add_permission(self, request):
        return False
