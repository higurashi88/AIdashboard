import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.projects.models import Repository
from apps.services import domain


pytestmark = pytest.mark.django_db


@pytest.fixture
def repository(project):
    return Repository.objects.create(
        project=project,
        name="sample-repo",
        path=r"C:\repos\sample-repo",
    )


def status_payload(path, **overrides):
    payload = {
        "path": path,
        "branch": "main",
        "upstream": "origin/main",
        "ahead": 2,
        "behind": 0,
        "changed_files": 3,
        "untracked_files": 1,
        "last_commit_at": "2026-09-24T09:00:00+09:00",
        "last_commit_sha": "a" * 40,
        "last_commit_subject": "日本語のコミットメッセージ",
        "status_error": "",
    }
    payload.update(overrides)
    return payload


def test_pipeline_can_list_and_report_repository_status(pipeline_client, repository):
    listed = pipeline_client.get("/api/v1/repositories/")
    assert listed.status_code == 200
    assert [item["path"] for item in listed.json()] == [repository.path]

    response = pipeline_client.post(
        "/api/v1/repositories/status/",
        {
            "repositories": [
                status_payload(repository.path),
                status_payload(r"C:\repos\unknown"),
            ]
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.json() == {"updated": 1, "unknown": [r"C:\repos\unknown"]}
    repository.refresh_from_db()
    assert repository.branch == "main"
    assert repository.ahead == 2
    assert repository.changed_files == 3
    assert repository.last_commit_subject == "日本語のコミットメッセージ"
    assert repository.collected_at is not None


def test_error_report_clears_previous_values(pipeline_client, repository):
    pipeline_client.post(
        "/api/v1/repositories/status/",
        {"repositories": [status_payload(repository.path)]},
        format="json",
    )

    pipeline_client.post(
        "/api/v1/repositories/status/",
        {"repositories": [{"path": repository.path, "status_error": "フォルダが見つかりません"}]},
        format="json",
    )

    repository.refresh_from_db()
    assert repository.status_error == "フォルダが見つかりません"
    assert repository.branch == ""
    assert repository.ahead is None
    assert repository.last_commit_at is None


def test_long_commit_subject_is_truncated(pipeline_client, repository):
    pipeline_client.post(
        "/api/v1/repositories/status/",
        {"repositories": [status_payload(repository.path, last_commit_subject="あ" * 800)]},
        format="json",
    )

    repository.refresh_from_db()
    assert len(repository.last_commit_subject) == 500


@pytest.mark.parametrize(
    "body",
    [
        {"repositories": []},
        {"repositories": [{"branch": "main"}]},
        {"repositories": [{"path": "x", "ahead": -1}]},
    ],
)
def test_invalid_status_report_is_rejected(pipeline_client, body):
    response = pipeline_client.post("/api/v1/repositories/status/", body, format="json")

    assert response.status_code == 400


def test_only_pipeline_can_report_status(web_client, mcp_client, discord_client, repository):
    body = {"repositories": [status_payload(repository.path)]}
    for client in (web_client, mcp_client, discord_client):
        assert (
            client.post("/api/v1/repositories/status/", body, format="json").status_code
            == 403
        )
    assert web_client.get("/api/v1/repositories/").status_code == 200
    assert mcp_client.get("/api/v1/repositories/").status_code == 403


def test_inactive_repositories_are_hidden(web_client, repository, project):
    Repository.objects.create(project=project, name="old", path=r"C:\repos\old", is_active=False)

    listed = web_client.get("/api/v1/repositories/").json()
    summary = web_client.get("/api/v1/dashboard/summary/").json()

    assert [item["name"] for item in listed] == ["sample-repo"]
    assert [item["name"] for item in summary["repositories"]] == ["sample-repo"]
    assert summary["repositories"][0]["project"] == project.slug


def test_get_project_includes_linked_repositories(repository, project):
    Repository.objects.create(name="unlinked", path=r"C:\repos\unlinked")

    result = domain.get_project(slug=project.slug)

    assert [item["name"] for item in result["repositories"]] == ["sample-repo"]


def test_seed_registers_repositories(tmp_path):
    config = tmp_path / "projects.toml"
    config.write_text(
        """
[[project]]
slug = "app"
code = "APP"
name = "App"
root_path = 'C:\\docs\\app'

[[repository]]
path = 'C:\\repos\\app-code'
project = "app"

[[repository]]
path = 'C:\\repos\\scratch'
name = "Scratch"
""",
        encoding="utf-8",
    )

    call_command("seed_initial_data", config=str(config))
    call_command("seed_initial_data", config=str(config))

    repositories = {repo.path: repo for repo in Repository.objects.all()}
    assert set(repositories) == {r"C:\repos\app-code", r"C:\repos\scratch"}
    assert repositories[r"C:\repos\app-code"].name == "app-code"
    assert repositories[r"C:\repos\app-code"].project.slug == "app"
    assert repositories[r"C:\repos\scratch"].name == "Scratch"
    assert repositories[r"C:\repos\scratch"].project is None


def test_seed_rejects_repository_with_unknown_project(tmp_path):
    config = tmp_path / "projects.toml"
    config.write_text(
        """
[[project]]
slug = "app"
code = "APP"
name = "App"

[[repository]]
path = 'C:\\repos\\x'
project = "missing"
""",
        encoding="utf-8",
    )

    with pytest.raises(CommandError):
        call_command("seed_initial_data", config=str(config))
