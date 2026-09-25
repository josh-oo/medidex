"""Keycloak-backed token verification for the MCP resource server.

Reuses the JWKS cache and decode/retry logic already in src/api/auth.py (the
REST API's own Keycloak integration) instead of re-implementing JWT handling.
This verifier differs only in which Keycloak client - and therefore which
token audience - it checks tokens against: REST API tokens are scoped to
medidex-frontend, MCP tokens are scoped to medidex-mcp (see
deploy/keycloak/realm-medidex.json).
"""

import os

from fastapi import HTTPException
from keycloak import KeycloakOpenID

from mcp.server.auth.provider import AccessToken, TokenVerifier

from src.api.auth import KEYCLOAK_URL, KEYCLOAK_REALM, verify_token as verify_keycloak_token

KEYCLOAK_MCP_CLIENT_ID = os.getenv("KEYCLOAK_MCP_CLIENT_ID", "medidex-mcp")
MCP_RESOURCE_URL = os.getenv("MCP_RESOURCE_URL")

if not MCP_RESOURCE_URL:
    raise RuntimeError("MCP_RESOURCE_URL must be set")

# Separate KeycloakOpenID instance so python-keycloak's own aud/azp check in
# a_decode_token() validates against the MCP client's id, not the frontend's.
# JWKS itself is realm-level and shared via the cache in src/api/auth.py.
_mcp_keycloak_openid = KeycloakOpenID(
    server_url=KEYCLOAK_URL,
    client_id=KEYCLOAK_MCP_CLIENT_ID,
    realm_name=KEYCLOAK_REALM,
)


class KeycloakMCPTokenVerifier(TokenVerifier):
    """Validates bearer tokens issued to the medidex-mcp Keycloak client."""

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            decoded = await verify_keycloak_token(token, keycloak_openid_client=_mcp_keycloak_openid)
        except HTTPException:
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
