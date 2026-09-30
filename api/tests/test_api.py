from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.automations.models import Automation, Run
from apps.projects.models import Project
from apps.services import domain
from apps.services import create_task, report_session, start_run
from apps.tasks.models import Task, TaskEvent


pytestmark = pytest.mark.django_db


def task_result(response):
    return response.json()["results"]


def test_unauthenticated_request_returns_uniform_401():
    response = APIClient().get("/api/v1/tasks/")

    assert response.status_code == 401
    assert response.json()["errors"] == {}
    assert "detail" in response.json()


def test_project_endpoints(web_client, project):
    listed = web_client.get("/api/v1/projects/")
    assert listed.status_code == 200
    assert listed.json()["results"][0]["slug"] == project.slug

    created = web_client.post(
        "/api/v1/projects/",
        {
            "name": "Another Project",
            "root_path": r"E:\home\another",
            "color": "#123ABC",
        },
        format="json",
    )
    assert created.status_code == 201
    assert created.json()["slug"] == "another-project"
    assert created.json()["code"] == "ANOTHERP"

    detail = web_client.get("/api/v1/projects/ANOTHER-PROJECT/")
    assert detail.status_code == 200

    updated = web_client.patch(
        "/api/v1/projects/another-project/",
        {"summary": "Updated", "is_pinned": True},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.json()["summary"] == "Updated"
    assert updated.json()["is_pinned"] is True


def test_task_crud_and_event_endpoints(web_client, project):
    created = web_client.post(
        "/api/v1/tasks/",
        {
            "project": project.slug,
            "title": "REST API task",
            "priority": 3,
        },
        format="json",
    )
    assert created.status_code == 201
    key = created.json()["key"]

    listed = web_client.get(
        "/api/v1/tasks/",
        {"project": project.slug, "status": "todo,in_progress", "q": "API"},
    )
    assert listed.status_code == 200
    assert [item["key"] for item in task_result(listed)] == [key]
    assert "last_human_note" not in task_result(listed)[0]

    detail = web_client.get(f"/api/v1/tasks/{key}/")
    assert detail.status_code == 200

    updated = web_client.patch(
        f"/api/v1/tasks/{key}/",
        {"status": "in_progress", "note": "着手しました"},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "in_progress"
    assert updated.json()["started_at"] is not None

    events = web_client.get(f"/api/v1/tasks/{key}/events/")
    assert events.status_code == 200
    event_types = {item["event_type"] for item in events.json()["results"]}
    assert {"created", "status_changed", "note"} <= event_types

    deleted = web_client.delete(f"/api/v1/tasks/{key}/")
    assert deleted.status_code == 204
    assert not Task.objects.filter(key=key).exists()


def test_task_actor_type_can_be_created_and_updated(web_client, project):
    created = web_client.post(
        "/api/v1/tasks/",
        {
            "project": project.slug,
            "title": "Human owned task",
            "actor_type": "human",
        },
        format="json",
    )

    assert created.status_code == 201
    assert created.json()["actor_type"] == "human"

    updated = web_client.patch(
        f"/api/v1/tasks/{created.json()['key']}/",
        {"actor_type": "agent"},
        format="json",
    )

    assert updated.status_code == 200
    assert updated.json()["actor_type"] == "agent"
    event = TaskEvent.objects.get(
        task__key=created.json()["key"],
        event_type=TaskEvent.EventType.EDITED,
    )
    assert event.payload["actor_type"] == {"from": "human", "to": "agent"}


@pytest.mark.parametrize("method", ["post", "patch"])
def test_invalid_task_actor_type_returns_400(web_client, project, method):
    if method == "post":
        response = web_client.post(
            "/api/v1/tasks/",
            {
                "project": project.slug,
                "title": "Invalid actor type",
                "actor_type": "robot",
            },
            format="json",
        )
    else:
        task = create_task(project, "Invalid actor type update")
        response = web_client.patch(
            f"/api/v1/tasks/{task['key']}/",
            {"actor_type": "robot"},
            format="json",
        )

    assert response.status_code == 400
    assert "actor_type" in response.json()["errors"]


def test_task_key_lookup_is_case_insensitive(web_client, project):
    task = create_task(project, "Case insensitive")

    response = web_client.get(f"/api/v1/tasks/{task['key'].lower()}/")

    assert response.status_code == 200
    assert response.json()["key"] == task["key"]


def test_invalid_task_ordering_returns_uniform_400(web_client):
    response = web_client.get("/api/v1/tasks/?ordering=title")

    assert response.status_code == 400
    assert response.json()["detail"] == "Validation failed."
    assert "ordering" in response.json()["errors"]


def test_task_ordering_uses_allowed_field(web_client, project):
    create_task(project, "Low", priority=1)
    create_task(project, "High", priority=3)

    response = web_client.get("/api/v1/tasks/?ordering=priority")

    assert response.status_code == 200
    assert [item["priority"] for item in task_result(response)] == [1, 3]


def test_task_list_default_excludes_hidden_statuses(web_client, project):
    included = {
        create_task(project, "Todo", status="todo")["key"],
        create_task(project, "In progress", status="in_progress")["key"],
        create_task(project, "Awaiting user", status="awaiting_user")["key"],
        create_task(project, "Blocked", status="blocked")["key"],
    }
    excluded = {
        create_task(project, "Recently done", status="done")["key"],
        create_task(project, "Cancelled", status="cancelled")["key"],
        create_task(project, "Backlog", status="backlog")["key"],
    }

    response = web_client.get("/api/v1/tasks/", {"project": project.slug})

    assert response.status_code == 200
    listed = {item["key"] for item in task_result(response)}
    assert listed == included
    assert listed.isdisjoint(excluded)


def test_task_list_returns_done_when_explicitly_requested(web_client, project):
    done = create_task(project, "Explicitly requested done", status="done")
    create_task(project, "Todo", status="todo")

    response = web_client.get(
        "/api/v1/tasks/",
        {"project": project.slug, "status": "done"},
    )

    assert response.status_code == 200
    assert [item["key"] for item in task_result(response)] == [done["key"]]


def test_pipeline_scope_cannot_access_tasks(pipeline_client):
    response = pipeline_client.get("/api/v1/tasks/")

    assert response.status_code == 403
    assert "required scope: web" in response.json()["detail"]


def test_non_web_scope_cannot_delete_task(mcp_client, project):
    task = create_task(project, "Protected")

    response = mcp_client.delete(f"/api/v1/tasks/{task['key']}/")

    assert response.status_code == 403
    assert Task.objects.filter(key=task["key"]).exists()


def test_session_list_endpoint(web_client, project):
    task = create_task(project, "Touched task")
    session = report_session(
        project,
        "Session complete",
        task_keys=[task["key"]],
        external_id="session-api-test",
    )

    response = web_client.get("/api/v1/sessions/")

    assert response.status_code == 200
    item = response.json()["results"][0]
    assert item["id"] == session["id"]
    assert item["tasks"] == [task["key"]]


def test_automation_list_includes_latest_run(web_client, automation):
    start_run(
        automation.key,
        "run-for-automation-list",
        "manual",
        timezone.now(),
    )

    response = web_client.get("/api/v1/automations/")

    assert response.status_code == 200
    item = response.json()["results"][0]
    assert item["key"] == automation.key
    assert item["name"] == automation.scheduled_task_name
    assert item["last_run"]["run_key"] == "run-for-automation-list"


def test_run_endpoints(web_client, pipeline_client, automation):
    started_at = timezone.now()
    created = pipeline_client.post(
        "/api/v1/runs/",
        {
            "automation_key": automation.key,
            "run_key": "pipeline-20260831-001",
            "status": "running",
            "trigger": "scheduled",
            "started_at": started_at.isoformat(),
            "log_path": r"E:\logs\pipeline.log",
        },
        format="json",
    )
    assert created.status_code == 201
    assert created.json()["status"] == "running"

    listed = web_client.get("/api/v1/runs/")
    assert listed.status_code == 200
    assert listed.json()["results"][0]["run_key"] == "pipeline-20260831-001"

    finished = pipeline_client.patch(
        "/api/v1/runs/pipeline-20260831-001/",
        {
            "status": "succeeded",
            "exit_code": 0,
            "ended_at": (started_at + timedelta(seconds=12)).isoformat(),
            "summary": "Completed",
        },
        format="json",
    )
    assert finished.status_code == 200
    assert finished.json()["duration_sec"] == 12


def test_web_scope_cannot_start_or_finish_run(web_client, automation):
    start = web_client.post(
        "/api/v1/runs/",
        {
            "automation_key": automation.key,
            "run_key": "forbidden-run",
            "trigger": "manual",
            "started_at": timezone.now().isoformat(),
        },
        format="json",
    )
    assert start.status_code == 403
    assert "required scope: pipeline" in start.json()["detail"]

    Run.objects.create(
        automation=automation,
        run_key="existing-run",
        trigger="manual",
        started_at=timezone.now(),
    )
    finish = web_client.patch(
        "/api/v1/runs/existing-run/",
        {"status": "failed"},
        format="json",
    )
    assert finish.status_code == 403


def test_dashboard_summary_collects_blocks_without_n_plus_one(
    web_client,
    project,
    automation,
):
    awaiting = create_task(project, "Need a decision", status="awaiting_user")
    create_task(project, "Working", status="in_progress")
    report_session(project, "Recent session", task_keys=[awaiting["key"]])

    inactive = Project.objects.create(
        slug="inactive",
        code="INACTIVE",
        name="Inactive",
        root_path=r"E:\home\inactive",
        is_active=False,
    )
    Project.objects.create(
        slug="archived",
        code="ARCHIVED",
        name="Archived",
        root_path=r"E:\home\archived",
        archived_at=timezone.now(),
    )

    with CaptureQueriesContext(connection) as queries:
        response = web_client.get("/api/v1/dashboard/summary/")

    assert response.status_code == 200
    data = response.json()
    assert data["awaiting_user"][0]["key"] == awaiting["key"]
    assert "last_human_note" not in data["awaiting_user"][0]
    assert data["in_progress"][0]["status"] == "in_progress"
    assert "last_human_note" not in data["in_progress"][0]
    assert data["automations"][0]["key"] == automation.key
    projects = {item["slug"]: item for item in data["projects"]}
    assert inactive.slug in projects
    assert projects[inactive.slug]["is_active"] is False
    assert "archived" not in projects
    assert data["recent_activity"]
    # Authentication performs two queries; the summary itself remains eight queries
    # (the eighth reads active repositories in one query).
    assert len(queries) <= 10


def test_dashboard_summary_separates_open_human_tasks(web_client, project):
    human_todo = create_task(
        project,
        "Human todo",
        priority=3,
        actor_type="human",
    )
    human_in_progress = create_task(
        project,
        "Human in progress",
        priority=2,
        status="in_progress",
        actor_type="human",
    )
    human_blocked = create_task(
        project,
        "Human blocked",
        priority=1,
        status="blocked",
        actor_type="human",
    )
    create_task(project, "Human done", status="done", actor_type="human")
    human_awaiting = create_task(
        project,
        "Human awaiting",
        status="awaiting_user",
        actor_type="human",
    )
    agent_in_progress = create_task(project, "Agent working", status="in_progress")
    archived = Project.objects.create(
        slug="human-archived",
        code="HARCHIVE",
        name="Human Archived",
        root_path=r"E:\home\human-archived",
        archived_at=timezone.now(),
    )
    create_task(archived, "Archived human", actor_type="human")

    response = web_client.get("/api/v1/dashboard/summary/")

    assert response.status_code == 200
    data = response.json()
    assert [task["key"] for task in data["human_tasks"]] == [
        human_todo["key"],
        human_in_progress["key"],
        human_blocked["key"],
    ]
    assert [task["key"] for task in data["in_progress"]] == [
        agent_in_progress["key"]
    ]
    assert human_awaiting["key"] in [task["key"] for task in data["awaiting_user"]]


def test_get_project_separates_agent_and_human_tasks(project):
    agent_task = create_task(project, "Agent task", status="todo")
    human_task = create_task(
        project,
        "Human task",
        status="blocked",
        actor_type="human",
    )
    task = Task.objects.get(key=human_task["key"])
    TaskEvent.objects.create(
        task=task,
        event_type=TaskEvent.EventType.NOTE,
        actor=Task.Actor.HUMAN,
        body="本人の進捗",
    )

    result = domain.get_project(project.slug)

    assert [item["key"] for item in result["tasks"]] == [agent_task["key"]]
    assert [item["key"] for item in result["human_tasks"]] == [human_task["key"]]
    assert result["human_tasks"][0]["last_human_note"]["body"] == "本人の進捗"


def test_mcp_task_queries_stay_flat_as_task_count_grows():
    small = Project.objects.create(
        slug="query-small",
        code="QSMALL",
        name="Query Small",
        root_path=r"E:\home\query-small",
    )
    large = Project.objects.create(
        slug="query-large",
        code="QLARGE",
        name="Query Large",
        root_path=r"E:\home\query-large",
    )
    for number in range(3):
        create_task(small, f"Small {number}")
    for number in range(30):
        create_task(large, f"Large {number}")

    with CaptureQueriesContext(connection) as small_project_queries:
        small_project_result = domain.get_project(small.slug)
    with CaptureQueriesContext(connection) as large_project_queries:
        large_project_result = domain.get_project(large.slug)
    with CaptureQueriesContext(connection) as small_list_queries:
        small_list_result = domain.list_tasks(project=small.slug)
    with CaptureQueriesContext(connection) as large_list_queries:
        large_list_result = domain.list_tasks(project=large.slug)

    assert len(small_project_result["tasks"]) == 3
    assert len(large_project_result["tasks"]) == 30
    assert len(small_list_result) == 3
    assert len(large_list_result) == 30
    assert len(small_project_queries) == len(large_project_queries)
    assert len(small_list_queries) == len(large_list_queries)


def test_schema_endpoints_are_available_to_web_scope(web_client):
    schema = web_client.get("/api/schema/")
    swagger = web_client.get("/api/schema/swagger-ui/")

    assert schema.status_code == 200
    assert swagger.status_code == 200


def test_domain_errors_use_uniform_404(web_client):
    response = web_client.get("/api/v1/tasks/UNKNOWN-999/")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Task could not be resolved: UNKNOWN-999",
        "errors": {},
    }


def test_task_updates_create_expected_events(web_client, project):
    task = create_task(project, "Original")

    response = web_client.patch(
        f"/api/v1/tasks/{task['key']}/",
        {"title": "Renamed", "status": "done", "note": "Finished"},
        format="json",
    )

    assert response.status_code == 200
    assert TaskEvent.objects.filter(task__key=task["key"], event_type="edited").exists()
    assert TaskEvent.objects.filter(
        task__key=task["key"], event_type="status_changed"
    ).exists()
    assert TaskEvent.objects.filter(task__key=task["key"], event_type="note").exists()
