from datetime import timedelta

import pytest
from django.utils import timezone

from apps.automations.models import Run
from apps.services import domain
from apps.tasks.models import TaskEvent


pytestmark = pytest.mark.django_db


def test_event_feed_without_cursor_returns_latest_id_only(discord_client, project):
    domain.create_task(project=project.slug, title="first", created_by="claude_code")
    latest = TaskEvent.objects.order_by("-id").first().id

    response = discord_client.get("/api/v1/events/")

    assert response.status_code == 200
    assert response.json() == {"results": [], "next_after": latest}


def test_event_feed_returns_events_after_cursor_in_ascending_order(discord_client, project):
    domain.create_task(project=project.slug, title="first", created_by="claude_code")
    cursor = discord_client.get("/api/v1/events/").json()["next_after"]
    created = domain.create_task(project=project.slug, title="second", created_by="claude_code")
    domain.update_task(
        created["key"],
        status="awaiting_user",
        note="判断してほしいこと",
        actor="claude_code",
    )

    body = discord_client.get(f"/api/v1/events/?after={cursor}").json()

    ids = [event["id"] for event in body["results"]]
    assert ids == sorted(ids)
    assert body["next_after"] == ids[-1]
    event_types = [event["event_type"] for event in body["results"]]
    assert event_types == ["created", "status_changed", "note"]
    status_event = body["results"][1]
    assert status_event["task_key"] == created["key"]
    assert status_event["task_title"] == "second"
    assert status_event["task_status"] == "awaiting_user"
    assert status_event["project"] == project.slug
    assert status_event["project_name"] == project.name
    assert status_event["payload"] == {"from": "todo", "to": "awaiting_user"}
    assert body["results"][2]["body"] == "判断してほしいこと"

    again = discord_client.get(f"/api/v1/events/?after={body['next_after']}").json()
    assert again == {"results": [], "next_after": body["next_after"]}


def test_event_feed_respects_limit(discord_client, project):
    cursor = discord_client.get("/api/v1/events/").json()["next_after"]
    for index in range(3):
        domain.create_task(project=project.slug, title=f"task {index}", created_by="claude_code")

    body = discord_client.get(f"/api/v1/events/?after={cursor}&limit=2").json()

    assert len(body["results"]) == 2
    assert body["next_after"] == body["results"][-1]["id"]


@pytest.mark.parametrize("query", ["after=-1", "after=abc", "limit=0", "limit=201"])
def test_event_feed_rejects_invalid_query(discord_client, query):
    response = discord_client.get(f"/api/v1/events/?{query}")

    assert response.status_code == 400


def test_run_list_filters_by_status_and_end_time(discord_client, automation):
    now = timezone.now()
    old_failed = Run.objects.create(
        automation=automation,
        run_key="old-failed",
        status=Run.Status.FAILED,
        trigger="scheduled",
        started_at=now - timedelta(hours=3),
        ended_at=now - timedelta(hours=2),
    )
    new_failed = Run.objects.create(
        automation=automation,
        run_key="new-failed",
        status=Run.Status.FAILED,
        trigger="scheduled",
        started_at=now - timedelta(minutes=10),
        ended_at=now - timedelta(minutes=5),
    )
    Run.objects.create(
        automation=automation,
        run_key="new-succeeded",
        status=Run.Status.SUCCEEDED,
        trigger="scheduled",
        started_at=now - timedelta(minutes=10),
        ended_at=now - timedelta(minutes=5),
    )
    cutoff = (now - timedelta(hours=1)).isoformat()

    response = discord_client.get(
        "/api/v1/runs/", {"status": "failed", "ended_after": cutoff}
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert [run["run_key"] for run in results] == [new_failed.run_key]
    assert results[0]["automation_name"] == "Sample Scheduled Task"
    assert old_failed.run_key not in {run["run_key"] for run in results}


def test_discord_scope_can_read_dashboard_summary(discord_client):
    response = discord_client.get("/api/v1/dashboard/summary/")

    assert response.status_code == 200


def test_discord_scope_is_read_only(discord_client, project, automation):
    created = domain.create_task(project=project.slug, title="target", created_by="claude_code")

    assert discord_client.get("/api/v1/tasks/").status_code == 403
    assert discord_client.get(f"/api/v1/tasks/{created['key']}/").status_code == 403
    assert (
        discord_client.patch(
            f"/api/v1/tasks/{created['key']}/", {"status": "done"}, format="json"
        ).status_code
        == 403
    )
    assert (
        discord_client.post(
            "/api/v1/tasks/", {"project": project.slug, "title": "x"}, format="json"
        ).status_code
        == 403
    )
    assert (
        discord_client.post(
            "/api/v1/runs/",
            {
                "automation": automation.key,
                "run_key": "discord-run",
                "trigger": "manual",
                "started_at": timezone.now().isoformat(),
            },
            format="json",
        ).status_code
        == 403
    )
    assert discord_client.get("/api/v1/projects/").status_code == 403


def test_other_scopes_cannot_read_event_feed(pipeline_client, mcp_client):
    assert pipeline_client.get("/api/v1/events/").status_code == 403
    assert mcp_client.get("/api/v1/events/").status_code == 403


def test_web_scope_can_read_event_feed(web_client):
    assert web_client.get("/api/v1/events/").status_code == 200
