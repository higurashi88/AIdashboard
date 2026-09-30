import importlib

import pytest
from django.apps import apps as django_apps
from rest_framework.test import APIClient

from apps.core.models import ApiKey, AppSetting
from apps.projects.models import Repository
from apps.services import app_settings
from apps.services.api_keys import create_api_key


pytestmark = pytest.mark.django_db


# --- 設定画面 -------------------------------------------------------------------

def test_settings_default_values(web_client):
    response = web_client.get("/api/v1/settings/")

    assert response.status_code == 200
    body = response.json()
    assert body["discord"] == {
        "bot_token_set": False,
        "bot_token_hint": "",
        "channel_id": "",
        "mention_user_id": "",
        "daily_summary_time": "08:00",
        "poll_interval_sec": 60,
    }
    assert body["notifications"] == {
        "awaiting_user": True,
        "failed_runs": True,
        "daily_summary": True,
        "projects": [],
    }
    assert body["backup"] == {"keep": 7}
    assert body["discord_status"]["state"] == "unknown"
    assert body["updated_at"] is None


def test_settings_update_hides_token_and_bot_can_read_it(web_client, discord_client, project):
    response = web_client.patch(
        "/api/v1/settings/",
        {
            "discord": {
                "bot_token": "abc.DEF.secret-token-1234",
                "channel_id": "123456789012345678",
                "daily_summary_time": "07:30",
            },
            "notifications": {"failed_runs": False, "projects": [project.slug, project.slug]},
            "backup": {"keep": 14},
        },
        format="json",
    )

    assert response.status_code == 200
    body = response.json()
    assert "secret-token" not in response.content.decode()
    assert body["discord"]["bot_token_set"] is True
    assert body["discord"]["bot_token_hint"] == "1234"
    assert body["discord"]["channel_id"] == "123456789012345678"
    assert body["discord"]["daily_summary_time"] == "07:30"
    assert body["discord"]["poll_interval_sec"] == 60
    assert body["notifications"]["failed_runs"] is False
    assert body["notifications"]["awaiting_user"] is True
    assert body["notifications"]["projects"] == [project.slug]
    assert body["backup"] == {"keep": 14}
    assert body["updated_at"] is not None

    config = discord_client.get("/api/v1/discord/config/")
    assert config.status_code == 200
    assert config.json()["bot_token"] == "abc.DEF.secret-token-1234"
    assert config.json()["channel_id"] == "123456789012345678"
    assert config.json()["notifications"]["projects"] == [project.slug]
    assert config.json()["time_zone"]


def test_settings_partial_update_keeps_token_and_blank_clears_it(web_client):
    web_client.patch("/api/v1/settings/", {"discord": {"bot_token": "token-abcd"}}, format="json")

    kept = web_client.patch("/api/v1/settings/", {"discord": {"channel_id": "42"}}, format="json")
    assert kept.json()["discord"]["bot_token_set"] is True

    cleared = web_client.patch("/api/v1/settings/", {"discord": {"bot_token": ""}}, format="json")
    assert cleared.json()["discord"]["bot_token_set"] is False
    assert app_settings.get_value(app_settings.DISCORD_BOT_TOKEN) == ""


@pytest.mark.parametrize(
    "payload",
    [
        {"discord": {"channel_id": "general"}},
        {"discord": {"mention_user_id": "@me"}},
        {"discord": {"daily_summary_time": "8:00"}},
        {"discord": {"daily_summary_time": "24:00"}},
        {"discord": {"poll_interval_sec": 5}},
        {"discord": {"bot_token": "has space"}},
        {"notifications": {"projects": ["no-such-project"]}},
        {"backup": {"keep": 0}},
        {},
    ],
)
def test_settings_update_rejects_invalid_values(web_client, payload):
    response = web_client.patch("/api/v1/settings/", payload, format="json")

    assert response.status_code == 400
    assert not AppSetting.objects.exclude(key__startswith="discord.status").exists()


def test_settings_scopes(discord_client, pipeline_client, mcp_client, web_client):
    assert discord_client.get("/api/v1/settings/").status_code == 403
    assert pipeline_client.get("/api/v1/settings/").status_code == 403
    assert web_client.get("/api/v1/discord/config/").status_code == 403
    assert mcp_client.get("/api/v1/discord/config/").status_code == 403
    assert web_client.post("/api/v1/discord/status/", {"state": "connected"}).status_code == 403
    assert discord_client.post("/api/v1/settings/discord/test/").status_code == 403

    assert pipeline_client.get("/api/v1/settings/backup/").json() == {"keep": 7}
    assert discord_client.get("/api/v1/settings/backup/").status_code == 403


def test_discord_test_request_and_status_report(web_client, discord_client):
    requested = web_client.post("/api/v1/settings/discord/test/")
    assert requested.status_code == 202
    requested_at = requested.json()["test_requested_at"]
    assert requested_at

    assert discord_client.get("/api/v1/discord/config/").json()["test_requested_at"] == requested_at

    report = discord_client.post(
        "/api/v1/discord/status/",
        {"state": "connected", "bot_user": "dashboard#0001", "test_handled_at": requested_at},
        format="json",
    )
    assert report.status_code == 200

    status = web_client.get("/api/v1/settings/").json()["discord_status"]
    assert status["state"] == "connected"
    assert status["bot_user"] == "dashboard#0001"
    assert status["test_handled_at"] == requested_at
    assert status["test_error"] == ""
    assert status["reported_at"]

    # テスト結果を含まない報告でも、前回のテスト結果は残る
    discord_client.post("/api/v1/discord/status/", {"state": "connected"}, format="json")
    assert web_client.get("/api/v1/settings/").json()["discord_status"]["test_handled_at"] == requested_at


def test_discord_status_rejects_unknown_state(discord_client):
    response = discord_client.post("/api/v1/discord/status/", {"state": "happy"}, format="json")

    assert response.status_code == 400


def test_env_import_migration_copies_discord_values_once(monkeypatch):
    migration = importlib.import_module(
        "apps.core.migrations.0004_import_discord_settings_from_env"
    )
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "from-env-token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "111")
    monkeypatch.setenv("DISCORD_POLL_INTERVAL_SEC", "5")
    monkeypatch.delenv("DISCORD_MENTION_USER_ID", raising=False)
    AppSetting.objects.create(key="discord.channel_id", value="999")

    migration.import_from_env(django_apps, None)

    values = app_settings.get_values()
    assert values[app_settings.DISCORD_BOT_TOKEN] == "from-env-token"
    # 既に保存済みの値は上書きしない
    assert values[app_settings.DISCORD_CHANNEL_ID] == "999"
    assert values[app_settings.DISCORD_POLL_INTERVAL_SEC] == 10
    assert values[app_settings.DISCORD_MENTION_USER_ID] == ""


# --- APIキー ----------------------------------------------------------------------

def test_api_key_list_marks_current_key_and_hides_hash(web_client):
    create_api_key("pipeline-host", ApiKey.Scope.PIPELINE)

    response = web_client.get("/api/v1/api-keys/")

    assert response.status_code == 200
    keys = response.json()
    assert {key["scope"] for key in keys} == {"web", "pipeline"}
    current = [key for key in keys if key["is_current"]]
    assert len(current) == 1 and current[0]["scope"] == "web"
    assert all("key_hash" not in key and "key" not in key for key in keys)


def test_api_key_create_returns_plaintext_once_and_it_works(web_client):
    response = web_client.post(
        "/api/v1/api-keys/", {"name": " new-bot ", "scope": "discord"}, format="json"
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "new-bot"
    assert body["key"].startswith(body["prefix"])

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Api-Key {body['key']}")
    assert client.get("/api/v1/discord/config/").status_code == 200

    listed = web_client.get("/api/v1/api-keys/").json()
    assert all("key" not in key for key in listed)


def test_api_key_can_be_deactivated_and_reactivated(web_client):
    api_key, raw_key = create_api_key("old-pipeline", ApiKey.Scope.PIPELINE)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Api-Key {raw_key}")

    response = web_client.patch(
        f"/api/v1/api-keys/{api_key.pk}/", {"is_active": False}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert client.get("/api/v1/settings/backup/").status_code == 401

    web_client.patch(f"/api/v1/api-keys/{api_key.pk}/", {"is_active": True}, format="json")
    assert client.get("/api/v1/settings/backup/").status_code == 200


def test_api_key_cannot_deactivate_the_key_used_by_the_screen(web_client):
    current = web_client.get("/api/v1/api-keys/").json()[0]

    response = web_client.patch(
        f"/api/v1/api-keys/{current['id']}/", {"is_active": False}, format="json"
    )

    assert response.status_code == 400
    assert ApiKey.objects.get(pk=current["id"]).is_active is True


def test_api_key_endpoints_validate_input(web_client):
    assert web_client.post("/api/v1/api-keys/", {"name": "x", "scope": "admin"}, format="json").status_code == 400
    missing = web_client.patch(
        "/api/v1/api-keys/00000000-0000-0000-0000-000000000000/", {"name": "x"}, format="json"
    )
    assert missing.status_code == 404


def test_api_keys_are_web_only(pipeline_client, discord_client):
    assert pipeline_client.get("/api/v1/api-keys/").status_code == 403
    assert discord_client.post("/api/v1/api-keys/", {"name": "x", "scope": "web"}, format="json").status_code == 403


# --- リポジトリの管理 -------------------------------------------------------------

def test_repository_create_list_update_delete(web_client, pipeline_client, project):
    created = web_client.post(
        "/api/v1/repositories/",
        {"path": "C:\\src\\my-app\\", "project": project.slug},
        format="json",
    )
    assert created.status_code == 201
    body = created.json()
    assert body["path"] == "C:\\src\\my-app"
    assert body["name"] == "my-app"
    assert body["project"] == project.slug
    assert body["is_active"] is True

    repository = Repository.objects.get(pk=body["id"])
    repository.branch = "main"
    repository.save()

    updated = web_client.patch(
        f"/api/v1/repositories/{body['id']}/",
        {"path": "C:\\src\\renamed", "project": None, "is_active": False},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.json()["project"] is None
    assert updated.json()["branch"] == ""
    # 名前は明示しない限り変わらない
    assert updated.json()["name"] == "my-app"

    assert pipeline_client.get("/api/v1/repositories/").json() == []
    everything = web_client.get("/api/v1/repositories/?include_inactive=true").json()
    assert [item["path"] for item in everything] == ["C:\\src\\renamed"]

    deleted = web_client.delete(f"/api/v1/repositories/{body['id']}/")
    assert deleted.status_code == 204
    assert not Repository.objects.exists()


@pytest.mark.parametrize(
    "payload",
    [
        {"path": "relative\\path"},
        {"path": "C:\\src\\x", "project": "no-such-project"},
        {"path": ""},
    ],
)
def test_repository_create_rejects_invalid_input(web_client, payload):
    assert web_client.post("/api/v1/repositories/", payload, format="json").status_code == 400


def test_repository_path_must_be_unique_ignoring_case(web_client):
    Repository.objects.create(name="app", path="C:\\src\\App")

    response = web_client.post("/api/v1/repositories/", {"path": "c:\\SRC\\app"}, format="json")

    assert response.status_code == 400


def test_repository_write_is_web_only(pipeline_client):
    response = pipeline_client.post("/api/v1/repositories/", {"path": "C:\\src\\x"}, format="json")

    assert response.status_code == 403


def test_repository_unknown_id_returns_404(web_client):
    response = web_client.delete("/api/v1/repositories/00000000-0000-0000-0000-000000000000/")

    assert response.status_code == 404
