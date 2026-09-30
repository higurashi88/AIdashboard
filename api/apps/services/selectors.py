from django.db.models import Count, Max, OuterRef, Q, Subquery

from apps.automations.models import Automation, Run
from apps.projects.models import Project, Repository
from apps.services.domain import (
    ProjectResolutionError,
    RunResolutionError,
    TaskResolutionError,
)
from apps.sessions.models import Session
from apps.tasks.models import Task, TaskEvent


DEFAULT_HIDDEN_STATUSES = (
    Task.Status.DONE,
    Task.Status.CANCELLED,
    Task.Status.BACKLOG,
)


def project_queryset():
    terminal_statuses = [Task.Status.DONE, Task.Status.CANCELLED]
    return Project.objects.annotate(
        open_tasks=Count(
            "tasks",
            filter=~Q(tasks__status__in=terminal_statuses),
            distinct=True,
        ),
        awaiting_user_count=Count(
            "tasks",
            filter=Q(tasks__status=Task.Status.AWAITING_USER),
            distinct=True,
        ),
        in_progress_count=Count(
            "tasks",
            filter=Q(tasks__status=Task.Status.IN_PROGRESS),
            distinct=True,
        ),
    ).order_by("sort_order", "name")


def get_project_by_slug(slug):
    try:
        return project_queryset().get(slug__iexact=str(slug).strip())
    except Project.DoesNotExist as exc:
        raise ProjectResolutionError(f"Project could not be resolved: {slug}") from exc


def task_queryset(project=None, statuses=None, query=None, ordering=None):
    queryset = Task.objects.select_related("project", "parent", "origin_session")
    if project:
        try:
            resolved_project = Project.objects.get(slug__iexact=str(project).strip())
        except Project.DoesNotExist as exc:
            raise ProjectResolutionError(
                f"Project could not be resolved: {project}"
            ) from exc
        queryset = queryset.filter(project=resolved_project)
    if statuses:
        queryset = queryset.filter(status__in=statuses)
    else:
        queryset = queryset.exclude(status__in=DEFAULT_HIDDEN_STATUSES)
    if query:
        queryset = queryset.filter(title__icontains=str(query).strip())
    return queryset.order_by(*(ordering or ["-priority", "-updated_at"]))


def get_task_by_key(key):
    try:
        return Task.objects.select_related("project", "parent", "origin_session").get(
            key__iexact=str(key).strip()
        )
    except Task.DoesNotExist as exc:
        raise TaskResolutionError(f"Task could not be resolved: {key}") from exc


def task_event_queryset(key):
    task = get_task_by_key(key)
    return task.events.select_related("task", "session").order_by("-occurred_at", "-id")


def task_event_feed(after=None, limit=100):
    """PJ横断のタスクイベントを ID 昇順で返す（通知用のカーソル読み出し）。

    after を省略すると結果は返さず、現在の最新 ID だけを返す。初めて購読する
    クライアントが過去の履歴をまとめて流さず「今から」購読を始めるためのもの。
    """
    if after is None:
        latest = TaskEvent.objects.aggregate(latest=Max("id"))["latest"] or 0
        return [], latest
    events = list(
        TaskEvent.objects.filter(id__gt=after)
        .select_related("task", "task__project")
        .order_by("id")[:limit]
    )
    next_after = events[-1].id if events else after
    return events, next_after


def repository_queryset(include_inactive=False):
    queryset = Repository.objects.select_related("project")
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    return queryset.order_by("sort_order", "name")


def session_queryset():
    return (
        Session.objects.select_related("project", "run")
        .prefetch_related("tasks")
        .order_by("-started_at")
    )


def automation_queryset():
    latest_run = Run.objects.filter(automation_id=OuterRef("pk")).order_by("-started_at")
    return (
        Automation.objects.select_related("project")
        .annotate(
            last_run_key=Subquery(latest_run.values("run_key")[:1]),
            last_run_status=Subquery(latest_run.values("status")[:1]),
            last_run_started_at=Subquery(latest_run.values("started_at")[:1]),
            last_run_ended_at=Subquery(latest_run.values("ended_at")[:1]),
            last_run_duration_sec=Subquery(latest_run.values("duration_sec")[:1]),
        )
        .order_by("project__sort_order", "key")
    )


def run_queryset(status=None, ended_after=None):
    queryset = Run.objects.select_related("automation", "automation__project")
    if status:
        queryset = queryset.filter(status=status)
    if ended_after is not None:
        queryset = queryset.filter(ended_at__gt=ended_after)
    return queryset.order_by("-started_at")


def get_run_by_key(run_key):
    try:
        return run_queryset().get(run_key=str(run_key).strip())
    except Run.DoesNotExist as exc:
        raise RunResolutionError(f"Run could not be resolved: {run_key}") from exc
