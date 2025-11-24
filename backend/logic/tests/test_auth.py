import pytest
from httpx import AsyncClient


class TestAuthEndpoints:
    """Test cases for authentication endpoints."""

    async def test_signup_success(self, async_client: AsyncClient):
        """Test successful user signup."""
        response = await async_client.post(
            "/signup",
            data={
                "username": "newuser@example.com",
                "password": "newpassword123"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_signup_duplicate_email(self, async_client: AsyncClient, test_user_token: str):
        """Test signup with already registered email."""
        response = await async_client.post(
            "/signup",
            data={
                "username": "test@example.com",
                "password": "password123"
            }
        )
        assert response.status_code == 400
        assert "already registered" in response.json()["detail"].lower()

    async def test_login_success(self, async_client: AsyncClient, test_user_token: str):
        """Test successful user login."""
        response = await async_client.post(
            "/login",
            data={
                "username": "test@example.com",
                "password": "testpassword123"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_invalid_credentials(self, async_client: AsyncClient):
        """Test login with invalid credentials."""
        response = await async_client.post(
            "/login",
            data={
                "username": "nonexistent@example.com",
                "password": "wrongpassword"
            }
        )
        assert response.status_code == 400
        assert "invalid credentials" in response.json()["detail"].lower()

    async def test_login_wrong_password(self, async_client: AsyncClient, test_user_token: str):
        """Test login with wrong password."""
        response = await async_client.post(
            "/login",
            data={
                "username": "test@example.com",
                "password": "wrongpassword"
            }
        )
        assert response.status_code == 400
        assert "invalid credentials" in response.json()["detail"].lower()

    async def test_logout(self, async_client: AsyncClient, test_user_token: str):
        """Test user logout."""
        response = await async_client.post(
            "/logout",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == 200
        assert "message" in response.json()

    async def test_create_api_key(self, async_client: AsyncClient, test_user_token: str):
        """Test creating an API key for authenticated user."""
        response = await async_client.put(
            "/users/me/api_keys",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == 201
        data = response.json()
        assert "api_key" in data
        assert "." in data["api_key"]  # API key format: key_id.secret

    async def test_get_api_keys(self, async_client: AsyncClient, test_user_token: str):
        """Test getting all API keys for authenticated user."""
        # First create an API key
        create_response = await async_client.put(
            "/users/me/api_keys",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert create_response.status_code == 201
        
        # Now get all API keys
        response = await async_client.get(
            "/users/me/api_keys",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == 200
        api_keys = response.json()
        assert isinstance(api_keys, list)
        assert len(api_keys) >= 1

    async def test_delete_api_key(self, async_client: AsyncClient, test_user_token: str):
        """Test deleting an API key."""
        # First create an API key
        create_response = await async_client.put(
            "/users/me/api_keys",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert create_response.status_code == 201
        api_key = create_response.json()["api_key"]
        key_id = api_key.split(".")[0]
        
        # Now delete it
        response = await async_client.delete(
            f"/users/me/api_keys/{key_id}",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == 204

    async def test_delete_nonexistent_api_key(self, async_client: AsyncClient, test_user_token: str):
        """Test deleting a non-existent API key."""
        response = await async_client.delete(
            "/users/me/api_keys/nonexistent",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == 404

    async def test_get_users_without_admin(self, async_client: AsyncClient, test_user_token: str):
        """Test getting users list without admin privileges."""
        response = await async_client.get(
            "/users",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == 401

    async def test_update_user_email_without_admin(self, async_client: AsyncClient, test_user_token: str):
        """Test updating user email without admin privileges."""
        response = await async_client.put(
            "/users/1/email?value=newemail@example.com",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == 401

    async def test_update_user_verified_without_admin(self, async_client: AsyncClient, test_user_token: str):
        """Test updating user verified state without admin privileges."""
        response = await async_client.put(
            "/users/1/verified?verified=true",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == 401

    async def test_update_user_role_without_admin(self, async_client: AsyncClient, test_user_token: str):
        """Test updating user role without admin privileges."""
        response = await async_client.put(
            "/users/1/role?role=admin",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == 401

    async def test_authenticated_endpoint_without_token(self, async_client: AsyncClient):
        """Test accessing authenticated endpoint without token."""
        response = await async_client.get("/users/me/api_keys")
        assert response.status_code == 401

    async def test_authenticated_endpoint_with_invalid_token(self, async_client: AsyncClient):
        """Test accessing authenticated endpoint with invalid token."""
        response = await async_client.get(
            "/users/me/api_keys",
            headers={"Authorization": "Bearer invalid_token_here"}
        )
        assert response.status_code == 401
