import asyncio
import json
import logging
from datetime import timedelta

import pytest
from asgiref.sync import sync_to_async
from django.db import connections
from django.utils import timezone
from starlette.testclient import TestClient

from apps.core.models import ApiKey
from apps.mcp.authentication import McpApiKeyMiddleware
from apps.mcp import tools as mcp_tools
from apps.mcp.server import mcp_asgi_application
from apps.services import create_task
from apps.services.api_keys import create_api_key
from apps.tasks.models import Task, TaskEvent


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def close_mcp_test_connections():
    yield

    async def close_thread_connection():
        await sync_to_async(connections.close_all, thread_sensitive=True)()

    asyncio.run(close_thread_connection())
    connections.close_all()


@pytest.fixture(scope="module")
def mcp_transport_client():
    with TestClient(mcp_asgi_application) as client:
        yield client


def run_tool(function, **arguments):
    return asyncio.run(function(**arguments))


def test_list_projects_tool(project):
    result = run_tool(mcp_tools.list_projects)

    assert result[0]["slug"] == project.slug


def test_get_project_tool_by_slug_and_cwd(project):
    by_slug = run_tool(mcp_tools.get_project, slug=project.slug)
    by_cwd = run_tool(
        mcp_tools.get_project,
        cwd=project.root_path + r"\src\nested",
    )

    assert by_slug["slug"] == project.slug
    assert by_cwd["slug"] == project.slug


def test_list_tasks_tool(project):
    created = create_task(project, "Find from MCP", status="todo")

    result = run_tool(
        mcp_tools.list_tasks,
        project=project.slug,
        status="todo,in_progress",
        query="MCP",
    )

    assert [item["key"] for item in result] == [created["key"]]


def test_get_project_and_list_tasks_include_latest_human_note(project):
    created = create_task(project, "Answered task", status="todo")
    task = Task.objects.get(key=created["key"])
    base_at = timezone.now() - timedelta(hours=1)
    TaskEvent.objects.create(
        task=task,
        event_type=TaskEvent.EventType.NOTE,
        actor=Task.Actor.HUMAN,
        body="古い回答",
        occurred_at=base_at,
    )
    latest_note_at = base_at + timedelta(minutes=1)
    TaskEvent.objects.create(
        task=task,
        event_type=TaskEvent.EventType.NOTE,
        actor=Task.Actor.HUMAN,
        body="本人の最新回答",
        occurred_at=latest_note_at,
    )
    TaskEvent.objects.create(
        task=task,
        event_type=TaskEvent.EventType.EDITED,
        actor=Task.Actor.HUMAN,
        body="humanだがnoteではない",
        occurred_at=latest_note_at + timedelta(minutes=1),
    )
    for offset in range(2, 13):
        TaskEvent.objects.create(
            task=task,
            event_type=TaskEvent.EventType.NOTE,
            actor=Task.Actor.CODEX,
            body=f"後続のエージェント活動 {offset}",
            occurred_at=base_at + timedelta(minutes=offset),
        )

    project_result = run_tool(mcp_tools.get_project, slug=project.slug)
    list_result = run_tool(mcp_tools.list_tasks, project=project.slug, status="todo")

    expected = {
        "body": "本人の最新回答",
        "at": timezone.localtime(latest_note_at).isoformat(),
    }
    project_task = next(item for item in project_result["tasks"] if item["key"] == task.key)
    listed_task = next(item for item in list_result if item["key"] == task.key)
    assert project_task["last_human_note"] == expected
    assert listed_task["last_human_note"] == expected
    assert all(
        item["body"] != "本人の最新回答"
        for item in project_result["recent_activity"]
    )


def test_get_project_and_list_tasks_return_none_without_human_note(project):
    created = create_task(project, "No answer", status="todo")

    project_result = run_tool(mcp_tools.get_project, slug=project.slug)
    list_result = run_tool(mcp_tools.list_tasks, project=project.slug, status="todo")

    project_task = next(
        item for item in project_result["tasks"] if item["key"] == created["key"]
    )
    listed_task = next(item for item in list_result if item["key"] == created["key"])
    assert project_task["last_human_note"] is None
    assert listed_task["last_human_note"] is None


def test_create_task_tool_defaults_to_claude_code(project):
    result = run_tool(
        mcp_tools.create_task,
        project=project.slug,
        title="Created over MCP",
        priority=2,
    )

    assert result["key"].startswith(f"{project.code}-")
    assert result["created_by"] == "claude_code"


def test_create_task_tool_accepts_actor_type(project):
    result = run_tool(
        mcp_tools.create_task,
        project=project.slug,
        title="Human task over MCP",
        actor_type="human",
    )

    assert result["actor_type"] == "human"
    assert Task.objects.get(key=result["key"]).actor_type == Task.ActorType.HUMAN


def test_update_task_tool_adds_note_and_actor(project):
    task = create_task(project, "Update over MCP")

    result = run_tool(
        mcp_tools.update_task,
        key=task["key"],
        status="in_progress",
        note="MCPから着手",
        agent="codex",
    )

    assert result["status"] == "in_progress"
    events = list(project.tasks.get(key=task["key"]).events.values("event_type", "actor"))
    assert {item["event_type"] for item in events} >= {"status_changed", "note"}
    assert all(
        item["actor"] == "codex"
        for item in events
        if item["event_type"] in {"status_changed", "note"}
    )


def test_update_task_tool_accepts_actor_type(project):
    task = create_task(project, "Hand over to human")

    result = run_tool(
        mcp_tools.update_task,
        key=task["key"],
        actor_type="human",
    )

    assert result["actor_type"] == "human"
    edited = project.tasks.get(key=task["key"]).events.get(
        event_type=TaskEvent.EventType.EDITED
    )
    assert edited.payload["actor_type"] == {"from": "agent", "to": "human"}


def test_report_session_tool_persists_task_relation(project):
    task = create_task(project, "Session task")

    result = run_tool(
        mcp_tools.report_session,
        project=project.slug,
        summary="MCPセッションを完了",
        task_keys=[task["key"]],
    )

    assert result["agent"] == "claude_code"
    assert result["task_keys"] == [task["key"]]


def test_unregistered_cwd_returns_actionable_japanese_error(project):
    result = run_tool(mcp_tools.get_project, cwd=r"Z:\unregistered\project")

    assert result["ok"] is False
    assert "list_projects()" in result["error"]
    assert "プロジェクトを特定できませんでした" in result["error"]
    assert project.slug in result["error"]


def test_tool_validation_error_is_a_result_not_protocol_exception(project):
    result = run_tool(
        mcp_tools.create_task,
        project=project.slug,
        title="",
    )

    assert result["ok"] is False
    assert result["error"].startswith("入力内容を確認してください。")


class RecordingApplication:
    def __init__(self):
        self.called = False

    async def __call__(self, scope, receive, send):
        self.called = True
        await send(
            {
                "type": "http.response.start",
                "status": 204,
                "headers": [],
            }
        )
        await send({"type": "http.response.body", "body": b""})


async def invoke_middleware(raw_key=None):
    downstream = RecordingApplication()
    middleware = McpApiKeyMiddleware(downstream)
    messages = []
    headers = []
    if raw_key is not None:
        headers.append((b"authorization", f"Api-Key {raw_key}".encode("ascii")))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "headers": headers,
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await middleware(scope, receive, send)
    return downstream, messages


def response_body(messages):
    body = next(message["body"] for message in messages if message["type"] == "http.response.body")
    return json.loads(body.decode("utf-8"))


def initialize_mcp(client, raw_key, host):
    return client.post(
        "/mcp",
        headers={
            "Authorization": f"Api-Key {raw_key}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "Host": host,
            "Origin": "http://localhost:8770",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "1.0"},
            },
        },
        follow_redirects=False,
    )


def test_mcp_transport_rejects_untrusted_host_with_421(mcp_transport_client):
    _, raw_key = create_api_key("mcp-invalid-host-test", ApiKey.Scope.MCP)

    response = initialize_mcp(mcp_transport_client, raw_key, "evil.example")

    assert response.status_code == 421


def test_mcp_transport_accepts_configured_host_with_200(mcp_transport_client):
    _, raw_key = create_api_key("mcp-allowed-host-test", ApiKey.Scope.MCP)

    response = initialize_mcp(mcp_transport_client, raw_key, "127.0.0.1")

    assert response.status_code == 200


def test_mcp_scope_key_is_accepted():
    api_key, raw_key = create_api_key("mcp-transport-test", ApiKey.Scope.MCP)

    downstream, messages = asyncio.run(invoke_middleware(raw_key))

    assert downstream.called is True
    assert messages[0]["status"] == 204
    api_key.refresh_from_db()
    assert api_key.last_used_at is not None


@pytest.mark.parametrize("scope", [ApiKey.Scope.WEB, ApiKey.Scope.PIPELINE])
def test_non_mcp_scope_key_is_rejected_with_protocol_error(scope):
    _, raw_key = create_api_key(f"{scope}-transport-test", scope)

    downstream, messages = asyncio.run(invoke_middleware(raw_key))

    assert downstream.called is False
    assert messages[0]["status"] == 403
    body = response_body(messages)
    assert body["jsonrpc"] == "2.0"
    assert "mcpスコープ" in body["error"]["message"]


def test_missing_api_key_is_rejected_with_protocol_error():
    downstream, messages = asyncio.run(invoke_middleware())

    assert downstream.called is False
    assert messages[0]["status"] == 401
    body = response_body(messages)
    assert body["jsonrpc"] == "2.0"
    assert "MCP認証が必要" in body["error"]["message"]


def test_every_tool_call_is_logged(caplog, project):
    caplog.set_level(logging.INFO, logger="apps.mcp.tools")

    run_tool(mcp_tools.list_projects)

    record = next(record for record in caplog.records if record.msg == "mcp_tool_call")
    assert record.mcp_tool == "list_projects"
    assert record.mcp_success is True
    assert record.mcp_arguments == {}
    assert record.mcp_duration_ms >= 0


def test_asgi_router_keeps_rest_on_django_and_routes_mcp(monkeypatch):
    from config import asgi

    django_recorder = RecordingApplication()
    mcp_recorder = RecordingApplication()
    monkeypatch.setattr(asgi, "django_application", django_recorder)
    monkeypatch.setattr(asgi, "mcp_asgi_application", mcp_recorder)
    router = asgi.PathRoutingApplication()

    async def invoke(path):
        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        await router(
            {"type": "http", "method": "GET", "path": path, "headers": []},
            receive,
            send,
        )

    asyncio.run(invoke("/api/v1/healthz/"))
    assert django_recorder.called is True
    assert mcp_recorder.called is False

    django_recorder.called = False
    asyncio.run(invoke("/mcp"))
    assert django_recorder.called is False
    assert mcp_recorder.called is True
    connections.close_all()
