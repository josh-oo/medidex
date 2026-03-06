from fastapi import APIRouter
from fastapi import Security, HTTPException, Depends
from fastapi.responses import Response
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
from sqlmodel import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from sqlmodel import SQLModel, Field
from sqlalchemy import MetaData
from pydantic import EmailStr

from asyncio import get_running_loop

from typing import List, Literal, Optional
import os

from passlib.context import CryptContext

import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

import httpx

from datetime import datetime, timedelta, timezone

import secrets
import hashlib

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET")
JWKS_URL = os.getenv("JWKS_URL")

POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DB_USERS = os.getenv("POSTGRES_DB_USERS")
POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = os.getenv("POSTGRES_PORT")

router = APIRouter(tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB_USERS}"

engine = create_async_engine(DATABASE_URL, echo=False)

if not JWT_SECRET or len(JWT_SECRET) < 32:
    raise RuntimeError("JWT_SECRET must be set and at least 32 characters long")

"""
Authentication
"""

metadata_user_data = MetaData()

class User(SQLModel, table=True, metadata=metadata_user_data):
    __tablename__ = "users"

    id: int = Field(default=None, primary_key=True)
    email: EmailStr = Field(index=True, unique=True)
    role: str = Field(default="USER")
    verified: bool = Field(default=False)
    password: str

class APIKey(SQLModel, table=True, metadata=metadata_user_data):
    __tablename__ = "api_keys"

    id: str = Field(primary_key=True, index=True)
    owner: int = Field(foreign_key="users.id", ondelete="CASCADE")
    hash: str = Field(index=True)

class UserDataResponse(BaseModel):
    id: int
    email: EmailStr
    role: str
    verified: bool

    model_config = {
        "from_attributes": True
    }

class TokenResponse(BaseModel):
    access_token: str
    token_type: str

class ApiKeyResponse(BaseModel):
    api_key: str

async def get_session() -> AsyncSession:
    async with AsyncSession(engine) as session:
        yield session

# Cache for JWKS keys - reload on failure
_jwks_cache = None

async def get_jwks_keys(force_refresh: bool = False):
    """Fetch and cache JWKS keys. Reloads on failure or when forced."""
    global _jwks_cache
    
    if _jwks_cache and not force_refresh:
        return _jwks_cache
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(JWKS_URL)
            response.raise_for_status()
            jwks_data = response.json()
            _jwks_cache = jwks_data.get("keys", [])
            return _jwks_cache
    except Exception:
        # If cache exists, return it even if refresh failed
        if _jwks_cache:
            return _jwks_cache
        # Otherwise, let the exception propagate
        raise

async def verify_token_jwks(token: str):
    """Verify token using JWKS endpoint. Returns decoded token or raises exception."""
    # Get the kid from token header
    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")
    
    if not kid:
        return None
    
    # Try with cached keys first
    keys = await get_jwks_keys(force_refresh=False)
    
    # Find matching key
    jwk_key = None
    for key in keys:
        if key.get("kid") == kid:
            jwk_key = key
            break
    
    # If key not found, try refreshing the cache once
    if not jwk_key:
        keys = await get_jwks_keys(force_refresh=True)
        for key in keys:
            if key.get("kid") == kid:
                jwk_key = key
                break
    
    if not jwk_key:
        return None
    
    # Get algorithm from JWK
    algorithm = jwk_key.get("alg", "EdDSA")
    
    # Convert JWK to public key
    public_key = jwt.algorithms.get_default_algorithms()[algorithm].from_jwk(jwk_key)
    
    # Verify and decode token
    decoded = jwt.decode(
        token,
        public_key,
        algorithms=[algorithm],
        options={"verify_aud": False}
    )
    return decoded

async def verify_token(token):
    """Verify token with JWKS support. Routes to JWKS or legacy based on kid presence."""
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        # Check if token has kid (new system) or not (legacy)
        unverified_header = jwt.get_unverified_header(token)
        
        if unverified_header.get("kid"):
            # New JWKS-based token
            decoded = await verify_token_jwks(token)
            return decoded
        else:
            # Legacy JWT_SECRET token
            decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            return decoded

    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token. Please log in again.")

def generate_token(user):
    expire = datetime.now(tz=timezone.utc) + timedelta(hours=8)
    return jwt.encode({'sub': user.email, 'roles': [user.role], 'id': user.id, 'isApproved': user.verified, 'exp': expire}, JWT_SECRET, algorithm='HS256')

def generate_api_key_pair():
    key_id = secrets.token_urlsafe(8)  # short prefix
    secret = secrets.token_urlsafe(32)
    full_key = f"{key_id}.{secret}"
    # Unsalted deterministic hash (SHA-256 hex)
    key_hash = hashlib.sha256(full_key.encode("utf-8")).hexdigest()
    return key_id, key_hash, full_key

"""
Authentication
"""

async def get_roles(token: str = Security(oauth2_scheme)):
    decoded = await verify_token(token)
    return decoded['roles']

async def is_admin(token: str = Security(oauth2_scheme)):
    decoded = await verify_token(token)
    if not "ADMIN" in decoded['roles']:
        raise HTTPException(status_code=401, detail="Not allowed")
    return token

async def get_user_id(token: Optional[str] = Security(oauth2_scheme)):
    if not token:
        return None
    result = await verify_token(token)
    if not result:
        return None
    return str(result['id'])

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
    if not decoded.get('isApproved', False):
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

@router.get("/users", dependencies=[Depends(is_admin)], summary="List all users (admin only).")
async def get_users(session: AsyncSession = Depends(get_session)) -> List[UserDataResponse]:
    users = (await session.execute(select(User))).scalars().all()
    safe_users = [UserDataResponse.from_orm(user) for user in users]
    return safe_users

@router.put("/users/{user_id}/email", dependencies=[Depends(is_admin)], summary="Update user email (admin only).")
async def update_user(user_id: int, value: EmailStr, session: AsyncSession = Depends(get_session)) -> UserDataResponse:
    
    old_user = await session.get(User, user_id)
    if old_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    old_user.email = value

    session.add(old_user)
    await session.commit()
    await session.refresh(old_user) 

    return UserDataResponse.from_orm(old_user)

@router.put("/users/{user_id}/verified", dependencies=[Depends(is_admin)], summary="Update user 'verified' state (admin only).")
async def update_user(user_id: int, verified: bool, session: AsyncSession = Depends(get_session)) -> UserDataResponse:
    
    old_user = await session.get(User, user_id)
    if old_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    old_user.verified = verified

    session.add(old_user)
    await session.commit()
    await session.refresh(old_user) 

    return UserDataResponse.from_orm(old_user)

@router.put("/users/{user_id}/role", dependencies=[Depends(is_admin)], summary="Update user role (admin only).")
async def update_user(user_id: int, role: Literal["USER", "ADMIN"], session: AsyncSession = Depends(get_session)) -> UserDataResponse:
    
    old_user = await session.get(User, user_id)
    if old_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    old_user.role = role

    session.add(old_user)
    await session.commit()
    await session.refresh(old_user) 

    return UserDataResponse.from_orm(old_user)

@router.put("/users/me/api_keys", summary="Create a new API key for the given user.", status_code=201)
async def create_api_key(token: str = Depends(is_verified), session: AsyncSession = Depends(get_session)) -> ApiKeyResponse:
    decoded = await verify_token(token)
    user_id = decoded['id']

    key_id, key_hash, full_key = generate_api_key_pair()

    api_key = APIKey(id=key_id, hash=key_hash, owner=user_id)
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)

    return {"api_key": full_key}

@router.delete("/users/me/api_keys/{key_id}", summary="Delete an API key belonging to the given user.", status_code=204)
async def delete_api_key(key_id: str, token: str = Depends(is_verified), session: AsyncSession = Depends(get_session)):
    decoded = await verify_token(token)
    user_id = decoded['id']

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
    user_id = decoded['id']

    statement = select(APIKey.id).where(APIKey.owner == user_id) # Excluding password
    api_keys = (await session.execute(statement)).scalars().all()

    return api_keys

@router.post("/signup", summary="Sign up a new user. Returns a JWT token.")
async def signup(form_data: OAuth2PasswordRequestForm = Depends(), session: AsyncSession = Depends(get_session)) -> TokenResponse:
    statement = select(User).where(User.email == form_data.username)
    existing_user = (await session.execute(statement)).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_pw = pwd_context.hash(form_data.password)
    new_user = User(email=form_data.username, password=hashed_pw)
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)  # fetch ID and other DB-generated fields

    token = generate_token(new_user)

    return {"access_token": token, "token_type": "bearer"}

@router.post("/login", summary="Log in existing user. Returns a JWT token.")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), session: AsyncSession = Depends(get_session)) -> TokenResponse:
    statement = select(User).where(User.email == form_data.username)
    existing_user = (await session.execute(statement)).scalars().first()

    # Validate credentials
    if not existing_user or not pwd_context.verify(form_data.password, existing_user.password):
        raise HTTPException(status_code=400, detail="Invalid credentials")

    return {"access_token": generate_token(existing_user), "token_type": "bearer"}

@router.post("/logout", summary="Log out the current user (not yet implemented)")
def logout():
    #TODO maybe add to blacklist
    return {"message": "Logout successful"}
