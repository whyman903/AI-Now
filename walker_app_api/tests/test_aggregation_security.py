"""
Tests for aggregation endpoint security (token authentication).
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
import os

# Must set environment variables before importing the app
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["AGGREGATION_SERVICE_TOKEN"] = "test-token-" + "x" * 32

from walker_app_api.main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def valid_token():
    """Return the valid test token."""
    return os.environ["AGGREGATION_SERVICE_TOKEN"]


class TestAggregationAuthentication:
    """Test authentication for aggregation endpoints."""

    def test_trigger_aggregation_without_token(self, client):
        """Should return 401 when token is missing."""
        response = client.post("/api/v1/aggregation/trigger")
        assert response.status_code == 401
        assert "authentication" in response.json()["detail"].lower()

    def test_trigger_aggregation_with_invalid_token(self, client):
        """Should return 401 when token is invalid."""
        response = client.post(
            "/api/v1/aggregation/trigger",
            headers={"X-Aggregation-Token": "invalid-token"}
        )
        assert response.status_code == 401
        assert "authentication" in response.json()["detail"].lower()

    def test_trigger_aggregation_with_valid_token(self, client, valid_token):
        """Should return 200 when token is valid."""
        with patch('app.services.content_aggregator.ContentAggregator.aggregate_all_content'):
            response = client.post(
                "/api/v1/aggregation/trigger",
                headers={"X-Aggregation-Token": valid_token}
            )
            assert response.status_code == 200
            assert response.json()["status"] == "triggered"

    def test_aggregate_now_without_token(self, client):
        """Should return 401 when token is missing."""
        response = client.post("/api/v1/aggregation/aggregate-now")
        assert response.status_code == 401

    def test_sources_refresh_without_token(self, client):
        """Should return 401 when token is missing."""
        response = client.post("/api/v1/items/sources/refresh/test-source")
        assert response.status_code == 401


class TestTokenValidation:
    """Test token validation logic."""

    def test_short_token_rejected(self):
        """Should reject tokens shorter than minimum length."""
        from app.api.deps import _valid_tokens
        from app.core.config import settings
        
        original_token = settings.AGGREGATION_SERVICE_TOKEN
        try:
            settings.AGGREGATION_SERVICE_TOKEN = "short"
            with pytest.raises(ValueError, match="at least"):
                _valid_tokens()
        finally:
            settings.AGGREGATION_SERVICE_TOKEN = original_token

    def test_token_rotation_support(self):
        """Should accept both primary and secondary tokens."""
        from app.api.deps import _valid_tokens
        from app.core.config import settings
        
        original_primary = settings.AGGREGATION_SERVICE_TOKEN
        original_secondary = settings.AGGREGATION_SERVICE_TOKEN_NEXT
        
        try:
            settings.AGGREGATION_SERVICE_TOKEN = "primary-token-" + "x" * 32
            settings.AGGREGATION_SERVICE_TOKEN_NEXT = "secondary-token-" + "x" * 32
            
            tokens = _valid_tokens()
            assert len(tokens) == 2
            assert settings.AGGREGATION_SERVICE_TOKEN in tokens
            assert settings.AGGREGATION_SERVICE_TOKEN_NEXT in tokens
        finally:
            settings.AGGREGATION_SERVICE_TOKEN = original_primary
            settings.AGGREGATION_SERVICE_TOKEN_NEXT = original_secondary


class TestHealthCheck:
    """Test health check endpoint."""

    def test_health_check_returns_status(self, client):
        """Should return health status for all services."""
        response = client.get("/health")
        assert response.status_code in [200, 503]
        data = response.json()
        assert "status" in data
        assert "services" in data
        assert "api" in data["services"]
        assert "database" in data["services"]


class TestProductionScenarios:
    """Integration tests for production scenarios."""

    def test_unauthenticated_endpoints_work(self, client):
        """Should allow access to public endpoints without token."""
        response = client.get("/")
        assert response.status_code == 200
        
        response = client.get("/health")
        assert response.status_code in [200, 503]
        
        response = client.get("/api/v1/aggregation/status")
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
