import pytest
from rest_framework.test import APIClient

from apps.automations.models import Automation
from apps.core.models import ApiKey
from apps.projects.models import Project
from apps.services.api_keys import create_api_key


@pytest.fixture
def project(db):
    return Project.objects.create(
        slug="sample-project",
        code="SAMPLE",
        name="Sample Project",
        root_path=r"E:\home\sample",
        summary="Test project",
        color="#336699",
    )


@pytest.fixture
def automation(project):
    return Automation.objects.create(
        key="sample-automation",
        project=project,
        scheduled_task_name="Sample Scheduled Task",
        schedule_human="毎日 07:00",
        state=Automation.State.ACTIVE,
    )


def _scoped_client(scope):
    _, raw_key = create_api_key(f"{scope}-test", scope)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Api-Key {raw_key}")
    return client


@pytest.fixture
def web_client(db):
    return _scoped_client(ApiKey.Scope.WEB)


@pytest.fixture
def pipeline_client(db):
    return _scoped_client(ApiKey.Scope.PIPELINE)


@pytest.fixture
def mcp_client(db):
    return _scoped_client(ApiKey.Scope.MCP)


@pytest.fixture
def discord_client(db):
    return _scoped_client(ApiKey.Scope.DISCORD)
