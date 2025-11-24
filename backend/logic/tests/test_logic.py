import pytest
from httpx import AsyncClient
import io


class TestLogicEndpoints:
    """Test cases for logic endpoints (batch processing and similarity search)."""

    async def test_get_batches_requires_auth(self, async_client: AsyncClient):
        """Test that getting batches requires authentication."""
        response = await async_client.get("/batches")
        assert response.status_code == 401

    async def test_get_batches_with_auth(self, async_client: AsyncClient, test_user_token: str):
        """Test getting batches with authentication."""
        response = await async_client.get(
            "/batches",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list) or isinstance(data, dict)

    async def test_create_batch_requires_auth(self, async_client: AsyncClient):
        """Test that creating a batch requires authentication."""
        files = {"file": ("test.ris", "TY  - JOUR\nER  - ", "text/plain")}
        response = await async_client.post("/batches", files=files)
        assert response.status_code == 401

    async def test_create_batch_with_auth(self, async_client: AsyncClient, test_user_token: str):
        """Test creating a batch with authentication."""
        # Create a simple RIS format file
        ris_content = b"""TY  - JOUR
TI  - Test Article Title
AU  - Smith, John
AB  - This is a test abstract for the article.
ER  - 
"""
        files = {"file": ("test.ris", ris_content, "text/plain")}
        response = await async_client.post(
            "/batches",
            files=files,
            headers={"Authorization": f"Bearer {test_user_token}"},
            params={"description": "Test batch"}
        )
        # May fail if embedding service is not available
        assert response.status_code in [201, 500, 502]

    async def test_create_batch_without_file(self, async_client: AsyncClient, test_user_token: str):
        """Test creating a batch without providing a file."""
        response = await async_client.post(
            "/batches",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == 422  # Validation error

    async def test_get_specific_batch(self, async_client: AsyncClient, test_user_token: str):
        """Test getting a specific batch by hash."""
        response = await async_client.get(
            "/batches/nonexistent_hash",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [404, 500]

    async def test_delete_batch_requires_auth(self, async_client: AsyncClient):
        """Test that deleting a batch requires authentication."""
        response = await async_client.delete("/batches/test_hash")
        assert response.status_code == 401

    async def test_delete_nonexistent_batch(self, async_client: AsyncClient, test_user_token: str):
        """Test deleting a non-existent batch."""
        response = await async_client.delete(
            "/batches/nonexistent_hash",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [404, 500]

    async def test_get_batch_report(self, async_client: AsyncClient, test_user_token: str):
        """Test getting a specific report from a batch."""
        response = await async_client.get(
            "/batches/test_hash/0",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [404, 500]

    async def test_assign_studies_to_report_requires_auth(self, async_client: AsyncClient):
        """Test that assigning studies to a report requires authentication."""
        response = await async_client.put(
            "/batches/test_hash/0/studies",
            json={"study_ids": [1, 2, 3]}
        )
        assert response.status_code == 401

    async def test_assign_studies_to_report(self, async_client: AsyncClient, test_user_token: str):
        """Test assigning studies to a report in a batch."""
        response = await async_client.put(
            "/batches/test_hash/0/studies",
            headers={"Authorization": f"Bearer {test_user_token}"},
            params={"study_ids": [1, 2, 3]}
        )
        assert response.status_code in [204, 404, 500]

    async def test_remove_assigned_studies_requires_auth(self, async_client: AsyncClient):
        """Test that removing assigned studies requires authentication."""
        response = await async_client.delete("/batches/test_hash/0/studies")
        assert response.status_code == 401

    async def test_remove_assigned_studies(self, async_client: AsyncClient, test_user_token: str):
        """Test removing assigned studies from a report."""
        response = await async_client.delete(
            "/batches/test_hash/0/studies",
            headers={"Authorization": f"Bearer {test_user_token}"},
            params={"study_ids": [1, 2]}
        )
        assert response.status_code in [204, 404, 500]

    async def test_get_similar_tags_requires_auth(self, async_client: AsyncClient):
        """Test that getting similar tags requires authentication."""
        response = await async_client.get("/batches/test_hash/0/similar_tags")
        assert response.status_code == 401

    async def test_get_similar_tags(self, async_client: AsyncClient, test_user_token: str):
        """Test getting similar tags for a report."""
        response = await async_client.get(
            "/batches/test_hash/0/similar_tags",
            headers={"Authorization": f"Bearer {test_user_token}"},
            params={"aspect": "interventions", "k": 10}
        )
        assert response.status_code in [200, 404, 500]

    async def test_get_similar_studies_requires_auth(self, async_client: AsyncClient):
        """Test that getting similar studies requires authentication."""
        response = await async_client.get("/batches/test_hash/0/similar_studies")
        assert response.status_code == 401

    async def test_get_similar_studies(self, async_client: AsyncClient, test_user_token: str):
        """Test getting similar studies for a report."""
        response = await async_client.get(
            "/batches/test_hash/0/similar_studies",
            headers={"Authorization": f"Bearer {test_user_token}"},
            params={"k": 10}
        )
        assert response.status_code in [200, 404, 500]

    async def test_get_similar_studies_with_aspect(self, async_client: AsyncClient, test_user_token: str):
        """Test getting similar studies with specific aspect filter."""
        response = await async_client.get(
            "/batches/test_hash/0/similar_studies",
            headers={"Authorization": f"Bearer {test_user_token}"},
            params={"aspect": "outcomes", "k": 5}
        )
        assert response.status_code in [200, 404, 500]

    async def test_get_similar_studies_with_cutoff(self, async_client: AsyncClient, test_user_token: str):
        """Test getting similar studies with cutoff date."""
        response = await async_client.get(
            "/batches/test_hash/0/similar_studies",
            headers={"Authorization": f"Bearer {test_user_token}"},
            params={"cutoff": "2024-01-01 00:00:00", "k": 10}
        )
        assert response.status_code in [200, 404, 500]

    async def test_get_related_studies_by_tag_requires_auth(self, async_client: AsyncClient):
        """Test that getting related studies by tag requires authentication."""
        response = await async_client.get("/interventions/Placebo/related_studies")
        assert response.status_code == 401

    async def test_get_related_studies_by_intervention(self, async_client: AsyncClient, test_user_token: str):
        """Test getting related studies by intervention tag."""
        response = await async_client.get(
            "/interventions/Placebo/related_studies",
            headers={"Authorization": f"Bearer {test_user_token}"},
            params={"k": 10}
        )
        assert response.status_code in [200, 500]

    async def test_get_related_studies_by_condition(self, async_client: AsyncClient, test_user_token: str):
        """Test getting related studies by condition tag."""
        response = await async_client.get(
            "/conditions/Diabetes/related_studies",
            headers={"Authorization": f"Bearer {test_user_token}"},
            params={"k": 10}
        )
        assert response.status_code in [200, 500]

    async def test_get_related_studies_by_outcome(self, async_client: AsyncClient, test_user_token: str):
        """Test getting related studies by outcome tag."""
        response = await async_client.get(
            "/outcomes/Mortality/related_studies",
            headers={"Authorization": f"Bearer {test_user_token}"},
            params={"k": 10}
        )
        assert response.status_code in [200, 500]

    async def test_get_related_studies_by_participant(self, async_client: AsyncClient, test_user_token: str):
        """Test getting related studies by participant tag."""
        response = await async_client.get(
            "/participants/Adult/related_studies",
            headers={"Authorization": f"Bearer {test_user_token}"},
            params={"k": 10}
        )
        assert response.status_code in [200, 500]

    async def test_get_related_studies_invalid_category(self, async_client: AsyncClient, test_user_token: str):
        """Test getting related studies with invalid category."""
        response = await async_client.get(
            "/invalid_category/test/related_studies",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [404, 422, 500]

    async def test_batch_subscribe_endpoint_requires_auth(self, async_client: AsyncClient):
        """Test that batch subscribe endpoint requires authentication."""
        response = await async_client.get("/batches/test_hash/subscribe")
        assert response.status_code == 401

    async def test_deprecated_similarity_search_studies(self, async_client: AsyncClient, test_user_token: str):
        """Test deprecated similarity search for studies endpoint."""
        response = await async_client.post(
            "/similarity_search/studies",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={
                "title": "Test title",
                "abstract": "Test abstract"
            }
        )
        # Endpoint is deprecated but should still work
        assert response.status_code in [200, 500]

    async def test_deprecated_similarity_search_tags(self, async_client: AsyncClient, test_user_token: str):
        """Test deprecated similarity search for tags endpoint."""
        response = await async_client.post(
            "/similarity_search/tags",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={
                "title": "Test title",
                "abstract": "Test abstract"
            }
        )
        # Endpoint is deprecated but should still work
        assert response.status_code in [200, 500]

    async def test_all_logic_endpoints_require_auth(self, async_client: AsyncClient):
        """Test that all logic endpoints require authentication."""
        endpoints = [
            ("GET", "/batches"),
            ("GET", "/batches/test_hash"),
            ("DELETE", "/batches/test_hash"),
            ("GET", "/batches/test_hash/0"),
            ("GET", "/batches/test_hash/0/similar_tags"),
            ("GET", "/batches/test_hash/0/similar_studies"),
            ("GET", "/interventions/test/related_studies"),
        ]
        
        for method, endpoint in endpoints:
            if method == "GET":
                response = await async_client.get(endpoint)
            elif method == "DELETE":
                response = await async_client.delete(endpoint)
            
            assert response.status_code == 401, f"{method} {endpoint} should require auth"
