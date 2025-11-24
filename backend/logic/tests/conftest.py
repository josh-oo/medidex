import pytest
import os
import tempfile
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from sqlmodel import SQLModel
from typing import AsyncGenerator
import asyncio

# Set test environment variables
test_db_dir = tempfile.mkdtemp()
os.makedirs(os.path.join(test_db_dir, "persistent"), exist_ok=True)
os.makedirs(os.path.join(test_db_dir, "resources"), exist_ok=True)
os.environ["DATABASE_VOLUME"] = test_db_dir
os.environ["JWT_SECRET"] = "test_secret_key_with_at_least_32_chars_long"
os.environ["DEBUG"] = "TRUE"
os.environ["EMBEDDING_HOST"] = "localhost"
os.environ["EMBEDDING_PORT"] = "50051"
os.environ["VECTORSTORE_HOST"] = "localhost"
os.environ["VECTORSTORE_PORT"] = "6334"

from api import app
from src.auth import engine as auth_engine


@pytest.fixture(scope="function", autouse=True)
async def setup_database():
    """Setup database tables before running each test."""
    async with auth_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield


@pytest.fixture(scope="function")
def test_app():
    """Provide the FastAPI application instance."""
    return app


@pytest.fixture
def client(test_app):
    """Provide a synchronous test client."""
    return TestClient(test_app)


@pytest.fixture
async def async_client(test_app) -> AsyncGenerator:
    """Provide an async test client."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), 
        base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
async def test_user_token(async_client: AsyncClient) -> str:
    """Create a test user and return the auth token."""
    response = await async_client.post(
        "/signup",
        data={
            "username": "test@example.com",
            "password": "testpassword123"
        }
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
async def test_admin_token(async_client: AsyncClient) -> str:
    """Create a test admin user and return the auth token."""
    # First create a regular user
    response = await async_client.post(
        "/signup",
        data={
            "username": "admin@example.com",
            "password": "adminpassword123"
        }
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    
    # In a real scenario, you'd need to manually update the user role to admin
    # For now, we'll just return the token
    return token


@pytest.fixture
def auth_headers(test_user_token: str) -> dict:
    """Provide authorization headers with test user token."""
    return {"Authorization": f"Bearer {test_user_token}"}


@pytest.fixture
def admin_headers(test_admin_token: str) -> dict:
    """Provide authorization headers with admin user token."""
    return {"Authorization": f"Bearer {test_admin_token}"}
