import os
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [value.strip() for value in os.getenv(name, default).split(",") if value.strip()]


def database_from_url(value):
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL must use the postgres or postgresql scheme")

    config = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(parsed.path.lstrip("/")),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or 5432),
        # ASGI（uvicorn）ではリクエストごとに別スレッドで同期処理が走るため、
        # 永続接続（CONN_MAX_AGE>0）は再利用されずに溜まり続け、max_connections に達する。
        # リクエスト終了時に必ず閉じる。
        "CONN_MAX_AGE": 0,
    }
    query = parse_qs(parsed.query)
    if "sslmode" in query:
        config["OPTIONS"] = {"sslmode": query["sslmode"][-1]}
    return config


DEBUG = env_bool("DJANGO_DEBUG", False)

# SECRET_KEY を未設定のまま本番起動させない。
# 既定値へ黙って落ちると、セッションやトークンの署名が公開値で行われてしまう。
# 開発（DJANGO_DEBUG=True）のときだけ、使い捨ての値を自動生成して起動を許す。
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        import secrets

        SECRET_KEY = secrets.token_urlsafe(50)
    else:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY が設定されていません。"
            ".env に十分に長いランダム文字列を設定してください。"
            "（開発時のみ DJANGO_DEBUG=True で自動生成されます）"
        )
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
# Compose 内部ネットワークのサービス名。discord-bot が http://api:8000 を直接呼ぶ。
# api はホストへ 127.0.0.1 でしか公開していないため、外部からこの名前では届かない。
if "api" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("api")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "apps.core.apps.CoreConfig",
    "apps.projects.apps.ProjectsConfig",
    "apps.automations.apps.AutomationsConfig",
    "apps.sessions.apps.SessionsConfig",
    "apps.tasks.apps.TasksConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": database_from_url(
        os.getenv(
            "DATABASE_URL",
            "postgresql://dashboard:change_me@db:5432/dashboard",
        )
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ja"
TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "Asia/Tokyo")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:8770")
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


def _unique(values):
    return list(dict.fromkeys(value for value in values if value))


def _mcp_default_origins(origins):
    result = []
    for origin in origins:
        parsed = urlparse(origin)
        if not parsed.scheme or not parsed.hostname:
            continue
        hosts = [parsed.hostname]
        if parsed.hostname == "localhost":
            hosts.append("127.0.0.1")
        elif parsed.hostname == "127.0.0.1":
            hosts.append("localhost")
        for host in hosts:
            netloc = f"{host}:{parsed.port}" if parsed.port else host
            result.append(f"{parsed.scheme}://{netloc}")
    return _unique(result)


def _mcp_default_hosts(origins):
    result = ["127.0.0.1", "localhost", "api", "api:8000"]
    for origin in origins:
        parsed = urlparse(origin)
        if not parsed.hostname:
            continue
        hosts = [parsed.hostname]
        if parsed.hostname == "localhost":
            hosts.append("127.0.0.1")
        elif parsed.hostname == "127.0.0.1":
            hosts.append("localhost")
        for host in hosts:
            result.append(host)
            if parsed.port:
                result.append(f"{host}:{parsed.port}")
    return _unique(result)


_dashboard_origins = _unique(
    [os.getenv("DASHBOARD_URL", ""), *CORS_ALLOWED_ORIGINS]
)
_default_mcp_origins = _mcp_default_origins(_dashboard_origins)
_default_mcp_hosts = _mcp_default_hosts(_default_mcp_origins)
MCP_ALLOWED_HOSTS = env_list("MCP_ALLOWED_HOSTS", ",".join(_default_mcp_hosts))
MCP_ALLOWED_ORIGINS = env_list(
    "MCP_ALLOWED_ORIGINS",
    ",".join(_default_mcp_origins),
)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.core.authentication.ApiKeyAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    # APIキーの総当たり対策。既定値はローカル運用に十分な余裕があり、
    # 正規の利用（UIのポーリング30秒、パイプライン数回/日）では当たらない。
    # 外部からアクセスできる場所へ置く場合は必ず見直すこと。
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        # 認証されなかったリクエスト（キーが無い・通らなかったもの）
        "anon": os.getenv("THROTTLE_ANON", "30/min"),
        # 認証済みのAPIキーごと
        "user": os.getenv("THROTTLE_USER", "600/min"),
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "AIdashboard API",
    "VERSION": "1.0.0",
    # リクエストとレスポンスでコンポーネントを分ける。
    # 既定値を持つ項目は「送信時は省略可・応答では必ず入る」という非対称な性質があり、
    # 1つのコンポーネントに同居させると生成クライアントの型が破綻する
    # （送信時に detail/priority/status まで必須になる、逆に応答で optional になる等）。
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "AutomationStateEnum": "apps.core.schema_enums.AutomationStateChoices",
        "RunStatusEnum": "apps.core.schema_enums.RunStatusChoices",
        "RunStartStatusEnum": "apps.core.schema_enums.RunStartStatusChoices",
        "RunFinishStatusEnum": "apps.core.schema_enums.RunFinishStatusChoices",
        "TaskStatusEnum": "apps.core.schema_enums.TaskStatusChoices",
        "TaskPriorityEnum": "apps.core.schema_enums.TaskPriorityChoices",
        "TaskActorEnum": "apps.core.schema_enums.TaskActorChoices",
        "SessionAgentEnum": "apps.core.schema_enums.SessionAgentChoices",
    },
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        }
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
