import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from apps.services.api_keys import ApiKeyResolutionError
from apps.services.domain import (
    DomainServiceError,
    ProjectResolutionError,
    RunResolutionError,
    TaskResolutionError,
)
from apps.services.repositories import RepositoryResolutionError


logger = logging.getLogger(__name__)


def _plain(value):
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return str(value)


def api_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        errors = (
            exc.message_dict
            if hasattr(exc, "message_dict")
            else {"non_field_errors": exc.messages}
        )
        return Response(
            {"detail": "Validation failed.", "errors": _plain(errors)},
            status=400,
        )

    if isinstance(
        exc,
        (ProjectResolutionError, TaskResolutionError, RunResolutionError),
    ):
        errors = {}
        if isinstance(exc, ProjectResolutionError) and exc.candidates:
            errors["candidates"] = exc.candidates
        return Response({"detail": str(exc), "errors": errors}, status=404)

    if isinstance(exc, (ApiKeyResolutionError, RepositoryResolutionError)):
        return Response({"detail": str(exc), "errors": {}}, status=404)

    if isinstance(exc, DomainServiceError):
        return Response({"detail": str(exc), "errors": {}}, status=400)

    response = drf_exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled REST API exception")
        return Response(
            {"detail": "Internal server error.", "errors": {}},
            status=500,
        )

    data = response.data
    if isinstance(data, dict) and set(data) == {"detail"}:
        detail = str(data["detail"])
        errors = {}
    else:
        detail = "Validation failed."
        errors = (
            _plain(data)
            if isinstance(data, dict)
            else {"non_field_errors": _plain(data)}
        )
    response.data = {"detail": detail, "errors": errors}
    return response
