"""
Tests for root and health check endpoints.
Verifies structured APIResponse format, status codes, and non-authentication behavior.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.anyio
async def test_root_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        json_data = response.json()
        assert json_data["success"] is True
        assert json_data["status_code"] == 200
        assert "Welcome to InfoScope AI API" in json_data["message"]
        assert json_data["data"]["service"] == "InfoScope AI"
        assert json_data["data"]["version"] == "0.1.0"
        assert json_data["data"]["health_url"] == "/api/v1/health"


@pytest.mark.anyio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        json_data = response.json()
        assert json_data["success"] is True
        assert json_data["status_code"] == 200
        assert json_data["message"] == "InfoScope AI backend is operational."
        assert json_data["data"]["status"] == "healthy"
        assert json_data["data"]["service"] == "InfoScope AI"
        assert "uptime_seconds" in json_data["data"]
        assert json_data["data"]["uptime_seconds"] >= 0


@pytest.mark.anyio
async def test_protected_research_without_auth_fails():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/research/sessions")
        # Should return 401 Unauthorized because valid JWT Bearer token is required
        assert response.status_code == 401
        json_data = response.json()
        assert json_data["success"] is False
        assert "credentials were not provided" in json_data["message"]
