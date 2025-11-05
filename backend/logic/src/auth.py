from fastapi import APIRouter
from fastapi import Security, HTTPException, Depends
from fastapi.responses import Response
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
from sqlmodel import select, SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from .utils.database_models import APIKey, User

from typing import List, Literal
import os

from passlib.context import CryptContext

from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError

from datetime import datetime, timedelta, timezone

import secrets

load_dotenv()

router = APIRouter(tags=["auth"])


DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")
JWT_SECRET = os.getenv("JWT_SECRET")
DEBUG = os.getenv("DEBUG") == "TRUE"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
api_key_header = APIKeyHeader(name="X-API-Key")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DATABASE_URL = "sqlite+aiosqlite:///" + os.path.join(DATABASE_VOLUME,"persistent","users.db")

engine = create_async_engine(DATABASE_URL, echo=True)

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

"""
def get_session():
    with Session(engine) as session:
        yield session
"""

async def get_session() -> AsyncSession:
    async with AsyncSession(engine) as session:
        yield session

@router.on_event("startup")
async def startup_event():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

"""
def init_db():
    SQLModel.metadata.create_all(engine)

@router.on_event("startup")
def on_startup():
    init_db()
"""

def verify_token(token):
    try:
        # Decode and verify the JWT
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return decoded

    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token. Please log in again.")

def generate_token(user):
    expire = datetime.now(tz=timezone.utc) + timedelta(hours=8)
    return jwt.encode({'sub': user.email, 'role': user.role, 'id': user.id, 'verified': user.verified, 'exp': expire}, JWT_SECRET, algorithm='HS256')

def is_admin(token: str = Security(oauth2_scheme)):
    decoded = verify_token(token)
    if decoded['role'] != "admin":
        raise HTTPException(status_code=401, detail="Not allowed")
    return token

def is_verified(token: str = Security(oauth2_scheme)):
    if DEBUG:
        return token
    decoded = verify_token(token)
    if decoded['verified'] != 1:
        raise HTTPException(status_code=401, detail="Not allowed")
    return token

def generate_api_key_pair():
    key_id = secrets.token_urlsafe(8)  # short prefix
    secret = secrets.token_urlsafe(32)
    full_key = f"{key_id}.{secret}"
    key_hash = pwd_context.hash(full_key)
    return key_id, key_hash, full_key

async def verify_api_key(api_key: str = Security(api_key_header), session: AsyncSession = Depends(get_session)):
    key_id = api_key.split(".")[0]

    statement = select(APIKey.hash).where(APIKey.id == key_id)
    matching_keys = (await session.execute(statement)).scalars().all()

    if matching_keys is None:
        raise HTTPException(status_code=400, detail="Invalid api key")

    for key in matching_keys:
        if pwd_context.verify(api_key, key.hash):
            return Response(status_code=201)
    
    raise HTTPException(status_code=400, detail="Invalid api key")

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
async def update_user(user_id: int, role: Literal["user", "admin"], session: AsyncSession = Depends(get_session)) -> UserDataResponse:
    
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
    decoded = verify_token(token)
    user_id = decoded['id']

    key_id, key_hash, full_key = generate_api_key_pair()

    api_key = APIKey(id=key_id, hash=key_hash, owner=user_id)
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)

    return {"api_key": full_key}

@router.delete("/users/me/api_keys/{key_id}", summary="Delete an API key belonging to the given user.", status_code=204)
async def delete_api_key(key_id: str, token: str = Depends(is_verified), session: AsyncSession = Depends(get_session)):
    decoded = verify_token(token)
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
    decoded = verify_token(token)
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
