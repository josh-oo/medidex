"""Framework-agnostic Keycloak token verification core.

Shared by fastapi_app/auth.py (the REST API's FastAPI-facing auth dependencies)
and mcp_server/auth.py (the MCP server's TokenVerifier) - both validate
against the same realm's JWKS, they just decode against different Keycloak
clients (different audiences) and wrap failures differently (HTTPException
for FastAPI, None for the MCP TokenVerifier protocol). Nothing in this module
imports FastAPI or raises HTTP-specific errors, so it can be reused outside
the REST API's presentation tier.
"""

import os

from dotenv import load_dotenv
from jwcrypto import jwk
from jwcrypto.jwt import JWTExpired
from keycloak import KeycloakOpenID

load_dotenv()

KEYCLOAK_URL = os.getenv("KEYCLOAK_URL")
# Browser/host-reachable Keycloak URL - used wherever a redirect or discovery
# document needs to be resolvable from outside the Docker network (the
# Swagger UI's OAuth redirect, the MCP server's advertised issuer). Falls
# back to KEYCLOAK_URL for setups where that's already publicly reachable.
KEYCLOAK_PUBLIC_URL = os.getenv("KEYCLOAK_PUBLIC_URL", KEYCLOAK_URL)
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "medidex")

if not KEYCLOAK_URL:
    raise RuntimeError("KEYCLOAK_URL must be set")

# Cache of the realm's signing key(s) - reload on failure or kid mismatch.
# Realm-level (not client-level), so it's shared across every KeycloakOpenID
# instance callers construct with create_keycloak_openid().
_jwk_set_cache = None


def create_keycloak_openid(client_id: str) -> KeycloakOpenID:
    """Build a KeycloakOpenID bound to a specific client (i.e. audience).

    python-keycloak's a_decode_token() validates a token's aud/azp against
    whichever client_id the instance was constructed with, so each Keycloak
    client that issues tokens for this backend to consume (medidex-frontend,
    medidex-mcp, ...) needs its own instance.
    """
    return KeycloakOpenID(
        server_url=KEYCLOAK_URL,
        client_id=client_id,
        realm_name=KEYCLOAK_REALM,
    )


async def get_jwk_set(keycloak_openid: KeycloakOpenID, force_refresh: bool = False):
    """Fetch and cache the realm's JWK set. Reloads on failure or when forced."""
    global _jwk_set_cache

    if _jwk_set_cache and not force_refresh:
        return _jwk_set_cache

    try:
        certs = await keycloak_openid.a_certs()
        key_set = jwk.JWKSet()
        for cert in certs["keys"]:
            key_set.add(jwk.JWK(**cert))
        _jwk_set_cache = key_set
        return _jwk_set_cache
    except Exception:
        # If cache exists, return it even if refresh failed
        if _jwk_set_cache:
            return _jwk_set_cache
        # Otherwise, let the exception propagate
        raise


async def decode_access_token(token: str, keycloak_openid: KeycloakOpenID) -> dict:
    """Decode and verify a Keycloak access token against the realm's JWKS.

    Raises jwcrypto.jwt.JWTExpired for an expired token, or whatever
    python-keycloak/jwcrypto raise for any other invalid token (bad
    signature, wrong audience, malformed, ...) - callers translate those
    into their own error convention (HTTPException, None, ...).
    """
    key_set = await get_jwk_set(keycloak_openid, force_refresh=False)
    try:
        return await keycloak_openid.a_decode_token(token, key=key_set)
    except JWTExpired:
        raise
    except Exception:
        # Signing key may have rotated; refresh once and retry
        key_set = await get_jwk_set(keycloak_openid, force_refresh=True)
        return await keycloak_openid.a_decode_token(token, key=key_set)
