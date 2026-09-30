from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.automations.models import Automation
from apps.projects.models import Project
from apps.services import create_task, update_task
from apps.tasks.models import TaskEvent


pytestmark = pytest.mark.django_db


SEED_CONFIG = """
[[project]]
slug = "demo"
code = "DEMO"
name = "デモPJ"
root_path = 'C:\\\\demo'

[[automation]]
key = "demo-nightly"
project = "demo"
name = "デモ 夜間実行"
scheduled_task_name = "Demo_Nightly"
schedule_human = "毎日 02:00"
state = "active"

[[automation]]
key = "demo-paused"
project = "demo"
name = "デモ 停止中"
state = "paused"
"""


def write_seed_config(tmp_path, body=SEED_CONFIG):
    path = tmp_path / "projects.toml"
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_seed_sets_automation_display_names(tmp_path):
    # 利用者ごとに異なる config/projects.toml へ依存しないよう、一時ファイルを渡す
    call_command("seed_initial_data", config=write_seed_config(tmp_path))

    assert dict(Automation.objects.values_list("key", "name")) == {
        "demo-nightly": "デモ 夜間実行",
        "demo-paused": "デモ 停止中",
    }
    assert Project.objects.get(slug="demo").code == "DEMO"


def test_seed_is_idempotent(tmp_path):
    config = write_seed_config(tmp_path)
    call_command("seed_initial_data", config=config)
    call_command("seed_initial_data", config=config)

    assert Project.objects.filter(slug="demo").count() == 1
    assert Automation.objects.count() == 2


def test_seed_rejects_automation_pointing_at_unknown_project(tmp_path):
    from django.core.management.base import CommandError

    body = SEED_CONFIG.replace('project = "demo"\nname = "デモ 夜間実行"',
                               'project = "missing"\nname = "デモ 夜間実行"')
    with pytest.raises(CommandError, match="missing"):
        call_command("seed_initial_data", config=write_seed_config(tmp_path, body))


def test_seed_rejects_missing_config_file():
    from django.core.management.base import CommandError

    with pytest.raises(CommandError, match="見つかりません"):
        call_command("seed_initial_data", config="/nonexistent/projects.toml")


def test_automation_name_falls_back_in_dashboard(web_client, project):
    Automation.objects.create(
        key="fallback-scheduled",
        project=project,
        name="",
        scheduled_task_name="Windows_Task_Name",
    )
    Automation.objects.create(
        key="fallback-key",
        project=project,
        name="",
        scheduled_task_name="",
    )

    response = web_client.get("/api/v1/dashboard/summary/")

    names = {item["key"]: item["name"] for item in response.json()["automations"]}
    assert names["fallback-scheduled"] == "Windows_Task_Name"
    assert names["fallback-key"] == "fallback-key"


def test_update_task_replaces_due_at_tags_and_parent(project):
    parent = create_task(project, "Parent")
    task = create_task(project, "Child")
    due_at = timezone.now() + timedelta(days=2)

    updated = update_task(
        task["key"],
        due_at=due_at,
        tags=["api", "important"],
        parent=parent["key"],
    )

    assert updated["due_at"] is not None
    assert updated["tags"] == ["api", "important"]
    assert updated["parent"] == parent["key"]
    event = TaskEvent.objects.filter(
        task__key=task["key"],
        event_type=TaskEvent.EventType.EDITED,
    ).first()
    assert set(event.payload) >= {"due_at", "tags", "parent"}
    assert event.payload["tags"]["to"] == ["api", "important"]
    assert event.payload["parent"]["to"] == parent["key"]


def test_update_task_can_clear_due_at_tags_and_parent(project):
    parent = create_task(project, "Parent")
    task = create_task(project, "Child", parent=parent["key"])
    due_at = timezone.now() + timedelta(days=1)
    update_task(task["key"], due_at=due_at, tags=["temporary"])

    updated = update_task(task["key"], due_at=None, tags=[], parent=None)

    assert updated["due_at"] is None
    assert updated["tags"] == []
    assert updated["parent"] is None


def test_update_task_rejects_parent_cycles(project):
    root = create_task(project, "Root")
    child = create_task(project, "Child", parent=root["key"])
    grandchild = create_task(project, "Grandchild", parent=child["key"])

    with pytest.raises(ValidationError, match="descendant"):
        update_task(root["key"], parent=grandchild["key"])
    with pytest.raises(ValidationError, match="itself"):
        update_task(root["key"], parent=root["key"])


def test_update_task_rejects_parent_from_another_project(project):
    other = Project.objects.create(
        slug="other-project",
        code="OTHER",
        name="Other",
        root_path=r"E:\home\other",
    )
    task = create_task(project, "Task")
    foreign_parent = create_task(other, "Foreign")

    with pytest.raises(ValidationError, match="same project"):
        update_task(task["key"], parent=foreign_parent["key"])


def test_rest_patch_updates_due_at_tags_and_parent(web_client, project):
    parent = create_task(project, "Parent")
    task = create_task(project, "Task")
    due_at = timezone.now() + timedelta(hours=3)

    response = web_client.patch(
        f"/api/v1/tasks/{task['key']}/",
        {
            "due_at": due_at.isoformat(),
            "tags": ["rest", "日本語"],
            "parent": parent["key"],
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["tags"] == ["rest", "日本語"]
    assert response.json()["parent"] == parent["key"]
    assert response.json()["due_at"] is not None


def test_schema_and_swagger_are_public():
    client = APIClient()

    assert client.get("/api/schema/").status_code == 200
    assert client.get("/api/schema/swagger-ui/").status_code == 200


def test_repeated_auth_failures_are_throttled(db):
    """APIキーの総当たりが抑止されること。

    DRF の throttle は認証成功後にしか走らないため、
    ApiKeyAuthentication 側で失敗回数を数えている。
    """
    from django.core.cache import cache

    cache.clear()
    client = APIClient()
    limit = 10

    statuses = []
    for index in range(limit + 5):
        client.credentials(HTTP_AUTHORIZATION=f"Api-Key wrong-{index}")
        statuses.append(client.get("/api/v1/tasks/").status_code)

    assert 401 in statuses, "不正キーが 401 にならない"
    assert 429 in statuses, "失敗を繰り返しても抑止されていない"
    assert statuses.index(429) > statuses.index(401), "最初から抑止されている"
    cache.clear()


def test_successful_auth_clears_failure_counter(db):
    from django.core.cache import cache

    from apps.services.api_keys import create_api_key

    cache.clear()
    _, raw = create_api_key(name="clears", scope="web")
    client = APIClient()

    for index in range(5):
        client.credentials(HTTP_AUTHORIZATION=f"Api-Key bad-{index}")
        client.get("/api/v1/tasks/")

    client.credentials(HTTP_AUTHORIZATION=f"Api-Key {raw}")
    assert client.get("/api/v1/tasks/").status_code == 200

    # 成功でカウンタが消えるので、再び失敗しても即座には抑止されない
    client.credentials(HTTP_AUTHORIZATION="Api-Key bad-again")
    assert client.get("/api/v1/tasks/").status_code == 401
    cache.clear()
