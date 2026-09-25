"""Keycloak-backed token verification for the MCP resource server.

Reuses the framework-agnostic JWKS cache and decode/retry logic in
src/utils/keycloak.py - not fastapi_app/auth.py, which is the REST API's FastAPI
presentation tier (Security/Depends dependencies, HTTPException translation)
and stays a REST-only concern. This verifier differs from the REST API's own
token verification only in which Keycloak client - and therefore which token
audience - it checks tokens against: REST API tokens are scoped to
medidex-frontend, MCP tokens are scoped to medidex-mcp (see
deploy/keycloak/realm-medidex.json).
"""

import os

from mcp.server.auth.provider import AccessToken, TokenVerifier

from src.utils.keycloak import create_keycloak_openid, decode_access_token

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
        if not token:
            return None

        try:
            decoded = await decode_access_token(token, _mcp_keycloak_openid)
        except Exception:
            return None

        if "APPROVED" not in decoded.get("roles", []):
            return None

        # RFC 8707 resource binding: require the resource-indicator audience
        # mapper (audience-medidex-mcp-resource) to be present, not just a
        # valid medidex-mcp client audience/azp.
        aud = decoded.get("aud")
        aud_list = aud if isinstance(aud, list) else [aud] if aud else []
        if MCP_RESOURCE_URL not in aud_list:
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
