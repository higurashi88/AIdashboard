from django.urls import path

from apps.core.api.views import (
    ApiKeyDetailView,
    ApiKeyListCreateView,
    AppSettingsView,
    AutomationListView,
    BackupSettingsView,
    DiscordBotConfigView,
    DiscordBotStatusView,
    DiscordTestRequestView,
    DashboardSummaryView,
    ProjectDetailView,
    ProjectListCreateView,
    RepositoryDetailView,
    RepositoryListView,
    RepositoryStatusView,
    RunDetailView,
    RunListCreateView,
    SessionListView,
    TaskDetailView,
    TaskEventFeedView,
    TaskEventListView,
    TaskListCreateView,
)


app_name = "api_v1"

urlpatterns = [
    path("dashboard/summary/", DashboardSummaryView.as_view(), name="dashboard-summary"),
    path("projects/", ProjectListCreateView.as_view(), name="project-list"),
    path("projects/<slug:slug>/", ProjectDetailView.as_view(), name="project-detail"),
    path("tasks/", TaskListCreateView.as_view(), name="task-list"),
    path("tasks/<str:key>/", TaskDetailView.as_view(), name="task-detail"),
    path("tasks/<str:key>/events/", TaskEventListView.as_view(), name="task-events"),
    path("events/", TaskEventFeedView.as_view(), name="event-feed"),
    path("repositories/", RepositoryListView.as_view(), name="repository-list"),
    path(
        "repositories/status/",
        RepositoryStatusView.as_view(),
        name="repository-status",
    ),
    path(
        "repositories/<uuid:repository_id>/",
        RepositoryDetailView.as_view(),
        name="repository-detail",
    ),
    path("settings/", AppSettingsView.as_view(), name="settings"),
    path("settings/backup/", BackupSettingsView.as_view(), name="settings-backup"),
    path(
        "settings/discord/test/",
        DiscordTestRequestView.as_view(),
        name="settings-discord-test",
    ),
    path("discord/config/", DiscordBotConfigView.as_view(), name="discord-config"),
    path("discord/status/", DiscordBotStatusView.as_view(), name="discord-status"),
    path("api-keys/", ApiKeyListCreateView.as_view(), name="api-key-list"),
    path("api-keys/<uuid:key_id>/", ApiKeyDetailView.as_view(), name="api-key-detail"),
    path("sessions/", SessionListView.as_view(), name="session-list"),
    path("automations/", AutomationListView.as_view(), name="automation-list"),
    path("runs/", RunListCreateView.as_view(), name="run-list"),
    path("runs/<str:run_key>/", RunDetailView.as_view(), name="run-detail"),
]
