"""監視対象のローカル Git リポジトリの登録・編集（設定画面から使う）。

状態の受け取りは domain.record_repository_statuses が受け持つ。
"""

from pathlib import PureWindowsPath

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.projects.models import Repository


class RepositoryResolutionError(Exception):
    pass


STATUS_FIELDS_TO_RESET = {
    "branch": "",
    "upstream": "",
    "ahead": None,
    "behind": None,
    "changed_files": None,
    "untracked_files": None,
    "last_commit_at": None,
    "last_commit_sha": "",
    "last_commit_subject": "",
    "status_error": "",
    "collected_at": None,
}


def repository_name_from_path(path):
    return PureWindowsPath(path).name or path


def _ensure_unique_path(path, exclude_id=None):
    duplicates = Repository.objects.filter(path__iexact=path)
    if exclude_id is not None:
        duplicates = duplicates.exclude(pk=exclude_id)
    if duplicates.exists():
        raise ValidationError({"path": f"このパスは既に登録されています: {path}"})


def get_repository(repository_id):
    try:
        return Repository.objects.select_related("project").get(pk=repository_id)
    except (Repository.DoesNotExist, ValidationError) as exc:
        raise RepositoryResolutionError(f"Repository could not be resolved: {repository_id}") from exc


@transaction.atomic
def create_repository(path, name="", project=None, is_active=True, sort_order=0):
    _ensure_unique_path(path)
    repository = Repository(
        path=path,
        name=(name or "").strip() or repository_name_from_path(path),
        project=project,
        is_active=is_active,
        sort_order=sort_order,
    )
    repository.full_clean()
    repository.save(force_insert=True)
    return repository


@transaction.atomic
def update_repository(repository_id, **changes):
    repository = get_repository(repository_id)
    if "path" in changes and changes["path"] != repository.path:
        _ensure_unique_path(changes["path"], exclude_id=repository.pk)
        repository.path = changes["path"]
        # 別のフォルダの状態を表示し続けないよう、次の収集まで空にする
        for field, value in STATUS_FIELDS_TO_RESET.items():
            setattr(repository, field, value)
    if "name" in changes:
        repository.name = (changes["name"] or "").strip() or repository_name_from_path(repository.path)
    if "project" in changes:
        repository.project = changes["project"]
    if "is_active" in changes:
        repository.is_active = changes["is_active"]
    if "sort_order" in changes:
        repository.sort_order = changes["sort_order"]
    repository.full_clean()
    repository.save()
    return repository


@transaction.atomic
def delete_repository(repository_id):
    get_repository(repository_id).delete()
