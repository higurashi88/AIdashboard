from rest_framework.permissions import BasePermission

from apps.core.models import ApiKey


class HasApiKeyScope(BasePermission):
    """Restrict a view using static or HTTP-method-specific API key scopes."""

    message = "This API key does not have the required scope"

    def has_permission(self, request, view):
        api_key = request.auth
        if not isinstance(api_key, ApiKey) or not api_key.is_active:
            return False
        scopes_by_method = getattr(view, "api_key_scopes_by_method", {})
        allowed_scopes = scopes_by_method.get(
            request.method,
            getattr(view, "api_key_scopes", None),
        )
        if allowed_scopes is None or api_key.scope in allowed_scopes:
            return True
        expected = ", ".join(sorted(allowed_scopes))
        self.message = (
            f"API key scope '{api_key.scope}' is not allowed; "
            f"required scope: {expected}."
        )
        return False
