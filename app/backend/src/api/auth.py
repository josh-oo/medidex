from fastapi import APIRouter
from fastapi import Security, HTTPException, Depends
from fastapi.security import OAuth2AuthorizationCodeBearer, APIKeyHeader
from dotenv import load_dotenv

from typing import Optional
import os
import time

import httpx
from jwcrypto import jwk
from jwcrypto.jwt import JWTExpired
from keycloak import KeycloakOpenID

load_dotenv()

KEYCLOAK_URL = os.getenv("KEYCLOAK_URL")
# Browser-reachable Keycloak URL, used for the Swagger UI authorization-code
# redirect (the browser talks to Keycloak directly, not through KEYCLOAK_URL,
# which is the backend's internal-network address). Falls back to
# KEYCLOAK_URL for setups where that's already publicly reachable.
KEYCLOAK_PUBLIC_URL = os.getenv("KEYCLOAK_PUBLIC_URL", KEYCLOAK_URL)
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "medidex")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "medidex-frontend")

router = APIRouter(tags=["auth"])

# This declares the standard OAuth2 authorization-code flow so that Swagger UI's
# "Authorize" button redirects to Keycloak's own hosted login page instead of
# collecting a username/password itself. Token verification below is unaffected -
# it still just decodes whatever bearer token is presented against the realm's
# JWKS, regardless of how the caller obtained it (including a client_credentials
# token from an API-key service-account client, see api/admin.py).
oauth2_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl=f"{KEYCLOAK_PUBLIC_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/auth",
    tokenUrl=f"{KEYCLOAK_PUBLIC_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token",
    auto_error=False,
)
# API keys (see api/admin.py) are sent as a plain opaque string in this header,
# same as the old locally-issued keys - verify_api_key() below is what makes
# that transparent even though a key is really a Keycloak client's credentials.
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

if not KEYCLOAK_URL:
    raise RuntimeError("KEYCLOAK_URL must be set")

"""
Authentication

Identity, roles ("USER"/"ADMIN") and account approval ("APPROVED") are all
managed by Keycloak (realm: KEYCLOAK_REALM). Access tokens are validated
locally against the realm's public key(s).
"""

keycloak_openid = KeycloakOpenID(
    server_url=KEYCLOAK_URL,
    client_id=KEYCLOAK_CLIENT_ID,
    realm_name=KEYCLOAK_REALM,
)

# Cache of the realm's signing key(s) - reload on failure or kid mismatch
_jwk_set_cache = None

async def get_jwk_set(force_refresh: bool = False):
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

async def verify_token(token):
    """Verify a Keycloak-issued access token and return its decoded claims."""
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        key_set = await get_jwk_set(force_refresh=False)
        try:
            decoded = await keycloak_openid.a_decode_token(token, key=key_set)
        except JWTExpired:
            raise
        except Exception:
            # Signing key may have rotated; refresh once and retry
            key_set = await get_jwk_set(force_refresh=True)
            decoded = await keycloak_openid.a_decode_token(token, key=key_set)
        return decoded
    except JWTExpired:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token. Please log in again.")

async def get_roles(token: str = Security(oauth2_scheme)):
    decoded = await verify_token(token)
    return decoded.get("roles", [])

async def is_admin(token: str = Security(oauth2_scheme)):
    decoded = await verify_token(token)
    if "ADMIN" not in decoded.get("roles", []):
        raise HTTPException(status_code=401, detail="Not allowed")
    return token

async def get_user_id(token: Optional[str] = Security(oauth2_scheme)):
    if not token:
        return None
    decoded = await verify_token(token)
    if not decoded:
        return None
    return decoded.get("sub")

async def is_verified(token: Optional[str] = Security(oauth2_scheme)):
    """Validate a JWT token if provided. Returns the token string when valid, otherwise None.

    Note: auto_error=False lets callers decide whether a missing token is acceptable.
    """
    if not token:
        return None
    decoded = await verify_token(token)
    if not decoded:
        return None
    if "APPROVED" not in decoded.get("roles", []):
        raise HTTPException(status_code=401, detail="Not allowed")

    return token

"""
API keys

An API key is "<client_id>.<client_secret>" for a Keycloak client_credentials
client created via api/admin.py - but callers just send it as a single opaque
string in X-API-Key, exactly like the old locally-issued keys. Verifying one
means exchanging it for an access token at Keycloak's normal token endpoint
and decoding that the same way as any other token; the exchanged token is
cached for its lifetime so a script sending the same key on every request
doesn't round-trip to Keycloak each time.
"""

_api_key_token_cache: dict = {}

async def exchange_api_key_for_token(client_id: str, client_secret: str) -> Optional[str]:
    cached = _api_key_token_cache.get(client_id)
    now = time.monotonic()
    if cached and cached["expires_at"] > now:
        return cached["token"]

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
    except httpx.HTTPError:
        return None

    if response.status_code != 200:
        return None

    data = response.json()
    token = data.get("access_token")
    if not token:
        return None
    # Refresh a bit before actual expiry so a request never races an expired cache entry.
    _api_key_token_cache[client_id] = {
        "token": token,
        "expires_at": now + max(data.get("expires_in", 60) - 10, 0),
    }
    return token

def revoke_api_key_cache(client_id: str) -> None:
    """Drop a cached exchange for a client_id so deleting it takes effect immediately.

    Without this, a key deleted right after being used would keep authenticating
    for up to its cached token's remaining lifetime (see api/admin.py's delete_api_key,
    which also caps that lifetime via access.token.lifespan when creating the client).
    """
    _api_key_token_cache.pop(client_id, None)

async def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> Optional[bool]:
    """Check the provided API key (if any). Returns True when valid, otherwise None."""
    if not api_key or "." not in api_key:
        return None

    client_id, client_secret = api_key.split(".", 1)
    token = await exchange_api_key_for_token(client_id, client_secret)
    if not token:
        return None

    try:
        decoded = await verify_token(token)
    except HTTPException:
        return None
    if "APPROVED" not in decoded.get("roles", []):
        return None
    return True

def is_verified_api_call(
    token: Optional[str] = Depends(is_verified, use_cache=False),
    api_key_valid: Optional[bool] = Depends(verify_api_key, use_cache=False),
):
    """Allow either a valid JWT (Authorization header) or a valid API key (X-API-Key header)."""
    if token:
        return True
    if api_key_valid:
        return True
    raise HTTPException(status_code=401, detail="Not authenticated")
