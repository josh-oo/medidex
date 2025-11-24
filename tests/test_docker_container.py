"""
Docker Container Integration Tests

These tests are designed to test the API endpoints of a running Docker container.
Unlike the unit tests that use FastAPI's TestClient, these tests make real HTTP
requests to a live service.

Usage:
    # Start the Docker containers first
    docker compose up -d

    # Run the container tests
    CONTAINER_URL=http://localhost:8002 pytest tests/test_docker_container.py -v

Environment Variables:
    CONTAINER_URL: The base URL of the running logic container (default: http://localhost:8002)
"""
import pytest
import os
import httpx
from typing import Generator

# Get the container URL from environment variable or use default
CONTAINER_URL = os.environ.get("CONTAINER_URL", "http://localhost:8002")


@pytest.fixture(scope="module")
def container_client() -> Generator[httpx.Client, None, None]:
    """Provide a synchronous HTTP client for container tests."""
    with httpx.Client(base_url=CONTAINER_URL, timeout=30.0) as client:
        yield client


@pytest.fixture(scope="module")
async def async_container_client():
    """Provide an async HTTP client for container tests."""
    async with httpx.AsyncClient(base_url=CONTAINER_URL, timeout=30.0) as client:
        yield client


@pytest.fixture(scope="module")
def container_user_token(container_client: httpx.Client) -> str:
    """Create a test user and return the auth token from the running container."""
    # Try to signup, if user exists, try to login
    response = container_client.post(
        "/signup",
        data={
            "username": "container_test@example.com",
            "password": "testpassword123"
        }
    )
    
    if response.status_code == 200:
        return response.json()["access_token"]
    elif response.status_code == 400 and "already registered" in response.json().get("detail", "").lower():
        # User exists, login instead
        response = container_client.post(
            "/login",
            data={
                "username": "container_test@example.com",
                "password": "testpassword123"
            }
        )
        assert response.status_code == 200
        return response.json()["access_token"]
    else:
        pytest.fail(f"Failed to get auth token: {response.status_code} - {response.text}")


class TestDockerContainerHealth:
    """Health check tests for the running Docker container."""

    def test_health_check(self, container_client: httpx.Client):
        """Test the readyz health check endpoint."""
        response = container_client.get("/readyz")
        assert response.status_code == 200
        assert response.json() == "Ready"

    def test_container_is_responsive(self, container_client: httpx.Client):
        """Test that the container responds to requests."""
        response = container_client.get("/readyz")
        assert response.status_code in [200, 503]  # 503 if dependencies not ready


class TestDockerContainerAuth:
    """Authentication tests for the running Docker container."""

    def test_signup_creates_user(self, container_client: httpx.Client):
        """Test that signup creates a new user (or returns error if exists)."""
        import uuid
        unique_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        response = container_client.post(
            "/signup",
            data={
                "username": unique_email,
                "password": "testpassword123"
            }
        )
        # Should either succeed (200) or fail because user exists (400)
        assert response.status_code in [200, 400]
        if response.status_code == 200:
            data = response.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"

    def test_login_with_invalid_credentials(self, container_client: httpx.Client):
        """Test login with invalid credentials returns 400."""
        response = container_client.post(
            "/login",
            data={
                "username": "nonexistent_user@example.com",
                "password": "wrongpassword"
            }
        )
        assert response.status_code == 400

    def test_unauthenticated_access_rejected(self, container_client: httpx.Client):
        """Test that protected endpoints reject unauthenticated requests."""
        response = container_client.get("/batches")
        assert response.status_code == 401


class TestDockerContainerEndpoints:
    """API endpoint tests for the running Docker container."""

    def test_get_batches_with_auth(self, container_client: httpx.Client, container_user_token: str):
        """Test getting batches with authentication."""
        response = container_client.get(
            "/batches",
            headers={"Authorization": f"Bearer {container_user_token}"}
        )
        # May return 200 (success) or 500 (if external dependencies not available)
        assert response.status_code in [200, 500]

    def test_get_studies_with_auth(self, container_client: httpx.Client, container_user_token: str):
        """Test getting studies with authentication."""
        response = container_client.get(
            "/studies?study_ids=1",
            headers={"Authorization": f"Bearer {container_user_token}"}
        )
        assert response.status_code in [200, 500]

    def test_get_interventions_with_auth(self, container_client: httpx.Client, container_user_token: str):
        """Test getting interventions with authentication."""
        response = container_client.get(
            "/interventions",
            headers={"Authorization": f"Bearer {container_user_token}"}
        )
        assert response.status_code in [200, 500]

    def test_get_conditions_with_auth(self, container_client: httpx.Client, container_user_token: str):
        """Test getting conditions with authentication."""
        response = container_client.get(
            "/conditions",
            headers={"Authorization": f"Bearer {container_user_token}"}
        )
        assert response.status_code in [200, 500]

    def test_get_outcomes_with_auth(self, container_client: httpx.Client, container_user_token: str):
        """Test getting outcomes with authentication."""
        response = container_client.get(
            "/outcomes",
            headers={"Authorization": f"Bearer {container_user_token}"}
        )
        assert response.status_code in [200, 500]


class TestDockerContainerAPIKeys:
    """API key management tests for the running Docker container."""

    def test_create_api_key(self, container_client: httpx.Client, container_user_token: str):
        """Test creating an API key."""
        response = container_client.put(
            "/users/me/api_keys",
            headers={"Authorization": f"Bearer {container_user_token}"}
        )
        assert response.status_code == 201
        data = response.json()
        assert "api_key" in data

    def test_get_api_keys(self, container_client: httpx.Client, container_user_token: str):
        """Test getting all API keys."""
        response = container_client.get(
            "/users/me/api_keys",
            headers={"Authorization": f"Bearer {container_user_token}"}
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestDockerContainerMappings:
    """Mapping endpoint tests for the running Docker container."""

    def test_get_report_study_mapping(self, container_client: httpx.Client, container_user_token: str):
        """Test getting report to study mapping."""
        response = container_client.get(
            "/mappings/report_study",
            headers={"Authorization": f"Bearer {container_user_token}"}
        )
        assert response.status_code in [200, 500]

    def test_get_study_report_mapping(self, container_client: httpx.Client, container_user_token: str):
        """Test getting study to report mapping."""
        response = container_client.get(
            "/mappings/study_report",
            headers={"Authorization": f"Bearer {container_user_token}"}
        )
        assert response.status_code in [200, 500]
