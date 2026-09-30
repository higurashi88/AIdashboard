from django.conf import settings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings


mcp_server = FastMCP(
    "AIdashboard",
    instructions=(
        "個人プロジェクトの現在地とタスクを管理します。"
        "作業開始時はget_project、終了時はreport_sessionを呼んでください。"
    ),
    stateless_http=True,
    streamable_http_path="/mcp",
    transport_security=TransportSecuritySettings(
        allowed_hosts=settings.MCP_ALLOWED_HOSTS,
        allowed_origins=settings.MCP_ALLOWED_ORIGINS,
    ),
)
