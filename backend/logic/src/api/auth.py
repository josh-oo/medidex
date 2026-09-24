from fastapi import APIRouter
from fastapi import Security, HTTPException, Depends
from fastapi.responses import Response
from fastapi.security import OAuth2PasswordBearer
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from dotenv import load_dotenv
from sqlmodel import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from sqlmodel import SQLModel, Field
from sqlalchemy import MetaData

from asyncio import get_running_loop

from typing import List, Optional
import os

from passlib.context import CryptContext

from jwcrypto import jwk
from jwcrypto.jwt import JWTExpired
from keycloak import KeycloakOpenID

import secrets
import hashlib

load_dotenv()

KEYCLOAK_URL = os.getenv("KEYCLOAK_URL")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "medidex")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "medidex-frontend")

POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DB_USERS = os.getenv("POSTGRES_DB_USERS")
POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = os.getenv("POSTGRES_PORT")

router = APIRouter(tags=["auth"])

# auto_error=False: callers may authenticate with an API key instead, see is_verified_api_call.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB_USERS}"

engine = create_async_engine(DATABASE_URL, echo=False)

if not KEYCLOAK_URL:
    raise RuntimeError("KEYCLOAK_URL must be set")

"""
Authentication

Identity, roles ("USER"/"ADMIN") and account approval ("APPROVED") are all
managed by Keycloak (realm: KEYCLOAK_REALM). Access tokens are validated
locally against the realm's public key(s). API keys remain a purely local
concept (Keycloak has no equivalent) and are stored alongside their owner's
Keycloak user id (the token's "sub" claim).
"""

keycloak_openid = KeycloakOpenID(
    server_url=KEYCLOAK_URL,
    client_id=KEYCLOAK_CLIENT_ID,
    realm_name=KEYCLOAK_REALM,
)

metadata_user_data = MetaData()

class APIKey(SQLModel, table=True, metadata=metadata_user_data):
    __tablename__ = "api_keys"

    id: str = Field(primary_key=True, index=True)
    owner: str = Field(index=True)  # Keycloak user id ("sub" claim)
    hash: str = Field(index=True)

class ApiKeyResponse(BaseModel):
    api_key: str

async def get_session() -> AsyncSession:
    async with AsyncSession(engine) as session:
        yield session

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

def generate_api_key_pair():
    key_id = secrets.token_urlsafe(8)  # short prefix
    secret = secrets.token_urlsafe(32)
    full_key = f"{key_id}.{secret}"
    # Unsalted deterministic hash (SHA-256 hex)
    key_hash = hashlib.sha256(full_key.encode("utf-8")).hexdigest()
    return key_id, key_hash, full_key

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

    Note: auto_error=False lets callers decide whether a missing token is acceptable (so
    endpoints can support either API keys or JWTs).
    """
    if not token:
        return None
    decoded = await verify_token(token)
    if not decoded:
        return None
    if "APPROVED" not in decoded.get("roles", []):
        raise HTTPException(status_code=401, detail="Not allowed")

    return token

async def verify_api_key(api_key: Optional[str] = Security(api_key_header), session: AsyncSession = Depends(get_session)):
    """Check the provided API key (if any). Returns True when valid, otherwise None.

    First tries new unsalted SHA-256 hash lookup by hash. If not found, falls back to legacy bcrypt verification.
    """
    if not api_key:
        return None

    # Compute SHA-256 hex of the provided full key and try direct hash match
    sha256_hex = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    statement = select(APIKey.hash).where(APIKey.hash == sha256_hex)
    match = (await session.execute(statement)).scalars().first()

    if match:
        return True

    # Fallback to legacy lookup by key_id and bcrypt verification
    return await verify_api_key_legacy(api_key, session)

async def verify_api_key_legacy(api_key: Optional[str], session: AsyncSession):
    """Check the provided API key (if any). Returns True when valid, otherwise None.

    Supports both legacy bcrypt-hashed keys and new unsalted SHA-256 hashes.
    """

    key_id = api_key.split(".")[0]

    # Fetch only the hash values
    statement = select(APIKey.hash).where(APIKey.id == key_id)
    hashes = (await session.execute(statement)).scalars().all()

    if not hashes:
        return None

    loop = get_running_loop()
    for h in hashes:
        if await loop.run_in_executor(None, pwd_context.verify, api_key, h):
            return True

    return None

def is_verified_api_call(token: Optional[str] = Depends(is_verified, use_cache=False), api_key_valid: Optional[bool] = Depends(verify_api_key, use_cache=False)):
    # Allow either a valid JWT token or a valid API key. Both dependencies use auto_error=False
    # so that FastAPI won't short-circuit with an HTTP error before we have a chance to
    # check the alternative authentication method.
    if token:
        return True
    if api_key_valid:
        return True
    raise HTTPException(status_code=401, detail="Not authenticated")

@router.put("/users/me/api_keys", summary="Create a new API key for the given user.", status_code=201)
async def create_api_key(token: str = Depends(is_verified), session: AsyncSession = Depends(get_session)) -> ApiKeyResponse:
    decoded = await verify_token(token)
    user_id = decoded["sub"]

    key_id, key_hash, full_key = generate_api_key_pair()

    api_key = APIKey(id=key_id, hash=key_hash, owner=user_id)
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)

    return {"api_key": full_key}

@router.delete("/users/me/api_keys/{key_id}", summary="Delete an API key belonging to the given user.", status_code=204)
async def delete_api_key(key_id: str, token: str = Depends(is_verified), session: AsyncSession = Depends(get_session)):
    decoded = await verify_token(token)
    user_id = decoded["sub"]

    statement = select(APIKey).where(APIKey.id == key_id, APIKey.owner == user_id)
    api_key = (await session.execute(statement)).scalars().first()

    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found or does not belong to user")

    await session.delete(api_key)
    await session.commit()

    return Response(status_code=204)

@router.get("/users/me/api_keys", summary="Get all API keys created by the given user.")
async def get_api_keys(token: str = Depends(is_verified), session: AsyncSession = Depends(get_session)) -> List[str]:
    decoded = await verify_token(token)
    user_id = decoded["sub"]

    statement = select(APIKey.id).where(APIKey.owner == user_id)  # Excluding password
    api_keys = (await session.execute(statement)).scalars().all()

    return api_keys
