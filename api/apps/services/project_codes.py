import re

from django.utils.text import slugify

from apps.projects.models import Project


def generate_project_slug(name, exclude_project_id=None):
    """Return an available ASCII slug, falling back to pj-<number>."""
    base = slugify(str(name or "").strip())[:64]
    queryset = Project.objects.all()
    if exclude_project_id:
        queryset = queryset.exclude(pk=exclude_project_id)
    used = {value.casefold() for value in queryset.values_list("slug", flat=True)}

    if not base:
        number = 1
        while f"pj-{number:02d}" in used:
            number += 1
        return f"pj-{number:02d}"

    if base.casefold() not in used:
        return base

    suffix = 2
    while True:
        suffix_text = f"-{suffix}"
        candidate = f"{base[: 64 - len(suffix_text)]}{suffix_text}"
        if candidate.casefold() not in used:
            return candidate
        suffix += 1


def generate_project_code(name, slug=None, exclude_project_id=None):
    """Return the next available project code without persisting it."""
    source = slug or name
    base = re.sub(r"[^A-Za-z0-9]", "", source).upper()[:8]
    queryset = Project.objects.all()
    if exclude_project_id:
        queryset = queryset.exclude(pk=exclude_project_id)
    used = {code.upper() for code in queryset.values_list("code", flat=True)}

    if not base:
        number = 1
        while f"PJ{number:02d}" in used:
            number += 1
        return f"PJ{number:02d}"

    if base not in used:
        return base

    suffix = 2
    while True:
        suffix_text = str(suffix)
        candidate = f"{base[: 12 - len(suffix_text)]}{suffix_text}"
        if candidate not in used:
            return candidate
        suffix += 1
