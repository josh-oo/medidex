"""Builds the Medidex MCP server and mounts it into the shared FastAPI app.

Runs in the same process/container as the REST API (see app/backend/CLAUDE.md) -
mounted onto the existing `app` in main.py rather than a separate service, the
same way agent/agent.py's router is included there.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import AnyHttpUrl

from mcp.server import MCPServer
from mcp.server.auth.settings import AuthSettings

from .auth import KeycloakMCPTokenVerifier, MCP_RESOURCE_URL
from . import tools
from . import resources
from src.api.auth import KEYCLOAK_PUBLIC_URL, KEYCLOAK_REALM

MCP_STREAMABLE_HTTP_PATH = "/mcp"


def build_mcp_server() -> MCPServer:
    server = MCPServer(
        name="Medidex",
        instructions=(
            "Search and retrieve clinical study and report records from Medidex, "
            "including which reports are already linked to a study."
        ),
        token_verifier=KeycloakMCPTokenVerifier(),
        auth=AuthSettings(
            # Must be the browser/host-reachable Keycloak URL (same one used for
            # the Swagger UI's OAuth redirect in src/api/auth.py), not KEYCLOAK_URL
            # (the internal Docker hostname) - MCP clients like mcp-remote run on
            # the host and fetch this URL directly, they can't resolve "keycloak".
            issuer_url=AnyHttpUrl(f"{KEYCLOAK_PUBLIC_URL}/realms/{KEYCLOAK_REALM}"),
            resource_server_url=AnyHttpUrl(MCP_RESOURCE_URL),
            validate_token_resource=True,
            # Without this, PRM's scopes_supported is omitted and MCP clients
            # (e.g. mcp-remote) fall back to requesting every scope Keycloak's
            # realm advertises in its own OIDC discovery document - most of
            # which medidex-mcp isn't entitled to, so Keycloak rejects the
            # authorization request outright (invalid_scope). "openid" is
            # always valid for any OIDC client; access control here is by
            # role + audience (see mcp_server/auth.py), not OAuth scopes.
            required_scopes=["openid"],
        ),
    )
    tools.register(server)
    resources.register(server)
    return server


def mount(app: FastAPI, mcp_server: MCPServer, path: str = MCP_STREAMABLE_HTTP_PATH) -> None:
    """Splice the MCP server's routes/middleware directly into `app`.

    Deliberately not `app.mount(path, mcp_server.streamable_http_app())`: the SDK
    registers its RFC 9728 protected-resource-metadata route at the host's
    absolute root (/.well-known/oauth-protected-resource/...), independent of
    where the /mcp endpoint itself lives. Wrapping the whole sub-app in a path
    Mount would nest that well-known route under the mount prefix too, making it
    unreachable at the URL the server itself advertises in its 401
    WWW-Authenticate header - verified against the installed SDK version before
    picking this approach (see plan for the reasoning).
    """
    sub_app = mcp_server.streamable_http_app(streamable_http_path=path)

    app.router.routes.extend(sub_app.routes)
    # Appended (not inserted at index 0 via add_middleware) so existing
    # middleware - notably CORS, added in main.py before this call runs -
    # stays outermost.
    app.user_middleware.extend(sub_app.user_middleware)

    existing_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def combined_lifespan(app: FastAPI):
        async with mcp_server.session_manager.run():
            async with existing_lifespan(app) as state:
                yield state

    app.router.lifespan_context = combined_lifespan
