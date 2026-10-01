"""Builds the Medidex MCP server and splices it into a FastAPI app.

Runs in the same process/container as the REST API (see app/backend/CLAUDE.md).
create_server() only builds the MCPServer instance; mount() is what actually
grafts its routes onto an existing FastAPI app. Both live here (not in
main.py) so a downstream deployable that builds its own composed app -
extending the OSS routers/tools rather than forking this module - can import
and reuse the exact same splicing logic instead of re-deriving the RFC 9728
workaround documented in mount() below.
"""

import base64
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable, Iterable, Optional

from fastapi import FastAPI
from mcp.server import MCPServer
from mcp.server.auth.settings import AuthSettings
from mcp.server.subscriptions import InMemorySubscriptionBus
from mcp.types import Icon
from pydantic import AnyHttpUrl

from .auth import KeycloakMCPTokenVerifier, MCP_RESOURCE_URL
from . import live_updates
from . import tools
from src.utils.keycloak import KEYCLOAK_PUBLIC_URL, KEYCLOAK_REALM

MCP_STREAMABLE_HTTP_PATH = "/mcp"

FAVICON_B64 = base64.b64encode((Path(__file__).parent / "favicon.ico").read_bytes()).decode()


def create_server(extra_tool_registrars: Iterable[Callable[[MCPServer], None]] = ()) -> MCPServer:
    """Build the MCP server with the OSS tool set, plus any additional
    registrars a downstream deployable wants mounted alongside it (e.g. an
    enterprise build adding its own tools without forking tools.py).
    """
    # Own bus instance (rather than the server's default) so live_updates'
    # lifespan task can publish to the exact same object passed to
    # subscriptions= below, without reaching into MCPServer's private state.
    subscriptions = InMemorySubscriptionBus()

    server = MCPServer(
        name="Medidex",
        icons=[Icon(src=f"data:image/x-icon;base64,{FAVICON_B64}")],
        instructions=(
            "Search and retrieve clinical study and report records from Medidex, "
            "including which reports are already linked to a study. Also exposes "
            "project management: reviewing projects and tasks, and (admin-only) "
            "creating projects and assigning/removing review tasks."
        ),
        token_verifier=KeycloakMCPTokenVerifier(),
        subscriptions=subscriptions,
        lifespan=live_updates.lifespan(subscriptions),
        auth=AuthSettings(
            # Must be the browser/host-reachable Keycloak URL (same one used for
            # the Swagger UI's OAuth redirect in fastapi_app/auth.py), not KEYCLOAK_URL
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
    for register_extra in extra_tool_registrars:
        register_extra(server)
    return server


def mount(app: FastAPI, server: MCPServer, path: str = MCP_STREAMABLE_HTTP_PATH) -> None:
    """Splice the MCP server's routes/middleware directly into `app`.

    Deliberately not `app.mount(path, server.streamable_http_app())`: the SDK
    registers its RFC 9728 protected-resource-metadata route at the host's
    absolute root (/.well-known/oauth-protected-resource/...), independent of
    where the /mcp endpoint itself lives. Wrapping the whole sub-app in a path
    Mount would nest that well-known route under the mount prefix too, making it
    unreachable at the URL the server itself advertises in its 401
    WWW-Authenticate header - verified against the installed SDK version before
    picking this approach.
    """
    sub_app = server.streamable_http_app(streamable_http_path=path)

    app.router.routes.extend(sub_app.routes)
    # Appended (not inserted at index 0 via add_middleware) so existing
    # middleware - notably CORS, added in fastapi_app.create_app() - stays
    # outermost.
    app.user_middleware.extend(sub_app.user_middleware)

    existing_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def combined_lifespan(app: FastAPI):
        async with server.session_manager.run():
            async with existing_lifespan(app) as state:
                yield state

    app.router.lifespan_context = combined_lifespan
