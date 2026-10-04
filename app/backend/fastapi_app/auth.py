from fastapi import APIRouter
from fastapi import Security, HTTPException, Depends
from fastapi.security import OAuth2AuthorizationCodeBearer
from dotenv import load_dotenv

from typing import Optional
import os

from src.utils.keycloak import (
    KEYCLOAK_URL,
    KEYCLOAK_PUBLIC_URL,
    KEYCLOAK_REALM,
    InvalidTokenError,
    TokenExpiredError,
    create_keycloak_openid,
    verify_token as verify_keycloak_token,
)
from src.services.authorization import (
    AdminRequiredError,
    NotApprovedError,
    require_admin,
    require_approved,
)

load_dotenv()

KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "medidex-frontend")

router = APIRouter(tags=["auth"])

# This declares the standard OAuth2 authorization-code flow so that Swagger UI's
# "Authorize" button redirects to Keycloak's own hosted login page instead of
# collecting a username/password itself. Token verification below is unaffected -
# it still just decodes whatever bearer token is presented against the realm's
# JWKS, regardless of how the caller obtained it.
oauth2_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl=f"{KEYCLOAK_PUBLIC_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/auth",
    tokenUrl=f"{KEYCLOAK_PUBLIC_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token",
    auto_error=False,
)

"""
Authentication

Identity, roles ("USER"/"ADMIN") and account approval ("APPROVED") are all
managed by Keycloak (realm: KEYCLOAK_REALM). Access tokens are validated
locally against the realm's public key(s) - the actual JWKS fetch/decode
logic lives in ../utils/keycloak.py so it can be reused outside this
FastAPI-specific presentation tier.
"""

keycloak_openid = create_keycloak_openid(KEYCLOAK_CLIENT_ID)

async def decode_token(token: Optional[str]) -> dict:
    """Decode a Keycloak-issued access token into its claims, or raise HTTPException."""
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        return await verify_keycloak_token(token, keycloak_openid)
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token. Please log in again.")

async def get_roles(token: str = Security(oauth2_scheme)):
    decoded = await decode_token(token)
    return decoded.get("roles", [])

async def is_admin(token: str = Security(oauth2_scheme)) -> dict:
    """Require a token with the ADMIN role. Returns its decoded claims."""
    decoded = await decode_token(token)
    try:
        require_admin(decoded.get("roles", []))
    except AdminRequiredError:
        raise HTTPException(status_code=401, detail="Not allowed")
    return decoded

async def get_user(token: Optional[str] = Security(oauth2_scheme)) -> Optional[dict]:
    """Decode the caller's token, requiring the APPROVED role if a token was
    given at all. Returns the decoded claims when valid, or None when no
    token was given - callers decide whether that's acceptable (auto_error=False
    on oauth2_scheme lets a missing token reach here instead of FastAPI
    rejecting it outright). Raises HTTPException if a token was given but
    isn't APPROVED.

    Replaces what used to be two separate dependencies: get_user_id (only
    needed decoded["sub"]) and is_verified (needed the APPROVED check) - every
    caller of either one decoded the same token the same way, so there was no
    reason to keep them apart. One side effect: get_context (fastapi_app/deps.py)
    depends on this for user_id, so nearly every route now gets the APPROVED
    check for free instead of only the routes that happened to also declare
    Depends(is_verified)/is_admin/is_verified_api_call.
    """
    if not token:
        return None
    decoded = await decode_token(token)
    try:
        require_approved(decoded.get("roles", []))
    except NotApprovedError:
        raise HTTPException(status_code=401, detail="Not allowed")

    return decoded

def is_verified_api_call(
    claims: Optional[dict] = Depends(get_user, use_cache=False),
):
    """Require an authenticated, approved caller (JWT in the Authorization header).

    Routes depend on this rather than get_user directly so a downstream
    deployable can swap in additional credential types via
    `app.dependency_overrides[is_verified_api_call]`.
    """
    if claims:
        return True
    raise HTTPException(status_code=401, detail="Not authenticated")
