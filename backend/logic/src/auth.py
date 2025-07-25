from fastapi import Security, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, EmailStr, constr
from dotenv import load_dotenv
from typing import Optional
import os

import sqlite3
from passlib.context import CryptContext

from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError

from datetime import datetime, timedelta, timezone

import secrets

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

class UserUpdate(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None
    verified: Optional[bool] = None

class UserOut(BaseModel):
    id: int
    email: EmailStr

class UserCreate(BaseModel):
    email: EmailStr
    password: constr(min_length=8)

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

def create_api_key(owner: int, db: sqlite3.Connection = Depends(get_db)):
    
    key_id, key_hash, full_key = generate_api_key_pair()
    db.execute(
        "INSERT INTO api_keys (id, hash, owner) VALUES (?, ?, ?)",
        (key_id, key_hash, owner)
    )
    db.commit()
    return JSONResponse(status_code=201, content={"api_key": full_key})

def delete_api_key(key_id: str, db: sqlite3.Connection = Depends(get_db)):

    cursor = db.cursor()

    cursor.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,))
    api_key = cursor.fetchone()
    if api_key is None:
        raise HTTPException(status_code=404, detail="Api key not found")

    cursor.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
    db.commit()
    return JSONResponse(status_code=201, content={"message": "Key removed"})

def get_api_keys(owner: int, db: sqlite3.Connection = Depends(get_db)):
    
    query = "SELECT id FROM api_keys WHERE owner = ?"  # Excluding password
    cursor = db.cursor()  # Create the cursor
    cursor.execute(query, (owner,))   # Execute the query
    rows = cursor.fetchall()  # Fetch all results

    return rows

def get_users(db: sqlite3.Connection = Depends(get_db)):
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

def update_user(user_id: int, user_update: UserUpdate, db: sqlite3.Connection = Depends(get_db)):
    
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

def signup(user: UserCreate, db: sqlite3.Connection = Depends(get_db)):
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
    return generate_token(new_user)

def login(form_data: OAuth2PasswordRequestForm = Depends(), db: sqlite3.Connection = Depends(get_db)):
    db.row_factory = sqlite3.Row
    # Find user by email
    cursor = db.execute("SELECT * FROM users WHERE email = ?", (form_data.username,))
    user = cursor.fetchone()

    # Validate credentials
    if not user or not pwd_context.verify(form_data.password, user["password"]):
        raise HTTPException(status_code=400, detail="Invalid credentials")

    return generate_token(user)

def logout():
    #TODO maybe add to blacklist
    return JSONResponse(status_code=201, content={"message": "Logout successful"})
