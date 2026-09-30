import os

from django.core.asgi import get_asgi_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_application = get_asgi_application()

# Import after Django setup because the MCP authentication layer uses Django models.
from apps.mcp.server import mcp_asgi_application  # noqa: E402


class PathRoutingApplication:
    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await mcp_asgi_application(scope, receive, send)
            return
        path = scope.get("path", "")
        if path == "/mcp" or path.startswith("/mcp/"):
            await mcp_asgi_application(scope, receive, send)
            return
        await django_application(scope, receive, send)


application = PathRoutingApplication()
