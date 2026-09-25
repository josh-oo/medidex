"""Builds the Medidex MCP server.

Runs in the same process/container as the REST API (see app/backend/CLAUDE.md),
but this module only builds the MCPServer instance. Splicing it into the
shared FastAPI app is main.py's job, not this package's - main.py is the one
place allowed to know that fastapi_app and mcp_server are being combined into
one process; this module has no idea it's being mounted into anything.
"""

from mcp.server import MCPServer
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl

from .auth import KeycloakMCPTokenVerifier, MCP_RESOURCE_URL
from . import tools
from . import resources
from src.utils.keycloak import KEYCLOAK_PUBLIC_URL, KEYCLOAK_REALM

MCP_STREAMABLE_HTTP_PATH = "/mcp"


def create_server() -> MCPServer:
    server = MCPServer(
        name="Medidex",
        instructions=(
            "Search and retrieve clinical study and report records from Medidex, "
            "including which reports are already linked to a study."
        ),
        token_verifier=KeycloakMCPTokenVerifier(),
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
    resources.register(server)
    return server
