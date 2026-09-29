"""Keycloak-backed token verification for the MCP resource server.

All actual verification - token decode/expiry (src/utils/keycloak.py),
APPROVED-role and RFC 8707 resource-audience checks (src/services/
authorization.py) - lives at the src level and is shared with
fastapi_app/auth.py. This module is just the MCP-specific adapter: it picks
the medidex-mcp Keycloak client (a different token audience than the REST
API's medidex-frontend, see deploy/keycloak/realm-medidex.json), translates
the shared checks' outcome into the TokenVerifier protocol (None on any
failure, no HTTPException), and builds the resulting AccessToken.
"""

import os

from mcp.server.auth.provider import AccessToken, TokenVerifier

from src.utils.keycloak import InvalidTokenError, create_keycloak_openid, verify_token as verify_keycloak_token
from src.services.authorization import (
    NotApprovedError,
    ResourceMismatchError,
    require_approved,
    require_resource_audience,
)

KEYCLOAK_MCP_CLIENT_ID = os.getenv("KEYCLOAK_MCP_CLIENT_ID", "medidex-mcp")
MCP_RESOURCE_URL = os.getenv("MCP_RESOURCE_URL")

if not MCP_RESOURCE_URL:
    raise RuntimeError("MCP_RESOURCE_URL must be set")

# Own KeycloakOpenID instance so python-keycloak's own aud/azp check in
# a_decode_token() validates against the MCP client's id, not the frontend's.
# JWKS itself is realm-level and shared via the cache in src/utils/keycloak.py.
_mcp_keycloak_openid = create_keycloak_openid(KEYCLOAK_MCP_CLIENT_ID)


class KeycloakMCPTokenVerifier(TokenVerifier):
    """Validates bearer tokens issued to the medidex-mcp Keycloak client."""

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            decoded = await verify_keycloak_token(token, _mcp_keycloak_openid)
        except InvalidTokenError:
            return None

        try:
            require_approved(decoded.get("roles", []))
            require_resource_audience(decoded, MCP_RESOURCE_URL)
        except (NotApprovedError, ResourceMismatchError):
            return None

        return AccessToken(
            token=token,
            client_id=decoded.get("azp", KEYCLOAK_MCP_CLIENT_ID),
            scopes=decoded.get("scope", "").split() if decoded.get("scope") else [],
            expires_at=decoded.get("exp"),
            resource=MCP_RESOURCE_URL,
            subject=decoded.get("sub"),
            claims=decoded,
        )
