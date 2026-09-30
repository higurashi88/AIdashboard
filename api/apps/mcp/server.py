from apps.mcp.authentication import McpApiKeyMiddleware
from apps.mcp.registry import mcp_server

# Importing registers exactly the six tools declared in the project specification.
from apps.mcp import tools as _tools  # noqa: E402,F401


mcp_asgi_application = McpApiKeyMiddleware(mcp_server.streamable_http_app())
