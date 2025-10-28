from fastapi import APIRouter
from fastapi import Security, HTTPException, Depends
from fastapi.responses import JSONResponse, Response
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, EmailStr, SecretStr
from dotenv import load_dotenv
from typing import Optional, List
from enum import Enum
import os

import sqlite3
from passlib.context import CryptContext

from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError

from datetime import datetime, timedelta, timezone

import secrets

router = APIRouter(tags=["auth"])

load_dotenv()

DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")
JWT_SECRET = os.getenv("JWT_SECRET")
DEBUG = os.getenv("DEBUG") == "TRUE"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
api_key_header = APIKeyHeader(name="X-API-Key")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_db():
    conn = sqlite3.connect(os.path.join(DATABASE_VOLUME,"users.db"))
    try:
        yield conn
    finally:
        conn.close()

class Roles(Enum):
    user = 'user'
    admin = 'admin'

class User(BaseModel):
    email: EmailStr
    role: Roles = Roles.user
    verified: Optional[bool] = None
    id: Optional[int] = None

class UserCredentials(BaseModel):
    email: EmailStr
    password: SecretStr

class TokenResponse(BaseModel):
    access_token: str
    token_type: str

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
    expire = datetime.now(tz=timezone.utc) + timedelta(minutes=15)
    return jwt.encode({'sub': user['email'], 'role': user['role'], 'id': user['id'], 'verified': user['verified'], 'exp': expire}, JWT_SECRET, algorithm='HS256')

def is_admin(token: str = Depends(oauth2_scheme)):
    decoded = verify_token(token)
    if decoded['role'] != "admin":
        raise HTTPException(status_code=401, detail="Not allowed")
    return token

def is_verified(token: str = Depends(oauth2_scheme)):
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

def verify_api_key(api_key: str = Security(api_key_header), db: sqlite3.Connection = Depends(get_db)):
    key_id = api_key.split(".")[0]
    cursor = db.cursor()
    cursor.execute("SELECT hash FROM api_keys WHERE id = ?", (key_id,))
    rows = cursor.fetchall()

    for row in rows:
        if pwd_context.verify(api_key, row[0]):
            return JSONResponse(status_code=201, content={"message": "Api key valid"})
    
    raise HTTPException(status_code=400, detail="Invalid api key")

@router.get("/users", dependencies=[Depends(is_admin)], summary="List all users (admin only)")
def get_users(db: sqlite3.Connection = Depends(get_db)) -> List[User]:
    query = "SELECT id, email, role, verified FROM users"  # Excluding password
    cursor = db.cursor()  # Create the cursor
    cursor.execute(query)   # Execute the query
    rows = cursor.fetchall()  # Fetch all results

    users = []
    for row in rows:
        user = {
            "id": row[0],
            "email": row[1],
            "role": row[2],
            "verified": row[3],
        }
        users.append(user)

    return users

@router.put("/users/{user_id}", dependencies=[Depends(is_admin)], summary="Update user information (admin only)")
def update_user(user_id: int, user_update: User, db: sqlite3.Connection = Depends(get_db)):
    
    fields = []
    values = []

    for field, value in user_update.dict(exclude_unset=True).items():
        fields.append(f"{field} = ?")
        values.append(value)

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update.")

    values.append(user_id)
    query = f"UPDATE users SET {', '.join(fields)} WHERE id = ?"

    cursor = db.cursor()
    cursor.execute(query, values)
    db.commit()

    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found.")

    return {"message": "User updated successfully"}

@router.put("/users/me/api_keys", summary="Create a new API key for the given user", status_code=201)
def create_api_key(token: str = Depends(is_verified), db: sqlite3.Connection = Depends(get_db)):
    decoded = verify_token(token)
    user_id = decoded['id']

    key_id, key_hash, full_key = generate_api_key_pair()
    db.execute(
        "INSERT INTO api_keys (id, hash, owner) VALUES (?, ?, ?)",
        (key_id, key_hash, user_id)
    )
    db.commit()
    return {"api_key": full_key}

@router.delete("/users/me/api_keys/{key_id}", summary="Delete an API key belonging to the given user", status_code=204)
def delete_api_key(key_id: str, token: str = Depends(is_verified), db: sqlite3.Connection = Depends(get_db)):
    decoded = verify_token(token)
    user_id = decoded['id']

    cursor = db.cursor()

    cursor.execute("SELECT * FROM api_keys WHERE id = ? AND owner = ?", (key_id, user_id))
    api_key = cursor.fetchone()
    if api_key is None:
        raise HTTPException(status_code=404, detail="API key not found or does not belong to user")

    cursor.execute("DELETE FROM api_keys WHERE id = ? AND owner = ?", (key_id, user_id))
    db.commit()

    return Response(status_code=204)

@router.get("/users/me/api_keys", summary="Get all API keys created by the given user")
def get_api_keys(token: str = Depends(is_verified), db: sqlite3.Connection = Depends(get_db)) -> List[str]:
    decoded = verify_token(token)
    user_id = decoded['id']

    query = "SELECT id FROM api_keys WHERE owner = ?"  # Excluding password
    cursor = db.cursor()  # Create the cursor
    cursor.execute(query, (user_id,))   # Execute the query
    rows = cursor.fetchall()  # Fetch all results

    return rows

@router.post("/signup", summary="Sign up a new users")
def signup(user: UserCredentials, db: sqlite3.Connection = Depends(get_db)) -> TokenResponse:
    db.row_factory = sqlite3.Row
    cursor = db.cursor()

    # Check if user already exists
    cursor.execute("SELECT * FROM users WHERE email = ?", (user.email,))
    existing_user = cursor.fetchone()
    if existing_user:
        db.close()
        raise HTTPException(status_code=400, detail="Email already registered")

    # Insert new user
    hashed_pw = pwd_context.hash(user.password)
    cursor.execute(
        "INSERT INTO users (email, password) VALUES (?, ?)",
        (user.email, hashed_pw)
    )
    db.commit()

    # Fetch the new user (with ID)
    new_user_id = cursor.lastrowid
    cursor.execute("SELECT * FROM users WHERE id = ?", (new_user_id,))
    new_user = cursor.fetchone()
    return {"access_token": generate_token(new_user), "token_type": "bearer"}

@router.post("/login", summary="Log in existing user and returns JWT token")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: sqlite3.Connection = Depends(get_db)) -> TokenResponse:
    db.row_factory = sqlite3.Row
    # Find user by email
    cursor = db.execute("SELECT * FROM users WHERE email = ?", (form_data.username,))
    user = cursor.fetchone()

    # Validate credentials
    if not user or not pwd_context.verify(form_data.password, user["password"]):
        raise HTTPException(status_code=400, detail="Invalid credentials")

    return {"access_token": generate_token(user), "token_type": "bearer"}

@router.post("/logout", summary="Log out the current user (not yet implemented)")
def logout():
    #TODO maybe add to blacklist
    return {"message": "Logout successful"}
