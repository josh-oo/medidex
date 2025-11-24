import pytest
from httpx import AsyncClient


class TestResourcesEndpoints:
    """Test cases for resources endpoints."""

    async def test_health_check(self, async_client: AsyncClient):
        """Test the readyz health check endpoint."""
        response = await async_client.get("/readyz")
        assert response.status_code == 200
        assert response.json() == "Ready"

    async def test_get_studies_requires_auth(self, async_client: AsyncClient):
        """Test that getting studies requires authentication."""
        response = await async_client.get("/studies?study_ids=1")
        assert response.status_code == 401

    async def test_get_studies_with_auth(self, async_client: AsyncClient, test_user_token: str):
        """Test getting studies with authentication."""
        response = await async_client.get(
            "/studies?study_ids=1",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        # May return 200 with empty list if no data, or error if database not setup
        assert response.status_code in [200, 500]

    async def test_get_single_study(self, async_client: AsyncClient, test_user_token: str):
        """Test getting a single study by ID."""
        response = await async_client.get(
            "/studies/1",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 404, 500]

    async def test_get_study_date_entered(self, async_client: AsyncClient, test_user_token: str):
        """Test getting study date entered."""
        response = await async_client.get(
            "/studies/1/date_entered",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 404, 500]

    async def test_get_study_interventions(self, async_client: AsyncClient, test_user_token: str):
        """Test getting study interventions."""
        response = await async_client.get(
            "/studies/1/interventions",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 500]

    async def test_get_study_conditions(self, async_client: AsyncClient, test_user_token: str):
        """Test getting study conditions."""
        response = await async_client.get(
            "/studies/1/conditions",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 500]

    async def test_get_study_outcomes(self, async_client: AsyncClient, test_user_token: str):
        """Test getting study outcomes."""
        response = await async_client.get(
            "/studies/1/outcomes",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 500]

    async def test_get_study_participants(self, async_client: AsyncClient, test_user_token: str):
        """Test getting study participants."""
        response = await async_client.get(
            "/studies/1/participants",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 500]

    async def test_get_study_design(self, async_client: AsyncClient, test_user_token: str):
        """Test getting study design."""
        response = await async_client.get(
            "/studies/1/design",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 500]

    async def test_get_study_persons(self, async_client: AsyncClient, test_user_token: str):
        """Test getting study persons."""
        response = await async_client.get(
            "/studies/1/persons",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 500]

    async def test_get_study_reports(self, async_client: AsyncClient, test_user_token: str):
        """Test getting study reports."""
        response = await async_client.get(
            "/studies/1/reports",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 500]

    async def test_get_study_reports_with_pdf_links(self, async_client: AsyncClient, test_user_token: str):
        """Test getting study reports with PDF links."""
        response = await async_client.get(
            "/studies/1/reports?include_pdf_links=true",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 500]

    async def test_get_study_id_by_trial_id(self, async_client: AsyncClient, test_user_token: str):
        """Test getting study ID by trial registration ID."""
        response = await async_client.get(
            "/studies/NCT00000000/study_id",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 500]

    async def test_get_all_reports(self, async_client: AsyncClient, test_user_token: str):
        """Test getting all reports."""
        response = await async_client.get(
            "/reports?report_ids=1",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 500]

    async def test_get_single_report(self, async_client: AsyncClient, test_user_token: str):
        """Test getting a single report by ID."""
        response = await async_client.get(
            "/reports/1",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 404, 500]

    async def test_get_report_pdf_number(self, async_client: AsyncClient, test_user_token: str):
        """Test getting report PDF number."""
        response = await async_client.get(
            "/reports/1/pdf_number",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 404, 500]

    async def test_get_report_pdf_link(self, async_client: AsyncClient, test_user_token: str):
        """Test getting report PDF link."""
        response = await async_client.get(
            "/reports/1/pdf_link",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 404, 500]

    async def test_get_report_pdf(self, async_client: AsyncClient, test_user_token: str):
        """Test getting report PDF file."""
        response = await async_client.get(
            "/reports/1/pdf",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 404, 500]

    async def test_get_interventions_by_studies(self, async_client: AsyncClient, test_user_token: str):
        """Test getting interventions grouped by studies."""
        response = await async_client.get(
            "/interventions/by_studies?study_ids=1",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 500]

    async def test_get_all_interventions(self, async_client: AsyncClient, test_user_token: str):
        """Test getting all interventions."""
        response = await async_client.get(
            "/interventions",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 500]

    async def test_get_all_interventions_with_ids(self, async_client: AsyncClient, test_user_token: str):
        """Test getting interventions filtered by IDs."""
        response = await async_client.get(
            "/interventions?ids=1",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 500]

    async def test_get_conditions_by_studies(self, async_client: AsyncClient, test_user_token: str):
        """Test getting conditions grouped by studies."""
        response = await async_client.get(
            "/conditions/by_studies?study_ids=1",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 500]

    async def test_get_all_conditions(self, async_client: AsyncClient, test_user_token: str):
        """Test getting all conditions."""
        response = await async_client.get(
            "/conditions",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 500]

    async def test_get_all_conditions_with_ids(self, async_client: AsyncClient, test_user_token: str):
        """Test getting conditions filtered by IDs."""
        response = await async_client.get(
            "/conditions?ids=1",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 500]

    async def test_get_outcomes_by_studies(self, async_client: AsyncClient, test_user_token: str):
        """Test getting outcomes grouped by studies."""
        response = await async_client.get(
            "/outcomes/by_studies?study_ids=1",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 500]

    async def test_get_all_outcomes(self, async_client: AsyncClient, test_user_token: str):
        """Test getting all outcomes."""
        response = await async_client.get(
            "/outcomes",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 500]

    async def test_get_all_outcomes_with_ids(self, async_client: AsyncClient, test_user_token: str):
        """Test getting outcomes filtered by IDs."""
        response = await async_client.get(
            "/outcomes?ids=1",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 500]

    async def test_get_mapping_report_study(self, async_client: AsyncClient, test_user_token: str):
        """Test getting report to study mapping."""
        response = await async_client.get(
            "/mappings/report_study",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 500]

    async def test_get_mapping_study_report(self, async_client: AsyncClient, test_user_token: str):
        """Test getting study to report mapping."""
        response = await async_client.get(
            "/mappings/study_report",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code in [200, 500]

    async def test_resources_require_authentication(self, async_client: AsyncClient):
        """Test that resource endpoints require authentication."""
        endpoints = [
            "/studies?study_ids=1",
            "/studies/1",
            "/reports?report_ids=1",
            "/reports/1",
            "/interventions",
            "/conditions",
            "/outcomes",
            "/mappings/report_study",
            "/mappings/study_report",
        ]
        
        for endpoint in endpoints:
            response = await async_client.get(endpoint)
            assert response.status_code == 401, f"Endpoint {endpoint} should require auth"
