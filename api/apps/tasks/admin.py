from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError

from apps.services import create_task, update_task
from apps.tasks.models import Task, TaskEvent


class TaskAdminForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        parent = cleaned_data.get("parent")
        project = cleaned_data.get("project")
        if self.instance.pk and not self.instance._state.adding:
            original_project_id = Task.objects.only("project_id").get(pk=self.instance.pk).project_id
            if project and original_project_id != project.pk:
                raise ValidationError("採番済みタスクのプロジェクトは変更できません。")
        if parent and project and parent.project_id != project.pk:
            raise ValidationError("親タスクは同じプロジェクトに属している必要があります。")
        return cleaned_data


class TaskEventInline(admin.TabularInline):
    model = TaskEvent
    extra = 0
    fields = ("event_type", "actor", "body", "session", "occurred_at", "payload")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    form = TaskAdminForm
    list_display = (
        "key",
        "title",
        "project",
        "status",
        "priority",
        "actor_type",
        "created_by",
        "updated_at",
    )
    list_filter = ("status", "priority", "actor_type", "created_by", "project")
    search_fields = ("key", "title", "detail")
    autocomplete_fields = ("project", "parent", "origin_session")
    readonly_fields = ("number", "key", "created_at", "updated_at", "started_at", "completed_at")
    date_hierarchy = "updated_at"
    inlines = (TaskEventInline,)

    def save_model(self, request, obj, form, change):
        if not change:
            due_at = obj.due_at
            tags = obj.tags
            created = create_task(
                project=obj.project,
                title=obj.title,
                detail=obj.detail,
                priority=obj.priority,
                status=obj.status,
                actor_type=obj.actor_type,
                parent=obj.parent,
                created_by=obj.created_by,
                session=obj.origin_session,
            )
            stored = Task.objects.get(pk=created["id"])
            Task.objects.filter(pk=stored.pk).update(due_at=due_at, tags=tags)
            stored.refresh_from_db()
            obj.__dict__.update(stored.__dict__)
            return

        due_at = obj.due_at
        tags = obj.tags
        created_by = obj.created_by
        origin_session_id = obj.origin_session_id
        update_task(
            key=obj.pk,
            status=obj.status,
            title=obj.title,
            detail=obj.detail,
            priority=obj.priority,
            actor_type=obj.actor_type,
            due_at=due_at,
            tags=tags,
            parent=obj.parent,
            actor=Task.Actor.HUMAN,
        )
        Task.objects.filter(pk=obj.pk).update(
            created_by=created_by,
            origin_session_id=origin_session_id,
        )
        obj.refresh_from_db()


@admin.register(TaskEvent)
class TaskEventAdmin(admin.ModelAdmin):
    list_display = ("task", "event_type", "actor", "occurred_at", "session")
    list_filter = ("event_type", "actor")
    search_fields = ("task__key", "task__title", "body")
    autocomplete_fields = ("task", "session")
    date_hierarchy = "occurred_at"
