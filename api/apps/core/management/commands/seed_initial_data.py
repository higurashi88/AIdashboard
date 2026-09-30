import os
import tomllib
from pathlib import Path, PureWindowsPath

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.automations.models import Automation
from apps.projects.models import Project, Repository


DEFAULT_CONFIG_NAME = "projects.toml"
EXAMPLE_CONFIG_NAME = "projects.example.toml"

PROJECT_FIELDS = {
    "slug", "code", "name", "root_path", "summary",
    "is_active", "sort_order", "is_pinned", "color",
}
AUTOMATION_FIELDS = {
    "key", "project", "name", "scheduled_task_name",
    "schedule_human", "script_path", "state",
}
REPOSITORY_FIELDS = {"path", "project", "name", "is_active", "sort_order"}


def config_dir():
    """設定ファイルの置き場所。

    コンテナでは compose が ./config を /config へ読み取り専用でマウントし、
    DASHBOARD_CONFIG_DIR でその場所を指す。
    ホストから直接実行する場合（pytest など）はリポジトリ直下の config/ を使う。
    """
    override = os.getenv("DASHBOARD_CONFIG_DIR")
    if override:
        return Path(override)
    return Path(settings.BASE_DIR).parent / "config"


def _repository_name(path):
    return PureWindowsPath(path).name or path


class Command(BaseCommand):
    help = (
        "config/projects.toml からプロジェクト・自動化・リポジトリを冪等に登録する。"
        "ファイルが無ければ config/projects.example.toml を使う。"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--config",
            help="設定ファイルのパス（既定: config/projects.toml、無ければ example）",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="DBへ書き込まず、読み取れた内容だけを表示する",
        )

    def resolve_config_path(self, explicit):
        if explicit:
            path = Path(explicit)
            if not path.exists():
                raise CommandError(f"設定ファイルが見つかりません: {path}")
            return path

        primary = config_dir() / DEFAULT_CONFIG_NAME
        if primary.exists():
            return primary

        example = config_dir() / EXAMPLE_CONFIG_NAME
        if example.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"{primary} が無いため {EXAMPLE_CONFIG_NAME} を使います。"
                    f"自分のプロジェクトを登録するには "
                    f"{EXAMPLE_CONFIG_NAME} を {DEFAULT_CONFIG_NAME} にコピーして編集してください。"
                )
            )
            return example

        raise CommandError(
            f"設定ファイルがありません。{config_dir()} に "
            f"{DEFAULT_CONFIG_NAME} を置いてください。"
        )

    def load(self, path):
        try:
            with path.open("rb") as handle:
                data = tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            raise CommandError(f"{path} の解析に失敗しました: {exc}") from exc

        projects = data.get("project", [])
        automations = data.get("automation", [])
        repositories = data.get("repository", [])

        if not projects:
            raise CommandError(f"{path} に [[project]] が1件もありません")

        for entry in projects:
            missing = {"slug", "code", "name"} - entry.keys()
            if missing:
                raise CommandError(
                    f"[[project]] に必須キーがありません: {', '.join(sorted(missing))} "
                    f"（{entry.get('slug', '不明なエントリ')}）"
                )
            unknown = entry.keys() - PROJECT_FIELDS
            if unknown:
                raise CommandError(
                    f"[[project]] に未知のキーがあります: {', '.join(sorted(unknown))}"
                )

        slugs = {entry["slug"] for entry in projects}
        for entry in automations:
            missing = {"key", "project"} - entry.keys()
            if missing:
                raise CommandError(
                    f"[[automation]] に必須キーがありません: {', '.join(sorted(missing))}"
                )
            unknown = entry.keys() - AUTOMATION_FIELDS
            if unknown:
                raise CommandError(
                    f"[[automation]] に未知のキーがあります: {', '.join(sorted(unknown))}"
                )
            if entry["project"] not in slugs:
                raise CommandError(
                    f"自動化 {entry['key']} が参照するプロジェクト "
                    f"'{entry['project']}' が同じファイルに定義されていません"
                )

        paths = set()
        for entry in repositories:
            if "path" not in entry:
                raise CommandError("[[repository]] に必須キーがありません: path")
            unknown = entry.keys() - REPOSITORY_FIELDS
            if unknown:
                raise CommandError(
                    f"[[repository]] に未知のキーがあります: {', '.join(sorted(unknown))}"
                )
            if entry.get("project") and entry["project"] not in slugs:
                raise CommandError(
                    f"リポジトリ {entry['path']} が参照するプロジェクト "
                    f"'{entry['project']}' が同じファイルに定義されていません"
                )
            if entry["path"] in paths:
                raise CommandError(f"[[repository]] の path が重複しています: {entry['path']}")
            paths.add(entry["path"])

        return projects, automations, repositories

    @transaction.atomic
    def handle(self, *args, **options):
        path = self.resolve_config_path(options.get("config"))
        projects, automations, repositories = self.load(path)

        self.stdout.write(f"設定ファイル: {path}")

        if options.get("dry_run"):
            for entry in projects:
                self.stdout.write(f"  project   {entry['slug']:<20} {entry['name']}")
            for entry in automations:
                self.stdout.write(f"  automation {entry['key']:<20} -> {entry['project']}")
            for entry in repositories:
                self.stdout.write(
                    f"  repository {entry['path']} -> {entry.get('project') or '（PJなし）'}"
                )
            self.stdout.write(self.style.WARNING("--dry-run のため書き込みませんでした"))
            return

        project_created = project_updated = 0
        projects_by_slug = {}
        for entry in projects:
            slug = entry["slug"]
            defaults = {k: v for k, v in entry.items() if k != "slug"}
            project, created = Project.objects.update_or_create(slug=slug, defaults=defaults)
            projects_by_slug[slug] = project
            project_created += int(created)
            project_updated += int(not created)

        automation_created = automation_updated = 0
        for entry in automations:
            defaults = {k: v for k, v in entry.items() if k not in {"key", "project"}}
            defaults["project"] = projects_by_slug[entry["project"]]
            _, created = Automation.objects.update_or_create(key=entry["key"], defaults=defaults)
            automation_created += int(created)
            automation_updated += int(not created)

        repository_created = repository_updated = 0
        for entry in repositories:
            defaults = {k: v for k, v in entry.items() if k not in {"path", "project"}}
            defaults.setdefault("name", _repository_name(entry["path"]))
            defaults["project"] = projects_by_slug.get(entry.get("project"))
            _, created = Repository.objects.update_or_create(
                path=entry["path"], defaults=defaults
            )
            repository_created += int(created)
            repository_updated += int(not created)

        self.stdout.write(
            self.style.SUCCESS(
                "Seed complete: "
                f"projects created={project_created}, updated={project_updated}; "
                f"automations created={automation_created}, updated={automation_updated}; "
                f"repositories created={repository_created}, updated={repository_updated}"
            )
        )
