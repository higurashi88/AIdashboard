from django.core.validators import RegexValidator
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.automations.models import Automation, Run
from apps.core.models import ApiKey
from apps.projects.models import Project, Repository
from apps.sessions.models import Session
from apps.tasks.models import Task, TaskEvent


class ProjectSerializer(serializers.ModelSerializer):
    open_tasks = serializers.IntegerField(read_only=True, default=0)
    awaiting_user = serializers.IntegerField(
        source="awaiting_user_count", read_only=True, default=0
    )
    in_progress = serializers.IntegerField(
        source="in_progress_count", read_only=True, default=0
    )

    class Meta:
        model = Project
        fields = (
            "id",
            "slug",
            "code",
            "name",
            "root_path",
            "summary",
            "is_active",
            "archived_at",
            "sort_order",
            "is_pinned",
            "color",
            "extra",
            "next_task_number",
            "open_tasks",
            "awaiting_user",
            "in_progress",
        )


class ProjectCreateSerializer(serializers.Serializer):
    slug = serializers.SlugField(max_length=64, required=False, allow_blank=True)
    code = serializers.CharField(
        max_length=12,
        required=False,
        allow_blank=True,
        validators=[
            RegexValidator(
                r"^[A-Za-z0-9]*$",
                "Use ASCII letters and numbers only.",
            )
        ],
    )
    name = serializers.CharField(max_length=120)
    root_path = serializers.CharField()
    summary = serializers.CharField(required=False, allow_blank=True, default="")
    is_active = serializers.BooleanField(required=False, default=True)
    archived_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    sort_order = serializers.IntegerField(
        required=False,
        min_value=-32768,
        max_value=32767,
        default=0,
    )
    is_pinned = serializers.BooleanField(required=False, default=False)
    color = serializers.RegexField(
        r"^#[0-9A-Fa-f]{6}$",
        required=False,
        default="#64748B",
    )
    extra = serializers.JSONField(required=False, default=dict)


class ProjectUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120, required=False)
    root_path = serializers.CharField(required=False)
    summary = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    archived_at = serializers.DateTimeField(required=False, allow_null=True)
    sort_order = serializers.IntegerField(
        required=False,
        min_value=-32768,
        max_value=32767,
    )
    is_pinned = serializers.BooleanField(required=False)
    color = serializers.RegexField(r"^#[0-9A-Fa-f]{6}$", required=False)
    extra = serializers.JSONField(required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("At least one field is required.")
        return attrs


class TaskSerializer(serializers.ModelSerializer):
    project = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    parent = serializers.SlugRelatedField(read_only=True, slug_field="key")

    class Meta:
        model = Task
        fields = (
            "id",
            "project",
            "number",
            "key",
            "title",
            "detail",
            "status",
            "priority",
            "actor_type",
            "parent",
            "created_by",
            "origin_session",
            "due_at",
            "started_at",
            "completed_at",
            "tags",
            "created_at",
            "updated_at",
        )


class TaskCreateSerializer(serializers.Serializer):
    project = serializers.CharField(max_length=64)
    title = serializers.CharField(max_length=255)
    detail = serializers.CharField(required=False, allow_blank=True, default="")
    # 読み取り系（TaskSerializer）はモデル由来の `.choices`（値＋ラベル）を使う。
    # ここで `.values`（値のみ）を使うと drf-spectacular が別の選択肢集合と見なし、
    # 同じ値なのに TaskStatusEnum とは別の enum（Status89cEnum 等）が生成される。
    # ChoiceField は (値, ラベル) 形式でも値のみでも同じ入力を受け付けるため、
    # `.choices` に揃えてもバリデーション挙動は変わらない。
    priority = serializers.ChoiceField(
        choices=Task.Priority.choices,
        required=False,
        default=Task.Priority.NONE,
    )
    status = serializers.ChoiceField(
        choices=Task.Status.choices,
        required=False,
        default=Task.Status.TODO,
    )
    actor_type = serializers.ChoiceField(
        choices=Task.ActorType.choices,
        required=False,
        default=Task.ActorType.AGENT,
    )
    parent = serializers.CharField(max_length=24, required=False, allow_null=True)


class TaskUpdateSerializer(serializers.Serializer):
    # TaskCreateSerializer と同じ理由で `.choices` を使う（enum の重複生成を防ぐため）
    status = serializers.ChoiceField(choices=Task.Status.choices, required=False)
    title = serializers.CharField(max_length=255, required=False)
    detail = serializers.CharField(required=False, allow_blank=True)
    priority = serializers.ChoiceField(choices=Task.Priority.choices, required=False)
    actor_type = serializers.ChoiceField(choices=Task.ActorType.choices, required=False)
    note = serializers.CharField(required=False, allow_blank=True)
    due_at = serializers.DateTimeField(required=False, allow_null=True)
    tags = serializers.ListField(
        child=serializers.CharField(max_length=64),
        required=False,
        allow_empty=True,
    )
    parent = serializers.CharField(
        max_length=24,
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("At least one field is required.")
        return attrs


class TaskListQuerySerializer(serializers.Serializer):
    project = serializers.CharField(required=False, allow_blank=True)
    status = serializers.CharField(required=False, allow_blank=True)
    q = serializers.CharField(required=False, allow_blank=True)
    ordering = serializers.ChoiceField(
        choices=(
            "priority",
            "-priority",
            "updated_at",
            "-updated_at",
            "created_at",
            "-created_at",
        ),
        required=False,
    )
    page = serializers.IntegerField(required=False, min_value=1)

    def validate_status(self, value):
        statuses = [item.strip() for item in value.split(",") if item.strip()]
        invalid = sorted(set(statuses) - set(Task.Status.values))
        if invalid:
            raise serializers.ValidationError(
                f"Unsupported status: {', '.join(invalid)}"
            )
        return statuses


class DashboardLastRunSerializer(serializers.Serializer):
    status = serializers.CharField()
    started_at = serializers.DateTimeField()
    duration_sec = serializers.IntegerField(allow_null=True)


class DashboardAutomationSerializer(serializers.Serializer):
    key = serializers.CharField()
    name = serializers.CharField()
    schedule = serializers.CharField()
    state = serializers.CharField()
    last_run = DashboardLastRunSerializer(allow_null=True)


class DashboardProjectSerializer(serializers.Serializer):
    slug = serializers.CharField()
    code = serializers.CharField()
    name = serializers.CharField()
    color = serializers.CharField()
    is_active = serializers.BooleanField()
    is_pinned = serializers.BooleanField()
    open_tasks = serializers.IntegerField()
    awaiting_user = serializers.IntegerField()
    in_progress = serializers.IntegerField()
    last_activity_at = serializers.DateTimeField(allow_null=True)
    is_stale = serializers.BooleanField()


class RecentActivitySerializer(serializers.Serializer):
    at = serializers.DateTimeField()
    actor = serializers.CharField()
    body = serializers.CharField()
    task_key = serializers.CharField(required=False)
    project = serializers.CharField()


class RepositorySerializer(serializers.ModelSerializer):
    project = serializers.SlugRelatedField(read_only=True, slug_field="slug", allow_null=True)

    class Meta:
        model = Repository
        fields = (
            "id",
            "is_active",
            "sort_order",
            "name",
            "path",
            "project",
            "branch",
            "upstream",
            "ahead",
            "behind",
            "changed_files",
            "untracked_files",
            "last_commit_at",
            "last_commit_subject",
            "status_error",
            "collected_at",
        )


class RepositoryStatusItemSerializer(serializers.Serializer):
    path = serializers.CharField(max_length=500)
    branch = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    upstream = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    ahead = serializers.IntegerField(required=False, min_value=0, allow_null=True)
    behind = serializers.IntegerField(required=False, min_value=0, allow_null=True)
    changed_files = serializers.IntegerField(required=False, min_value=0, allow_null=True)
    untracked_files = serializers.IntegerField(required=False, min_value=0, allow_null=True)
    last_commit_at = serializers.DateTimeField(required=False, allow_null=True)
    last_commit_sha = serializers.CharField(max_length=64, required=False, allow_blank=True, allow_null=True)
    last_commit_subject = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    status_error = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_last_commit_subject(self, value):
        return (value or "")[:500]


class RepositoryStatusReportSerializer(serializers.Serializer):
    repositories = RepositoryStatusItemSerializer(many=True, allow_empty=False, max_length=200)


class RepositoryStatusResultSerializer(serializers.Serializer):
    updated = serializers.IntegerField()
    unknown = serializers.ListField(child=serializers.CharField())


class DashboardSummarySerializer(serializers.Serializer):
    awaiting_user = TaskSerializer(many=True)
    human_tasks = TaskSerializer(many=True)
    in_progress = TaskSerializer(many=True)
    automations = DashboardAutomationSerializer(many=True)
    projects = DashboardProjectSerializer(many=True)
    recent_activity = RecentActivitySerializer(many=True)
    repositories = RepositorySerializer(many=True)


class TaskEventSerializer(serializers.ModelSerializer):
    task_key = serializers.CharField(source="task.key", read_only=True)

    class Meta:
        model = TaskEvent
        fields = (
            "id",
            "task_key",
            "session",
            "event_type",
            "actor",
            "body",
            "occurred_at",
            "payload",
        )


class TaskEventFeedQuerySerializer(serializers.Serializer):
    after = serializers.IntegerField(
        required=False,
        min_value=0,
        help_text="このIDより後のイベントを返す。省略時は結果を返さず、現在の最新IDだけを返す。",
    )
    limit = serializers.IntegerField(required=False, min_value=1, max_value=200, default=100)


class TaskEventFeedItemSerializer(serializers.ModelSerializer):
    task_key = serializers.CharField(source="task.key", read_only=True)
    task_title = serializers.CharField(source="task.title", read_only=True)
    task_status = serializers.CharField(source="task.status", read_only=True)
    project = serializers.CharField(source="task.project.slug", read_only=True)
    project_name = serializers.CharField(source="task.project.name", read_only=True)

    class Meta:
        model = TaskEvent
        fields = (
            "id",
            "task_key",
            "task_title",
            "task_status",
            "project",
            "project_name",
            "event_type",
            "actor",
            "body",
            "occurred_at",
            "payload",
        )


class TaskEventFeedSerializer(serializers.Serializer):
    results = TaskEventFeedItemSerializer(many=True)
    next_after = serializers.IntegerField()


class SessionSerializer(serializers.ModelSerializer):
    project = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    run = serializers.SlugRelatedField(read_only=True, slug_field="run_key")
    tasks = serializers.SlugRelatedField(many=True, read_only=True, slug_field="key")

    class Meta:
        model = Session
        fields = (
            "id",
            "external_id",
            "agent",
            "project",
            "run",
            "tasks",
            "started_at",
            "ended_at",
            "summary",
        )


class AutomationLastRunSerializer(serializers.Serializer):
    run_key = serializers.CharField()
    status = serializers.CharField()
    started_at = serializers.DateTimeField()
    ended_at = serializers.DateTimeField(allow_null=True)
    duration_sec = serializers.IntegerField(allow_null=True)


class AutomationSerializer(serializers.ModelSerializer):
    project = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    name = serializers.SerializerMethodField()
    schedule = serializers.CharField(source="schedule_human", read_only=True)
    last_run = serializers.SerializerMethodField()

    class Meta:
        model = Automation
        fields = (
            "id",
            "key",
            "project",
            "name",
            "scheduled_task_name",
            "schedule",
            "script_path",
            "state",
            "last_run",
        )

    @extend_schema_field(OpenApiTypes.STR)
    def get_name(self, obj) -> str:
        return obj.name or obj.scheduled_task_name or obj.key

    @extend_schema_field(AutomationLastRunSerializer)
    def get_last_run(self, obj) -> dict | None:
        if obj.last_run_key is None:
            return None
        return {
            "run_key": obj.last_run_key,
            "status": obj.last_run_status,
            "started_at": obj.last_run_started_at,
            "ended_at": obj.last_run_ended_at,
            "duration_sec": obj.last_run_duration_sec,
        }


class RunSerializer(serializers.ModelSerializer):
    automation_key = serializers.CharField(source="automation.key", read_only=True)
    automation_name = serializers.SerializerMethodField()
    project = serializers.CharField(source="automation.project.slug", read_only=True)

    class Meta:
        model = Run
        fields = (
            "id",
            "automation_key",
            "automation_name",
            "project",
            "run_key",
            "status",
            "trigger",
            "started_at",
            "ended_at",
            "duration_sec",
            "exit_code",
            "log_path",
            "summary",
            "metrics",
        )

    @extend_schema_field(OpenApiTypes.STR)
    def get_automation_name(self, obj) -> str:
        automation = obj.automation
        return automation.name or automation.scheduled_task_name or automation.key


class RunListQuerySerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Run.Status.choices, required=False)
    ended_after = serializers.DateTimeField(
        required=False,
        help_text="この時刻より後に終了した実行だけを返す。",
    )


class RunStartSerializer(serializers.Serializer):
    automation_key = serializers.CharField(max_length=64)
    run_key = serializers.CharField(max_length=128)
    status = serializers.ChoiceField(
        choices=(Run.Status.RUNNING,),
        required=False,
        default=Run.Status.RUNNING,
    )
    trigger = serializers.CharField(max_length=32)
    started_at = serializers.DateTimeField()
    log_path = serializers.CharField(required=False, allow_blank=True, default="")


class RunFinishSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=(Run.Status.SUCCEEDED, Run.Status.FAILED)
    )
    exit_code = serializers.IntegerField(required=False, allow_null=True)
    ended_at = serializers.DateTimeField(required=False, allow_null=True)
    summary = serializers.CharField(required=False, allow_blank=True)


# --- 設定画面 ---------------------------------------------------------------

DIGITS_OR_BLANK = RegexValidator(
    r"^\d{0,20}$",
    "数字のIDで入力してください（Discord の開発者モードでコピーできます）",
)
HH_MM = RegexValidator(r"^([01]\d|2[0-3]):[0-5]\d$", "HH:MM 形式（例 08:00）で入力してください")


class DiscordSettingsSerializer(serializers.Serializer):
    bot_token_set = serializers.BooleanField()
    bot_token_hint = serializers.CharField(help_text="トークンの末尾4文字。未設定なら空。")
    channel_id = serializers.CharField(allow_blank=True)
    mention_user_id = serializers.CharField(allow_blank=True)
    daily_summary_time = serializers.CharField()
    poll_interval_sec = serializers.IntegerField()


class DiscordSettingsUpdateSerializer(serializers.Serializer):
    bot_token = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=200,
        help_text="空文字で削除。省略すれば変更しない。応答には含めない。",
    )
    channel_id = serializers.CharField(
        required=False, allow_blank=True, validators=[DIGITS_OR_BLANK]
    )
    mention_user_id = serializers.CharField(
        required=False, allow_blank=True, validators=[DIGITS_OR_BLANK]
    )
    daily_summary_time = serializers.CharField(required=False, validators=[HH_MM])
    poll_interval_sec = serializers.IntegerField(required=False, min_value=10, max_value=3600)

    def validate_bot_token(self, value):
        if any(character.isspace() for character in value):
            raise serializers.ValidationError("トークンに空白や改行を含めないでください")
        return value


class NotificationSettingsSerializer(serializers.Serializer):
    awaiting_user = serializers.BooleanField()
    failed_runs = serializers.BooleanField()
    daily_summary = serializers.BooleanField()
    projects = serializers.ListField(
        child=serializers.CharField(),
        help_text="通知するプロジェクトの slug。空なら全プロジェクト。",
    )


class NotificationSettingsUpdateSerializer(serializers.Serializer):
    awaiting_user = serializers.BooleanField(required=False)
    failed_runs = serializers.BooleanField(required=False)
    daily_summary = serializers.BooleanField(required=False)
    projects = serializers.ListField(
        child=serializers.SlugField(max_length=64),
        required=False,
        max_length=200,
    )

    def validate_projects(self, value):
        slugs = list(dict.fromkeys(value))
        known = set(Project.objects.filter(slug__in=slugs).values_list("slug", flat=True))
        unknown = [slug for slug in slugs if slug not in known]
        if unknown:
            raise serializers.ValidationError(
                f"登録されていないプロジェクトです: {', '.join(unknown)}"
            )
        return slugs


class BackupSettingsSerializer(serializers.Serializer):
    keep = serializers.IntegerField()


class BackupSettingsUpdateSerializer(serializers.Serializer):
    keep = serializers.IntegerField(required=False, min_value=1, max_value=365)


class DiscordStatusSerializer(serializers.Serializer):
    state = serializers.CharField(
        help_text=(
            "unknown / waiting_config / connecting / connected / "
            "login_failed / channel_error / error"
        ),
    )
    detail = serializers.CharField(allow_blank=True)
    bot_user = serializers.CharField(allow_blank=True)
    reported_at = serializers.CharField(allow_null=True)
    test_requested_at = serializers.CharField(allow_null=True)
    test_handled_at = serializers.CharField(allow_null=True)
    test_error = serializers.CharField(allow_blank=True)


class AppSettingsSerializer(serializers.Serializer):
    discord = DiscordSettingsSerializer()
    notifications = NotificationSettingsSerializer()
    backup = BackupSettingsSerializer()
    discord_status = DiscordStatusSerializer()
    time_zone = serializers.CharField()
    updated_at = serializers.DateTimeField(allow_null=True)


class AppSettingsUpdateSerializer(serializers.Serializer):
    discord = DiscordSettingsUpdateSerializer(required=False)
    notifications = NotificationSettingsUpdateSerializer(required=False)
    backup = BackupSettingsUpdateSerializer(required=False)

    def validate(self, attrs):
        if not any(attrs.values()):
            raise serializers.ValidationError("変更する項目がありません")
        return attrs


class DiscordBotNotificationSerializer(serializers.Serializer):
    awaiting_user = serializers.BooleanField()
    failed_runs = serializers.BooleanField()
    daily_summary = serializers.BooleanField()
    projects = serializers.ListField(child=serializers.CharField())


class DiscordBotConfigSerializer(serializers.Serializer):
    bot_token = serializers.CharField(allow_blank=True)
    channel_id = serializers.CharField(allow_blank=True)
    mention_user_id = serializers.CharField(allow_blank=True)
    daily_summary_time = serializers.CharField()
    poll_interval_sec = serializers.IntegerField()
    time_zone = serializers.CharField()
    notifications = DiscordBotNotificationSerializer()
    test_requested_at = serializers.CharField(allow_null=True)


class DiscordStatusReportSerializer(serializers.Serializer):
    state = serializers.ChoiceField(
        choices=(
            "waiting_config",
            "connecting",
            "connected",
            "login_failed",
            "channel_error",
            "error",
        )
    )
    detail = serializers.CharField(required=False, allow_blank=True, default="", max_length=1000)
    bot_user = serializers.CharField(required=False, allow_blank=True, default="", max_length=200)
    test_handled_at = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=64
    )
    test_error = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=1000
    )


# --- APIキー ------------------------------------------------------------------

class ApiKeySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    prefix = serializers.CharField()
    scope = serializers.CharField()
    is_active = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    last_used_at = serializers.DateTimeField(allow_null=True)
    is_current = serializers.BooleanField(help_text="この画面自身が使っているキーか")


class ApiKeyCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    scope = serializers.ChoiceField(choices=ApiKey.Scope.choices)


class ApiKeyCreatedSerializer(ApiKeySerializer):
    key = serializers.CharField(help_text="発行したキーの平文。この応答でしか返さない。")


class ApiKeyUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120, required=False)
    is_active = serializers.BooleanField(required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("変更する項目がありません")
        return attrs


# --- リポジトリの管理 ---------------------------------------------------------

WINDOWS_ABSOLUTE_PATH = RegexValidator(
    r"^([A-Za-z]:[\\/]|\\\\)",
    "絶対パス（例 C:\\Users\\you\\src\\my-app）で入力してください",
)


class RepositoryWriteSerializer(serializers.Serializer):
    path = serializers.CharField(max_length=500, validators=[WINDOWS_ABSOLUTE_PATH])
    name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    project = serializers.SlugField(
        max_length=64, required=False, allow_null=True, allow_blank=True
    )
    is_active = serializers.BooleanField(required=False)
    sort_order = serializers.IntegerField(required=False, min_value=-32768, max_value=32767)

    def validate_path(self, value):
        value = value.strip()
        # 末尾の区切り文字は揃える（C:\ のようなドライブ直下は残す）
        stripped = value.rstrip("\\/")
        return value if stripped.endswith(":") else stripped

    def validate_project(self, value):
        if not value:
            return None
        try:
            return Project.objects.get(slug=value)
        except Project.DoesNotExist as exc:
            raise serializers.ValidationError(
                f"登録されていないプロジェクトです: {value}"
            ) from exc


class RepositoryListQuerySerializer(serializers.Serializer):
    include_inactive = serializers.BooleanField(
        required=False,
        default=False,
        help_text="true なら収集対象から外したものも返す（設定画面用）。",
    )
