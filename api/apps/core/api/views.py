from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.serializers import (
    ApiKeyCreateSerializer,
    ApiKeyCreatedSerializer,
    ApiKeySerializer,
    ApiKeyUpdateSerializer,
    AppSettingsSerializer,
    AppSettingsUpdateSerializer,
    AutomationSerializer,
    BackupSettingsSerializer,
    DiscordBotConfigSerializer,
    DiscordStatusReportSerializer,
    DiscordStatusSerializer,
    RepositoryListQuerySerializer,
    RepositoryWriteSerializer,
    DashboardSummarySerializer,
    ProjectCreateSerializer,
    ProjectSerializer,
    ProjectUpdateSerializer,
    RunFinishSerializer,
    RunSerializer,
    RunStartSerializer,
    SessionSerializer,
    TaskCreateSerializer,
    RepositorySerializer,
    RepositoryStatusReportSerializer,
    RepositoryStatusResultSerializer,
    RunListQuerySerializer,
    TaskEventFeedQuerySerializer,
    TaskEventFeedSerializer,
    TaskEventSerializer,
    TaskListQuerySerializer,
    TaskSerializer,
    TaskUpdateSerializer,
)
from apps.core.models import ApiKey
from apps.core.permissions import HasApiKeyScope
from apps.services import api_keys
from apps.services import app_settings
from apps.services import domain
from apps.services import repositories
from apps.services import selectors


class ScopedAPIView(APIView):
    permission_classes = [HasApiKeyScope]
    api_key_scopes = {ApiKey.Scope.WEB}


class PaginatedAPIView(ScopedAPIView):
    pagination_class = PageNumberPagination

    def paginated_response(self, request, queryset, serializer_class):
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = serializer_class(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class DashboardSummaryView(ScopedAPIView):
    api_key_scopes = {ApiKey.Scope.WEB, ApiKey.Scope.DISCORD}

    @extend_schema(responses={200: DashboardSummarySerializer})
    def get(self, request):
        return Response(domain.get_dashboard_summary())


class ProjectListCreateView(PaginatedAPIView):
    @extend_schema(responses={200: ProjectSerializer(many=True)})
    def get(self, request):
        return self.paginated_response(
            request,
            selectors.project_queryset(),
            ProjectSerializer,
        )

    @extend_schema(request=ProjectCreateSerializer, responses={201: ProjectSerializer})
    def post(self, request):
        serializer = ProjectCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = domain.create_project(**serializer.validated_data)
        result = selectors.get_project_by_slug(project.slug)
        return Response(ProjectSerializer(result).data, status=status.HTTP_201_CREATED)


class ProjectDetailView(ScopedAPIView):
    @extend_schema(responses={200: ProjectSerializer})
    def get(self, request, slug):
        project = selectors.get_project_by_slug(slug)
        return Response(ProjectSerializer(project).data)

    @extend_schema(request=ProjectUpdateSerializer, responses={200: ProjectSerializer})
    def patch(self, request, slug):
        serializer = ProjectUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        project = domain.update_project(slug, **serializer.validated_data)
        result = selectors.get_project_by_slug(project.slug)
        return Response(ProjectSerializer(result).data)


class TaskListCreateView(PaginatedAPIView):
    @extend_schema(
        parameters=[TaskListQuerySerializer],
        responses={200: TaskSerializer(many=True)},
    )
    def get(self, request):
        query = TaskListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        ordering = [values["ordering"]] if values.get("ordering") else None
        queryset = selectors.task_queryset(
            project=values.get("project"),
            statuses=values.get("status"),
            query=values.get("q"),
            ordering=ordering,
        )
        return self.paginated_response(request, queryset, TaskSerializer)

    @extend_schema(request=TaskCreateSerializer, responses={201: TaskSerializer})
    def post(self, request):
        serializer = TaskCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created = domain.create_task(
            **serializer.validated_data,
            created_by="human",
        )
        task = selectors.get_task_by_key(created["key"])
        return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED)


class TaskDetailView(ScopedAPIView):
    @extend_schema(responses={200: TaskSerializer})
    def get(self, request, key):
        task = selectors.get_task_by_key(key)
        return Response(TaskSerializer(task).data)

    @extend_schema(request=TaskUpdateSerializer, responses={200: TaskSerializer})
    def patch(self, request, key):
        serializer = TaskUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = domain.update_task(
            key,
            actor="human",
            **serializer.validated_data,
        )
        task = selectors.get_task_by_key(updated["key"])
        return Response(TaskSerializer(task).data)

    @extend_schema(responses={204: None})
    def delete(self, request, key):
        domain.delete_task(key)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TaskEventListView(PaginatedAPIView):
    @extend_schema(responses={200: TaskEventSerializer(many=True)})
    def get(self, request, key):
        return self.paginated_response(
            request,
            selectors.task_event_queryset(key),
            TaskEventSerializer,
        )


class TaskEventFeedView(ScopedAPIView):
    api_key_scopes = {ApiKey.Scope.WEB, ApiKey.Scope.DISCORD}

    @extend_schema(
        parameters=[TaskEventFeedQuerySerializer],
        responses={200: TaskEventFeedSerializer},
    )
    def get(self, request):
        query = TaskEventFeedQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        events, next_after = selectors.task_event_feed(
            after=values.get("after"),
            limit=values["limit"],
        )
        return Response(
            TaskEventFeedSerializer({"results": events, "next_after": next_after}).data
        )


class RepositoryListView(ScopedAPIView):
    """登録済みで有効なリポジトリの一覧（ページ分けしない）と、画面からの追加。

    ホストの収集スクリプト（pipeline）が対象を知るためにも使う。
    """

    api_key_scopes_by_method = {
        "GET": {ApiKey.Scope.WEB, ApiKey.Scope.PIPELINE},
        "POST": {ApiKey.Scope.WEB},
    }

    @extend_schema(
        parameters=[RepositoryListQuerySerializer],
        responses={200: RepositorySerializer(many=True)},
    )
    def get(self, request):
        query = RepositoryListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        queryset = selectors.repository_queryset(
            include_inactive=query.validated_data["include_inactive"]
        )
        return Response(RepositorySerializer(queryset, many=True).data)

    @extend_schema(request=RepositoryWriteSerializer, responses={201: RepositorySerializer})
    def post(self, request):
        serializer = RepositoryWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        repository = repositories.create_repository(**serializer.validated_data)
        return Response(RepositorySerializer(repository).data, status=status.HTTP_201_CREATED)


class RepositoryDetailView(ScopedAPIView):
    @extend_schema(request=RepositoryWriteSerializer, responses={200: RepositorySerializer})
    def patch(self, request, repository_id):
        serializer = RepositoryWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        repository = repositories.update_repository(repository_id, **serializer.validated_data)
        return Response(RepositorySerializer(repository).data)

    @extend_schema(responses={204: None})
    def delete(self, request, repository_id):
        repositories.delete_repository(repository_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RepositoryStatusView(ScopedAPIView):
    api_key_scopes = {ApiKey.Scope.PIPELINE}

    @extend_schema(
        request=RepositoryStatusReportSerializer,
        responses={200: RepositoryStatusResultSerializer},
    )
    def post(self, request):
        serializer = RepositoryStatusReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = domain.record_repository_statuses(serializer.validated_data["repositories"])
        return Response(RepositoryStatusResultSerializer(result).data)


class SessionListView(PaginatedAPIView):
    @extend_schema(responses={200: SessionSerializer(many=True)})
    def get(self, request):
        return self.paginated_response(
            request,
            selectors.session_queryset(),
            SessionSerializer,
        )


class AutomationListView(PaginatedAPIView):
    @extend_schema(responses={200: AutomationSerializer(many=True)})
    def get(self, request):
        return self.paginated_response(
            request,
            selectors.automation_queryset(),
            AutomationSerializer,
        )


class RunListCreateView(PaginatedAPIView):
    api_key_scopes_by_method = {
        "GET": {ApiKey.Scope.WEB, ApiKey.Scope.DISCORD},
        "POST": {ApiKey.Scope.PIPELINE},
    }

    @extend_schema(
        parameters=[RunListQuerySerializer],
        responses={200: RunSerializer(many=True)},
    )
    def get(self, request):
        query = RunListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        return self.paginated_response(
            request,
            selectors.run_queryset(
                status=values.get("status"),
                ended_after=values.get("ended_after"),
            ),
            RunSerializer,
        )

    @extend_schema(request=RunStartSerializer, responses={201: RunSerializer})
    def post(self, request):
        serializer = RunStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        values.pop("status", None)
        started = domain.start_run(**values)
        run = selectors.get_run_by_key(started["run_key"])
        return Response(RunSerializer(run).data, status=status.HTTP_201_CREATED)


class RunDetailView(ScopedAPIView):
    api_key_scopes_by_method = {"PATCH": {ApiKey.Scope.PIPELINE}}

    @extend_schema(request=RunFinishSerializer, responses={200: RunSerializer})
    def patch(self, request, run_key):
        serializer = RunFinishSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        finished = domain.finish_run(run_key, **serializer.validated_data)
        run = selectors.get_run_by_key(finished["run_key"])
        return Response(RunSerializer(run).data)


class AppSettingsView(ScopedAPIView):
    """設定画面の値の取得と保存（web スコープのみ）。トークンは応答に含めない。"""

    @extend_schema(responses={200: AppSettingsSerializer})
    def get(self, request):
        return Response(AppSettingsSerializer(app_settings.settings_for_web()).data)

    @extend_schema(request=AppSettingsUpdateSerializer, responses={200: AppSettingsSerializer})
    def patch(self, request):
        serializer = AppSettingsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        app_settings.update_groups(serializer.validated_data)
        return Response(AppSettingsSerializer(app_settings.settings_for_web()).data)


class BackupSettingsView(ScopedAPIView):
    """ホストの backup.ps1 が保持世代数を読むためのもの。"""

    api_key_scopes = {ApiKey.Scope.WEB, ApiKey.Scope.PIPELINE}

    @extend_schema(responses={200: BackupSettingsSerializer})
    def get(self, request):
        return Response({"keep": app_settings.get_value(app_settings.BACKUP_KEEP)})


class DiscordTestRequestView(ScopedAPIView):
    """テスト送信を bot に依頼する。bot は次の設定確認（15秒ごと）で送信し、結果を報告する。"""

    @extend_schema(request=None, responses={202: DiscordStatusSerializer})
    def post(self, request):
        return Response(app_settings.request_discord_test(), status=status.HTTP_202_ACCEPTED)


class DiscordBotConfigView(ScopedAPIView):
    """bot が起動時と定期的に読む設定。トークンを含むので discord スコープだけに返す。"""

    api_key_scopes = {ApiKey.Scope.DISCORD}

    @extend_schema(responses={200: DiscordBotConfigSerializer})
    def get(self, request):
        return Response(DiscordBotConfigSerializer(app_settings.discord_config_for_bot()).data)


class DiscordBotStatusView(ScopedAPIView):
    """bot が接続状態とテスト送信の結果を報告する（設定画面に表示する）。"""

    api_key_scopes = {ApiKey.Scope.DISCORD}

    @extend_schema(request=DiscordStatusReportSerializer, responses={200: DiscordStatusSerializer})
    def post(self, request):
        serializer = DiscordStatusReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(app_settings.record_discord_status(**serializer.validated_data))


def _api_key_data(api_key, request):
    return {
        "id": api_key.pk,
        "name": api_key.name,
        "prefix": api_key.prefix,
        "scope": api_key.scope,
        "is_active": api_key.is_active,
        "created_at": api_key.created_at,
        "last_used_at": api_key.last_used_at,
        "is_current": api_key.pk == getattr(request.auth, "pk", None),
    }


class ApiKeyListCreateView(ScopedAPIView):
    @extend_schema(responses={200: ApiKeySerializer(many=True)})
    def get(self, request):
        keys = [_api_key_data(api_key, request) for api_key in api_keys.list_api_keys()]
        return Response(ApiKeySerializer(keys, many=True).data)

    @extend_schema(request=ApiKeyCreateSerializer, responses={201: ApiKeyCreatedSerializer})
    def post(self, request):
        serializer = ApiKeyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        api_key, raw_key = api_keys.create_api_key(
            name=serializer.validated_data["name"].strip(),
            scope=serializer.validated_data["scope"],
        )
        data = {**_api_key_data(api_key, request), "key": raw_key}
        return Response(ApiKeyCreatedSerializer(data).data, status=status.HTTP_201_CREATED)


class ApiKeyDetailView(ScopedAPIView):
    @extend_schema(request=ApiKeyUpdateSerializer, responses={200: ApiKeySerializer})
    def patch(self, request, key_id):
        serializer = ApiKeyUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        api_key = api_keys.update_api_key(
            key_id,
            current_key_id=getattr(request.auth, "pk", None),
            **serializer.validated_data,
        )
        return Response(ApiKeySerializer(_api_key_data(api_key, request)).data)
