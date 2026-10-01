import os

import fastmcp
from fastmcp.tools.function_tool import FunctionTool
from mcp.types import ToolAnnotations
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.types import ASGIApp

from golinks_mcp.tools.audit_log import AuditLogListOutput, get_audit_logs
from golinks_mcp.tools.collections import CollectionsListOutput, search_collections
from golinks_mcp.tools.golinks import (
    GoLinkOutput,
    GoLinksListOutput,
    create_golink,
    get_golink,
    list_golinks,
)
from golinks_mcp.tools.search import SearchGoLinksOutput, search_golinks
from golinks_mcp.tools.users import UsersListOutput, search_users

# OAuth discovery env vars with production defaults
_ISSUER = os.environ.get("GOLINKS_OAUTH_ISSUER", "https://www.golinks.io")
_AUTHORIZE_URL = os.environ.get(
    "GOLINKS_OAUTH_AUTHORIZE_URL",
    "https://app.golinks.io/oauth_authorize.php",
)
_TOKEN_URL = os.environ.get(
    "GOLINKS_OAUTH_TOKEN_URL",
    "https://api.golinks.io/oauth/token",
)
_REVOKE_URL = os.environ.get(
    "GOLINKS_OAUTH_REVOKE_URL",
    "https://api.golinks.io/oauth/revoke",
)
_MCP_RESOURCE_URL = os.environ.get("MCP_RESOURCE_URL", "https://mcp.golinks.io")

_SCOPES = ["golinks:read", "golinks:write", "search:read", "admin:read", "users:read"]
_OPENAI_CHALLENGE_TOKEN = "P1DPnUpwXo9fibpB43IR6ar4KQFzN3eJTgfdTThNDDU"

mcp = fastmcp.FastMCP("GoLinks")

mcp.add_tool(
    FunctionTool.from_function(
        list_golinks,
        title="List go links",
        output_schema=GoLinksListOutput.model_json_schema(),
        annotations=ToolAnnotations(
            title="List go links",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
)
mcp.add_tool(
    FunctionTool.from_function(
        get_golink,
        title="Get go link",
        output_schema=GoLinkOutput.model_json_schema(),
        annotations=ToolAnnotations(
            title="Get go link",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
)
mcp.add_tool(
    FunctionTool.from_function(
        search_golinks,
        title="Search go links",
        output_schema=SearchGoLinksOutput.model_json_schema(),
        annotations=ToolAnnotations(
            title="Search go links",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
)
mcp.add_tool(
    FunctionTool.from_function(
        create_golink,
        title="Create go link",
        output_schema=GoLinkOutput.model_json_schema(),
        annotations=ToolAnnotations(
            title="Create go link",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
)
mcp.add_tool(
    FunctionTool.from_function(
        get_audit_logs,
        title="Get audit logs",
        output_schema=AuditLogListOutput.model_json_schema(),
        annotations=ToolAnnotations(
            title="Get audit logs",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
)
mcp.add_tool(
    FunctionTool.from_function(
        search_collections,
        title="Search collections",
        output_schema=CollectionsListOutput.model_json_schema(),
        annotations=ToolAnnotations(
            title="Search collections",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
)
mcp.add_tool(
    FunctionTool.from_function(
        search_users,
        title="Search users",
        output_schema=UsersListOutput.model_json_schema(),
        annotations=ToolAnnotations(
            title="Search users",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
)


class RequireBearerOnMCP(BaseHTTPMiddleware):
    """Return 401 + WWW-Authenticate on /mcp when no Bearer token is present.

    Without this, MCP clients (e.g. Claude) skip OAuth discovery and treat the
    connector as unauthenticated.
    """

    def __init__(self, app: ASGIApp, resource_metadata_url: str) -> None:
        super().__init__(app)
        self._resource_metadata_url = resource_metadata_url

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path == "/mcp":
            auth = request.headers.get("authorization", "")
            if not auth.lower().startswith("bearer "):
                return JSONResponse(
                    {"error": "unauthorized"},
                    status_code=401,
                    headers={
                        "WWW-Authenticate": (
                            f'Bearer realm="GoLinks MCP", '
                            f'resource_metadata="{self._resource_metadata_url}"'
                        )
                    },
                )
        return await call_next(request)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


@mcp.custom_route("/.well-known/openai-apps-challenge", methods=["GET"])
async def openai_challenge(request: Request) -> PlainTextResponse:
    return PlainTextResponse(_OPENAI_CHALLENGE_TOKEN)


@mcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])
async def oauth_protected_resource_metadata(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "resource": _MCP_RESOURCE_URL,
            "authorization_servers": [_MCP_RESOURCE_URL],
            "scopes_supported": _SCOPES,
            "bearer_methods_supported": ["header"],
        }
    )


@mcp.custom_route("/.well-known/oauth-protected-resource/mcp", methods=["GET"])
async def oauth_protected_resource_metadata_mcp(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "resource": f"{_MCP_RESOURCE_URL}/mcp",
            "authorization_servers": [_MCP_RESOURCE_URL],
            "scopes_supported": _SCOPES,
            "bearer_methods_supported": ["header"],
        }
    )


@mcp.custom_route("/.well-known/oauth-authorization-server", methods=["GET"])
async def oauth_authorization_server_metadata(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "issuer": _ISSUER,
            "authorization_endpoint": _AUTHORIZE_URL,
            "token_endpoint": _TOKEN_URL,
            "revocation_endpoint": _REVOKE_URL,
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
            "scopes_supported": _SCOPES,
        }
    )
