from datetime import datetime, timedelta
from pathlib import PureWindowsPath
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.automations.models import Automation, Run
from apps.projects.models import Project, Repository
from apps.sessions.models import Session
from apps.services.project_codes import generate_project_code, generate_project_slug
from apps.tasks.models import Task, TaskEvent


class DomainServiceError(Exception):
    pass


class ProjectResolutionError(DomainServiceError):
    def __init__(self, message, candidates=None):
        super().__init__(message)
        self.candidates = candidates or []


class TaskResolutionError(DomainServiceError):
    pass


class RunResolutionError(DomainServiceError):
    pass


def _iso(value):
    if not value:
        return None
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.isoformat()


def _active_project_candidates():
    return list(
        Project.objects.filter(is_active=True, archived_at__isnull=True)
        .order_by("sort_order", "name")
        .values_list("slug", flat=True)
    )


def _resolve_project(reference):
    if isinstance(reference, Project):
        return reference
    if reference is None or str(reference).strip() == "":
        raise ProjectResolutionError(
            "A project slug, code, or UUID is required",
            _active_project_candidates(),
        )

    text = str(reference).strip()
    query = Q(slug=text) | Q(code__iexact=text)
    try:
        query |= Q(pk=UUID(text))
    except (ValueError, TypeError, AttributeError):
        pass
    try:
        return Project.objects.get(query)
    except Project.DoesNotExist as exc:
        raise ProjectResolutionError(
            f"Project could not be resolved: {text}",
            _active_project_candidates(),
        ) from exc
    except Project.MultipleObjectsReturned as exc:
        raise ProjectResolutionError(f"Project reference is ambiguous: {text}") from exc


def _normalize_windows_path(path):
    text = str(PureWindowsPath(str(path).strip())).replace("/", "\\")
    return text.rstrip("\\").casefold()


def _resolve_project_from_cwd(cwd):
    if cwd is None or str(cwd).strip() == "":
        raise ProjectResolutionError(
            "cwd must not be empty",
            _active_project_candidates(),
        )
    normalized_cwd = _normalize_windows_path(cwd)
    matches = []
    projects = Project.objects.filter(is_active=True, archived_at__isnull=True).exclude(root_path="")
    for project in projects:
        normalized_root = _normalize_windows_path(project.root_path)
        if normalized_cwd == normalized_root or normalized_cwd.startswith(normalized_root + "\\"):
            matches.append((len(normalized_root), project))
    if not matches:
        raise ProjectResolutionError(
            f"No registered project contains cwd: {cwd}",
            _active_project_candidates(),
        )
    matches.sort(key=lambda item: item[0], reverse=True)
    return matches[0][1]


def _resolve_task(reference, queryset=None):
    if isinstance(reference, Task):
        return reference
    if reference is None or str(reference).strip() == "":
        raise TaskResolutionError("A task key or UUID is required")
    queryset = queryset if queryset is not None else Task.objects.all()
    text = str(reference).strip()
    query = Q(key__iexact=text)
    try:
        query |= Q(pk=UUID(text))
    except (ValueError, TypeError, AttributeError):
        pass
    try:
        return queryset.get(query)
    except Task.DoesNotExist as exc:
        raise TaskResolutionError(f"Task could not be resolved: {text}") from exc
    except Task.MultipleObjectsReturned as exc:
        raise TaskResolutionError(f"Task reference is ambiguous: {text}") from exc


def _resolve_session(reference):
    if reference is None or reference == "":
        return None
    if isinstance(reference, Session):
        return reference
    text = str(reference).strip()
    query = Q(external_id=text)
    try:
        query |= Q(pk=UUID(text))
    except (ValueError, TypeError, AttributeError):
        pass
    try:
        return Session.objects.get(query)
    except Session.DoesNotExist as exc:
        raise DomainServiceError(f"Session could not be resolved: {text}") from exc


def _coerce_datetime(value, field_name):
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        result = parse_datetime(value)
        if result is None:
            raise ValidationError({field_name: "Use an ISO 8601 datetime"})
    else:
        raise ValidationError({field_name: "A datetime or ISO 8601 string is required"})
    if timezone.is_naive(result):
        result = timezone.make_aware(result, timezone.get_current_timezone())
    return result


def _validate_choice(value, choices, field_name):
    if value not in choices:
        raise ValidationError({field_name: f"Unsupported value: {value}"})


def _with_last_human_note(queryset):
    latest_human_note = TaskEvent.objects.filter(
        task_id=OuterRef("pk"),
        actor=Task.Actor.HUMAN,
        event_type=TaskEvent.EventType.NOTE,
    ).order_by("-occurred_at", "-id")
    return queryset.annotate(
        last_human_note_body=Subquery(latest_human_note.values("body")[:1]),
        last_human_note_at=Subquery(latest_human_note.values("occurred_at")[:1]),
    )


def _task_dict(task, *, last_human_note=False):
    result = {
        "id": str(task.pk),
        "project": task.project.slug,
        "number": task.number,
        "key": task.key,
        "title": task.title,
        "detail": task.detail,
        "status": task.status,
        "priority": task.priority,
        "actor_type": task.actor_type,
        "parent": task.parent.key if task.parent_id else None,
        "created_by": task.created_by,
        "origin_session": str(task.origin_session_id) if task.origin_session_id else None,
        "due_at": _iso(task.due_at),
        "started_at": _iso(task.started_at),
        "completed_at": _iso(task.completed_at),
        "tags": list(task.tags),
        "created_at": _iso(task.created_at),
        "updated_at": _iso(task.updated_at),
    }
    if last_human_note:
        result["last_human_note"] = (
            {
                "body": task.last_human_note_body,
                "at": _iso(task.last_human_note_at),
            }
            if task.last_human_note_at is not None
            else None
        )
    return result


def _run_dict(run):
    return {
        "id": str(run.pk),
        "automation_key": run.automation.key,
        "run_key": run.run_key,
        "status": run.status,
        "trigger": run.trigger,
        "started_at": _iso(run.started_at),
        "ended_at": _iso(run.ended_at),
        "duration_sec": run.duration_sec,
        "exit_code": run.exit_code,
        "log_path": run.log_path,
        "summary": run.summary,
        "metrics": run.metrics,
    }


def _repository_dict(repository):
    return {
        "name": repository.name,
        "path": repository.path,
        "project": repository.project.slug if repository.project_id else None,
        "branch": repository.branch,
        "upstream": repository.upstream,
        "ahead": repository.ahead,
        "behind": repository.behind,
        "changed_files": repository.changed_files,
        "untracked_files": repository.untracked_files,
        "last_commit_at": _iso(repository.last_commit_at),
        "last_commit_subject": repository.last_commit_subject,
        "status_error": repository.status_error,
        "collected_at": _iso(repository.collected_at),
    }


def _active_repositories():
    return Repository.objects.filter(is_active=True).select_related("project").order_by(
        "sort_order", "name"
    )


REPOSITORY_STATUS_FIELDS = (
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
)


@transaction.atomic
def record_repository_statuses(items, collected_at=None):
    """ホストの収集スクリプトから届いた状態を、path が一致するリポジトリへ保存する。"""
    collected_at = collected_at or timezone.now()
    repositories = {
        repository.path: repository
        for repository in Repository.objects.select_for_update().filter(
            path__in=[item["path"] for item in items]
        )
    }
    updated = []
    unknown = []
    for item in items:
        repository = repositories.get(item["path"])
        if repository is None:
            unknown.append(item["path"])
            continue
        for field in REPOSITORY_STATUS_FIELDS:
            value = item.get(field)
            if value is None and field not in {"ahead", "behind", "changed_files", "untracked_files", "last_commit_at"}:
                value = ""
            setattr(repository, field, value)
        repository.collected_at = collected_at
        repository.save(update_fields=[*REPOSITORY_STATUS_FIELDS, "collected_at", "updated_at"])
        updated.append(repository.path)
    return {"updated": len(updated), "unknown": unknown}


def list_projects():
    terminal_statuses = [Task.Status.DONE, Task.Status.CANCELLED]
    projects = (
        Project.objects.filter(is_active=True, archived_at__isnull=True)
        .annotate(
            open_tasks=Count("tasks", filter=~Q(tasks__status__in=terminal_statuses)),
            awaiting_user=Count("tasks", filter=Q(tasks__status=Task.Status.AWAITING_USER)),
        )
        .order_by("sort_order", "name")
    )
    return [
        {
            "slug": project.slug,
            "code": project.code,
            "name": project.name,
            "summary": project.summary,
            "open_tasks": project.open_tasks,
            "awaiting_user": project.awaiting_user,
        }
        for project in projects
    ]


@transaction.atomic
def create_project(
    name,
    root_path,
    slug=None,
    code=None,
    summary="",
    is_active=True,
    archived_at=None,
    sort_order=0,
    is_pinned=False,
    color="#64748B",
    extra=None,
):
    if not name or not str(name).strip():
        raise ValidationError({"name": "name must not be empty"})
    if not root_path or not str(root_path).strip():
        raise ValidationError({"root_path": "root_path must not be empty"})

    resolved_slug = str(slug).strip().lower() if slug else generate_project_slug(name)
    resolved_code = (
        str(code).strip().upper()
        if code
        else generate_project_code(name=name, slug=resolved_slug)
    )
    project = Project(
        slug=resolved_slug,
        code=resolved_code,
        name=str(name).strip(),
        root_path=str(root_path).strip(),
        summary=summary or "",
        is_active=is_active,
        archived_at=archived_at,
        sort_order=sort_order,
        is_pinned=is_pinned,
        color=color,
        extra={} if extra is None else extra,
    )
    project.full_clean()
    project.save(force_insert=True)
    return project


@transaction.atomic
def update_project(slug, **changes):
    try:
        project = Project.objects.select_for_update().get(slug__iexact=str(slug).strip())
    except Project.DoesNotExist as exc:
        raise ProjectResolutionError(f"Project could not be resolved: {slug}") from exc

    mutable_fields = {
        "name",
        "root_path",
        "summary",
        "is_active",
        "archived_at",
        "sort_order",
        "is_pinned",
        "color",
        "extra",
    }
    unknown = set(changes) - mutable_fields
    if unknown:
        raise ValidationError(
            {field: "This field cannot be updated" for field in sorted(unknown)}
        )
    for field, value in changes.items():
        if field in {"name", "root_path"} and not str(value or "").strip():
            raise ValidationError({field: f"{field} must not be empty"})
        setattr(project, field, value)
    project.full_clean()
    project.save(update_fields=sorted(changes) if changes else None)
    return project


def get_project(slug=None, cwd=None):
    if slug is not None and str(slug).strip() != "":
        project = _resolve_project(slug)
    elif cwd is not None and str(cwd).strip() != "":
        project = _resolve_project_from_cwd(cwd)
    else:
        raise ProjectResolutionError(
            "Specify either slug or cwd",
            _active_project_candidates(),
        )

    task_queryset = _with_last_human_note(
        Task.objects.select_related("project", "parent", "origin_session")
    )
    tasks = list(
        task_queryset.filter(
            project=project,
            status__in=[Task.Status.TODO, Task.Status.IN_PROGRESS, Task.Status.BLOCKED],
            actor_type=Task.ActorType.AGENT,
        )
        .order_by("-priority", "updated_at")
    )
    human_tasks = list(
        task_queryset.filter(
            project=project,
            status__in=[Task.Status.TODO, Task.Status.IN_PROGRESS, Task.Status.BLOCKED],
            actor_type=Task.ActorType.HUMAN,
        )
        .order_by("-priority", "updated_at")
    )
    awaiting = list(
        task_queryset.filter(project=project, status=Task.Status.AWAITING_USER)
        .order_by("-priority", "updated_at")
    )

    activity = []
    events = TaskEvent.objects.filter(task__project=project).select_related("task").order_by("-occurred_at")[:10]
    for event in events:
        activity.append(
            {
                "at": _iso(event.occurred_at),
                "actor": event.actor,
                "body": event.body,
                "task_key": event.task.key,
            }
        )
    sessions = Session.objects.filter(project=project).exclude(summary="").order_by("-ended_at", "-started_at")[:10]
    for session in sessions:
        activity.append(
            {
                "at": _iso(session.ended_at or session.started_at),
                "actor": session.agent,
                "body": session.summary,
                "session_id": str(session.pk),
            }
        )
    activity.sort(key=lambda item: item["at"] or "", reverse=True)

    automations = []
    for automation in project.automations.all().order_by("key"):
        last_run = automation.runs.order_by("-started_at").first()
        automations.append(
            {
                "key": automation.key,
                "name": automation.name or automation.scheduled_task_name or automation.key,
                "schedule": automation.schedule_human,
                "state": automation.state,
                "last_run": _run_dict(last_run) if last_run else None,
            }
        )

    return {
        "id": str(project.pk),
        "slug": project.slug,
        "code": project.code,
        "name": project.name,
        "root_path": project.root_path,
        "summary": project.summary,
        "tasks": [_task_dict(task, last_human_note=True) for task in tasks],
        "awaiting_user": [_task_dict(task, last_human_note=True) for task in awaiting],
        "human_tasks": [
            _task_dict(task, last_human_note=True) for task in human_tasks
        ],
        "recent_activity": activity[:10],
        "automations": automations,
        "repositories": [
            _repository_dict(repository)
            for repository in _active_repositories().filter(project=project)
        ],
    }


def get_dashboard_summary():
    task_queryset = Task.objects.select_related("project", "parent", "origin_session")
    awaiting_user = list(
        task_queryset.filter(
            status=Task.Status.AWAITING_USER,
            project__archived_at__isnull=True,
        ).order_by("-priority", "-updated_at")
    )
    in_progress = list(
        task_queryset.filter(
            status=Task.Status.IN_PROGRESS,
            actor_type=Task.ActorType.AGENT,
            project__archived_at__isnull=True,
        ).order_by("-priority", "-updated_at")[:10]
    )
    human_tasks = list(
        task_queryset.filter(
            actor_type=Task.ActorType.HUMAN,
            status__in=[Task.Status.TODO, Task.Status.IN_PROGRESS, Task.Status.BLOCKED],
            project__archived_at__isnull=True,
        ).order_by("-priority", "-updated_at")
    )

    latest_run = Run.objects.filter(automation_id=OuterRef("pk")).order_by("-started_at")
    automations = (
        Automation.objects.filter(project__archived_at__isnull=True)
        .select_related("project")
        .annotate(
            last_run_status=Subquery(latest_run.values("status")[:1]),
            last_run_started_at=Subquery(latest_run.values("started_at")[:1]),
            last_run_duration_sec=Subquery(latest_run.values("duration_sec")[:1]),
        )
    )
    automation_items = [
        {
            "key": automation.key,
            "name": automation.name or automation.scheduled_task_name or automation.key,
            "schedule": automation.schedule_human,
            "state": automation.state,
            "last_run": (
                {
                    "status": automation.last_run_status,
                    "started_at": _iso(automation.last_run_started_at),
                    "duration_sec": automation.last_run_duration_sec,
                }
                if automation.last_run_started_at is not None
                else None
            ),
        }
        for automation in automations.order_by("project__sort_order", "key")
    ]

    latest_task = Task.objects.filter(project_id=OuterRef("pk")).order_by("-updated_at")
    latest_event = TaskEvent.objects.filter(task__project_id=OuterRef("pk")).order_by(
        "-occurred_at"
    )
    latest_session = (
        Session.objects.filter(project_id=OuterRef("pk"))
        .annotate(activity_at=Coalesce("ended_at", "started_at"))
        .order_by("-activity_at")
    )
    latest_project_run = (
        Run.objects.filter(automation__project_id=OuterRef("pk"))
        .annotate(activity_at=Coalesce("ended_at", "started_at"))
        .order_by("-activity_at")
    )
    terminal_statuses = [Task.Status.DONE, Task.Status.CANCELLED]
    projects = Project.objects.filter(archived_at__isnull=True).annotate(
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
        last_task_at=Subquery(latest_task.values("updated_at")[:1]),
        last_event_at=Subquery(latest_event.values("occurred_at")[:1]),
        last_session_at=Subquery(latest_session.values("activity_at")[:1]),
        last_run_at=Subquery(latest_project_run.values("activity_at")[:1]),
    )
    stale_cutoff = timezone.now() - timedelta(days=7)
    project_items = []
    for project in projects:
        activity_values = [
            project.last_task_at,
            project.last_event_at,
            project.last_session_at,
            project.last_run_at,
        ]
        last_activity_at = max((value for value in activity_values if value), default=None)
        project_items.append(
            {
                "slug": project.slug,
                "code": project.code,
                "name": project.name,
                "color": project.color,
                "is_active": project.is_active,
                "is_pinned": project.is_pinned,
                "open_tasks": project.open_tasks,
                "awaiting_user": project.awaiting_user_count,
                "in_progress": project.in_progress_count,
                "last_activity_at": _iso(last_activity_at),
                "is_stale": last_activity_at is None or last_activity_at <= stale_cutoff,
                "_sort_order": project.sort_order,
            }
        )
    project_items.sort(
        key=lambda item: (
            not item["is_pinned"],
            not bool(item["open_tasks"]),
            item["_sort_order"],
            item["name"].casefold(),
        )
    )
    for item in project_items:
        item.pop("_sort_order")

    recent_activity = []
    events = (
        TaskEvent.objects.filter(task__project__archived_at__isnull=True)
        .select_related("task", "task__project")
        .order_by("-occurred_at", "-id")[:10]
    )
    for event in events:
        recent_activity.append(
            {
                "at": _iso(event.occurred_at),
                "actor": event.actor,
                "body": event.body,
                "task_key": event.task.key,
                "project": event.task.project.slug,
            }
        )
    sessions = (
        Session.objects.filter(project__isnull=False, project__archived_at__isnull=True)
        .exclude(summary="")
        .select_related("project")
        .annotate(activity_at=Coalesce("ended_at", "started_at"))
        .order_by("-activity_at")[:10]
    )
    for session in sessions:
        recent_activity.append(
            {
                "at": _iso(session.activity_at),
                "actor": session.agent,
                "body": session.summary,
                "project": session.project.slug,
            }
        )
    recent_activity.sort(key=lambda item: item["at"] or "", reverse=True)

    return {
        "awaiting_user": [_task_dict(task) for task in awaiting_user],
        "human_tasks": [_task_dict(task) for task in human_tasks],
        "in_progress": [_task_dict(task) for task in in_progress],
        "automations": automation_items,
        "projects": project_items,
        "recent_activity": recent_activity[:10],
        "repositories": [
            _repository_dict(repository) for repository in _active_repositories()
        ],
    }


def list_tasks(project=None, status=None, query=None, limit=50):
    try:
        limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"limit": "limit must be an integer"}) from exc
    if limit < 1 or limit > 200:
        raise ValidationError({"limit": "limit must be between 1 and 200"})

    tasks = _with_last_human_note(
        Task.objects.select_related("project", "parent", "origin_session")
    )
    if project is not None and str(project).strip() != "":
        tasks = tasks.filter(project=_resolve_project(project))
    if status is not None and str(status).strip() != "":
        statuses = [value.strip() for value in str(status).split(",") if value.strip()]
        invalid = sorted(set(statuses) - set(Task.Status.values))
        if invalid:
            raise ValidationError({"status": f"Unsupported status: {', '.join(invalid)}"})
        tasks = tasks.filter(status__in=statuses)
    else:
        stale_done_cutoff = timezone.now() - timedelta(days=90)
        tasks = tasks.exclude(status__in=[Task.Status.BACKLOG, Task.Status.CANCELLED]).exclude(
            status=Task.Status.DONE,
            updated_at__lt=stale_done_cutoff,
        )
    if query is not None and str(query).strip() != "":
        tasks = tasks.filter(title__icontains=str(query).strip())
    tasks = tasks.order_by("-priority", "-updated_at")[:limit]
    return [_task_dict(task, last_human_note=True) for task in tasks]


@transaction.atomic
def create_task(
    project,
    title,
    detail=None,
    priority=0,
    status="todo",
    actor_type="agent",
    parent=None,
    created_by="human",
    session=None,
):
    resolved_project = _resolve_project(project)
    resolved_session = _resolve_session(session)
    _validate_choice(status, Task.Status.values, "status")
    _validate_choice(actor_type, Task.ActorType.values, "actor_type")
    _validate_choice(created_by, Task.Actor.values, "created_by")
    try:
        priority = int(priority)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"priority": "priority must be an integer"}) from exc
    _validate_choice(priority, Task.Priority.values, "priority")
    if not title or not str(title).strip():
        raise ValidationError({"title": "title must not be empty"})

    locked_project = Project.objects.select_for_update().get(pk=resolved_project.pk)
    resolved_parent = _resolve_task(parent) if parent else None
    if resolved_parent and resolved_parent.project_id != locked_project.pk:
        raise ValidationError({"parent": "parent must belong to the same project"})
    if resolved_session and resolved_session.project_id not in {None, locked_project.pk}:
        raise ValidationError({"session": "session belongs to a different project"})

    number = locked_project.next_task_number
    locked_project.next_task_number = number + 1
    locked_project.save(update_fields=["next_task_number"])
    now = timezone.now()
    task = Task(
        project=locked_project,
        number=number,
        key=f"{locked_project.code}-{number}",
        title=str(title).strip(),
        detail=detail or "",
        priority=priority,
        status=status,
        actor_type=actor_type,
        parent=resolved_parent,
        created_by=created_by,
        origin_session=resolved_session,
        started_at=now if status == Task.Status.IN_PROGRESS else None,
        completed_at=now if status == Task.Status.DONE else None,
    )
    task.full_clean()
    task.save(force_insert=True)
    TaskEvent.objects.create(
        task=task,
        session=resolved_session,
        event_type=TaskEvent.EventType.CREATED,
        actor=created_by,
        body=task.title,
        payload={"status": task.status, "priority": task.priority},
    )
    return _task_dict(task)


@transaction.atomic
def update_task(
    key,
    status=None,
    title=None,
    detail=None,
    priority=None,
    actor_type=None,
    note=None,
    actor="human",
    session=None,
    due_at=...,
    tags=...,
    parent=...,
):
    task = _resolve_task(key, Task.objects.select_for_update())
    resolved_session = _resolve_session(session)
    _validate_choice(actor, Task.Actor.values, "actor")
    if resolved_session and resolved_session.project_id not in {None, task.project_id}:
        raise ValidationError({"session": "session belongs to a different project"})

    old_status = task.status
    edited = {}
    if status is not None:
        _validate_choice(status, Task.Status.values, "status")
        if status != task.status:
            task.status = status
            if status == Task.Status.IN_PROGRESS and task.started_at is None:
                task.started_at = timezone.now()
            if status == Task.Status.DONE:
                task.completed_at = timezone.now()
    if title is not None:
        if not str(title).strip():
            raise ValidationError({"title": "title must not be empty"})
        if str(title).strip() != task.title:
            edited["title"] = {"from": task.title, "to": str(title).strip()}
            task.title = str(title).strip()
    if detail is not None and detail != task.detail:
        edited["detail"] = {"changed": True}
        task.detail = detail
    if priority is not None:
        try:
            priority = int(priority)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"priority": "priority must be an integer"}) from exc
        _validate_choice(priority, Task.Priority.values, "priority")
        if priority != task.priority:
            edited["priority"] = {"from": task.priority, "to": priority}
            task.priority = priority
    if actor_type is not None:
        _validate_choice(actor_type, Task.ActorType.values, "actor_type")
        if actor_type != task.actor_type:
            edited["actor_type"] = {"from": task.actor_type, "to": actor_type}
            task.actor_type = actor_type
    if due_at is not ...:
        resolved_due_at = (
            None if due_at is None else _coerce_datetime(due_at, "due_at")
        )
        if resolved_due_at != task.due_at:
            edited["due_at"] = {
                "from": _iso(task.due_at),
                "to": _iso(resolved_due_at),
            }
            task.due_at = resolved_due_at
    if tags is not ...:
        if tags is None or isinstance(tags, (str, bytes)):
            raise ValidationError({"tags": "tags must be a list of strings"})
        try:
            resolved_tags = list(tags)
        except TypeError as exc:
            raise ValidationError({"tags": "tags must be a list of strings"}) from exc
        if any(not isinstance(tag, str) for tag in resolved_tags):
            raise ValidationError({"tags": "tags must be a list of strings"})
        if resolved_tags != task.tags:
            edited["tags"] = {"from": list(task.tags), "to": resolved_tags}
            task.tags = resolved_tags
    if parent is not ...:
        resolved_parent = (
            None
            if parent is None or str(parent).strip() == ""
            else _resolve_task(parent, Task.objects.select_for_update())
        )
        if resolved_parent and resolved_parent.project_id != task.project_id:
            raise ValidationError({"parent": "parent must belong to the same project"})
        current = resolved_parent
        visited = set()
        while current is not None:
            if current.pk in visited:
                raise ValidationError({"parent": "parent hierarchy contains a cycle"})
            visited.add(current.pk)
            if current.pk == task.pk:
                raise ValidationError(
                    {"parent": "parent cannot be the task itself or its descendant"}
                )
            if current.parent_id is None:
                break
            current = Task.objects.select_for_update().get(pk=current.parent_id)
        if (resolved_parent.pk if resolved_parent else None) != task.parent_id:
            edited["parent"] = {
                "from": task.parent.key if task.parent_id else None,
                "to": resolved_parent.key if resolved_parent else None,
            }
            task.parent = resolved_parent

    task.full_clean()
    task.save()
    if task.status != old_status:
        TaskEvent.objects.create(
            task=task,
            session=resolved_session,
            event_type=TaskEvent.EventType.STATUS_CHANGED,
            actor=actor,
            body=f"{old_status} → {task.status}",
            payload={"from": old_status, "to": task.status},
        )
    if edited:
        TaskEvent.objects.create(
            task=task,
            session=resolved_session,
            event_type=TaskEvent.EventType.EDITED,
            actor=actor,
            body="タスク内容を更新",
            payload=edited,
        )
    if note is not None:
        TaskEvent.objects.create(
            task=task,
            session=resolved_session,
            event_type=TaskEvent.EventType.NOTE,
            actor=actor,
            body=str(note),
            payload={},
        )
    return _task_dict(task)


@transaction.atomic
def delete_task(key):
    task = _resolve_task(key, Task.objects.select_for_update())
    result = {"key": task.key, "project": task.project.slug}
    task.delete()
    return result


@transaction.atomic
def report_session(
    project,
    summary,
    task_keys=None,
    agent="claude_code",
    external_id=None,
):
    resolved_project = _resolve_project(project)
    _validate_choice(agent, Session.Agent.values, "agent")
    if not summary or not str(summary).strip():
        raise ValidationError({"summary": "summary must not be empty"})

    if task_keys is None:
        keys = []
    elif isinstance(task_keys, str):
        keys = [task_keys]
    else:
        keys = list(task_keys)
    resolved_tasks = []
    for key in keys:
        task = _resolve_task(key)
        if task.project_id != resolved_project.pk:
            raise ValidationError({"task_keys": f"{task.key} belongs to a different project"})
        resolved_tasks.append(task)

    now = timezone.now()
    if external_id:
        session, created = Session.objects.select_for_update().get_or_create(
            external_id=external_id,
            defaults={
                "project": resolved_project,
                "agent": agent,
                "started_at": now,
                "ended_at": now,
                "summary": str(summary).strip(),
            },
        )
        if not created:
            session.project = resolved_project
            session.agent = agent
            session.ended_at = session.ended_at or now
            session.summary = str(summary).strip()
            session.full_clean()
            session.save(update_fields=["project", "agent", "ended_at", "summary"])
    else:
        session = Session(
            project=resolved_project,
            agent=agent,
            started_at=now,
            ended_at=now,
            summary=str(summary).strip(),
        )
        session.full_clean()
        session.save(force_insert=True)
    session.tasks.set(resolved_tasks)

    return {
        "id": str(session.pk),
        "external_id": session.external_id,
        "agent": session.agent,
        "project": resolved_project.slug,
        "started_at": _iso(session.started_at),
        "ended_at": _iso(session.ended_at),
        "summary": session.summary,
        "task_keys": [task.key for task in resolved_tasks],
    }


@transaction.atomic
def start_run(automation_key, run_key, trigger, started_at, log_path=None):
    try:
        automation = Automation.objects.get(key=automation_key)
    except Automation.DoesNotExist as exc:
        raise RunResolutionError(f"Automation could not be resolved: {automation_key}") from exc
    if not run_key or not str(run_key).strip():
        raise ValidationError({"run_key": "run_key must not be empty"})
    if not trigger or not str(trigger).strip():
        raise ValidationError({"trigger": "trigger must not be empty"})

    candidate = Run(
        automation=automation,
        run_key=str(run_key).strip(),
        status=Run.Status.RUNNING,
        trigger=str(trigger).strip(),
        started_at=_coerce_datetime(started_at, "started_at"),
        log_path=log_path or "",
    )
    # Validate all input fields before INSERT while allowing run_key retries.
    candidate.full_clean(validate_unique=False)
    run, created = Run.objects.get_or_create(
        run_key=candidate.run_key,
        defaults={
            "automation": candidate.automation,
            "status": candidate.status,
            "trigger": candidate.trigger,
            "started_at": candidate.started_at,
            "log_path": candidate.log_path,
        },
    )
    if not created and run.automation_id != automation.pk:
        raise ValidationError({"run_key": "run_key already belongs to another automation"})
    return _run_dict(run)


@transaction.atomic
def finish_run(run_key, status, exit_code=None, ended_at=None, summary=None):
    if status not in {Run.Status.SUCCEEDED, Run.Status.FAILED}:
        raise ValidationError({"status": "finish status must be succeeded or failed"})
    try:
        run = Run.objects.select_for_update().select_related("automation").get(run_key=run_key)
    except Run.DoesNotExist as exc:
        raise RunResolutionError(f"Run could not be resolved: {run_key}") from exc

    if ended_at is None and run.status in {Run.Status.SUCCEEDED, Run.Status.FAILED}:
        finish_time = run.ended_at or timezone.now()
    else:
        finish_time = timezone.now() if ended_at is None else _coerce_datetime(ended_at, "ended_at")
    if finish_time < run.started_at:
        raise ValidationError({"ended_at": "ended_at must not be before started_at"})
    run.status = status
    run.ended_at = finish_time
    run.duration_sec = max(0, int((finish_time - run.started_at).total_seconds()))
    if exit_code is not None:
        try:
            run.exit_code = int(exit_code)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"exit_code": "exit_code must be an integer"}) from exc
    if summary is not None:
        run.summary = str(summary)
    run.full_clean()
    run.save(
        update_fields=["status", "ended_at", "duration_sec", "exit_code", "summary"]
    )
    return _run_dict(run)
