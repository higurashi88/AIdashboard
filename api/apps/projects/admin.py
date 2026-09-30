from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError

from apps.projects.models import Project, Repository
from apps.services.project_codes import generate_project_code


class ProjectAdminForm(forms.ModelForm):
    code = forms.CharField(
        max_length=12,
        required=False,
        help_text="空欄ならslug/nameから自動生成します。タスク作成後は変更できません。",
    )

    class Meta:
        model = Project
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        code = (cleaned_data.get("code") or "").strip().upper()
        if not code:
            code = generate_project_code(
                name=cleaned_data.get("name") or "",
                slug=cleaned_data.get("slug") or "",
                exclude_project_id=self.instance.pk,
            )
        if self.instance.pk and self.instance.tasks.exists():
            original_code = Project.objects.only("code").get(pk=self.instance.pk).code
            if original_code != code:
                raise ValidationError("タスク作成後はプロジェクトコードを変更できません。")
        cleaned_data["code"] = code
        return cleaned_data


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    form = ProjectAdminForm
    list_display = (
        "name",
        "slug",
        "code",
        "is_active",
        "is_pinned",
        "sort_order",
        "next_task_number",
        "archived_at",
    )
    list_filter = ("is_active", "is_pinned")
    search_fields = ("name", "slug", "code", "root_path")
    ordering = ("sort_order", "name")


@admin.register(Repository)
class RepositoryAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "project",
        "branch",
        "changed_files",
        "ahead",
        "behind",
        "collected_at",
        "is_active",
    )
    list_filter = ("is_active", "project")
    search_fields = ("name", "path")
    readonly_fields = (
        "branch",
        "upstream",
        "ahead",
        "behind",
        "changed_files",
        "untracked_files",
        "last_commit_at",
        "last_commit_sha",
        "last_commit_subject",
        "status_error",
        "collected_at",
    )
