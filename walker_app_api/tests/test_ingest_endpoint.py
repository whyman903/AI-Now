import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["AGGREGATION_SERVICE_TOKEN"] = "test-token-" + "x" * 32

from app.core import config
from app.db.models import ContentItem

config.settings.AGGREGATION_SERVICE_TOKEN = os.environ["AGGREGATION_SERVICE_TOKEN"]


@pytest.fixture
def client(sessionmaker_fixture):
    from walker_app_api import main
    return TestClient(main.app)


@pytest.fixture
def valid_token():
    return os.environ["AGGREGATION_SERVICE_TOKEN"]


@pytest.fixture
def sample_items():
    return [
        {
            "title": "Claude Opus 4.5 Released",
            "url": "https://www.anthropic.com/research/opus-4-5",
            "author": "Anthropic",
            "published_at": "2025-01-15T10:00:00",
            "thumbnail_url": "https://www.anthropic.com/images/opus.jpg",
            "type": "research_lab",
            "meta_data": {
                "source_name": "Anthropic",
                "extraction_method": "selenium",
                "date_iso": "2025-01-15T10:00:00",
                "date_display": "Jan 15, 2025",
            },
        },
        {
            "title": "GPT-5 Announced",
            "url": "https://openai.com/research/gpt-5",
            "author": "OpenAI",
            "published_at": "2025-01-16T14:30:00",
            "thumbnail_url": "https://openai.com/images/gpt5.png",
            "type": "research_lab",
            "meta_data": {
                "source_name": "OpenAI",
                "extraction_method": "selenium",
            },
        },
    ]


class TestIngestAuthentication:
    def test_ingest_without_token(self, client):
        response = client.post(
            "/api/v1/aggregation/ingest",
            json={"source_key": "scrape_anthropic", "items": []},
        )
        assert response.status_code == 401

    def test_ingest_with_invalid_token(self, client):
        response = client.post(
            "/api/v1/aggregation/ingest",
            json={"source_key": "scrape_anthropic", "items": []},
            headers={"X-Aggregation-Token": "bad-token"},
        )
        assert response.status_code == 401

    def test_ingest_with_valid_token_empty_items(self, client, valid_token):
        response = client.post(
            "/api/v1/aggregation/ingest",
            json={"source_key": "scrape_anthropic", "items": []},
            headers={"X-Aggregation-Token": valid_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["items_added"] == 0
        assert data["items_updated"] == 0


class TestIngestValidation:
    def test_ingest_missing_source_key(self, client, valid_token):
        response = client.post(
            "/api/v1/aggregation/ingest",
            json={"items": []},
            headers={"X-Aggregation-Token": valid_token},
        )
        assert response.status_code == 422

    def test_ingest_missing_required_item_fields(self, client, valid_token):
        response = client.post(
            "/api/v1/aggregation/ingest",
            json={
                "source_key": "scrape_anthropic",
                "items": [{"author": "Anthropic"}],
            },
            headers={"X-Aggregation-Token": valid_token},
        )
        assert response.status_code == 422

    def test_ingest_minimal_item(self, client, valid_token):
        response = client.post(
            "/api/v1/aggregation/ingest",
            json={
                "source_key": "scrape_anthropic",
                "items": [{"title": "Test", "url": "https://example.com/test"}],
            },
            headers={"X-Aggregation-Token": valid_token},
        )
        assert response.status_code == 200
        assert response.json()["items_added"] == 1


class TestIngestPersistence:
    def test_ingest_creates_content_items(self, client, valid_token, sample_items, sessionmaker_fixture):
        response = client.post(
            "/api/v1/aggregation/ingest",
            json={"source_key": "scrape_anthropic", "items": sample_items},
            headers={"X-Aggregation-Token": valid_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["items_added"] == 2
        assert data["source_key"] == "scrape_anthropic"

        with sessionmaker_fixture() as session:
            items = session.query(ContentItem).order_by(ContentItem.title).all()
            assert len(items) == 2
            opus = items[0]
            assert opus.title == "Claude Opus 4.5 Released"
            assert opus.author == "Anthropic"
            assert opus.source_key == "scrape_anthropic"
            assert opus.thumbnail_url == "https://www.anthropic.com/images/opus.jpg"
            assert opus.meta_data["source_name"] == "Anthropic"
            assert opus.meta_data["extraction_method"] == "selenium"

    def test_ingest_deduplicates_by_url(self, client, valid_token, sample_items, sessionmaker_fixture):
        client.post(
            "/api/v1/aggregation/ingest",
            json={"source_key": "scrape_anthropic", "items": sample_items},
            headers={"X-Aggregation-Token": valid_token},
        )

        response = client.post(
            "/api/v1/aggregation/ingest",
            json={"source_key": "scrape_anthropic", "items": sample_items},
            headers={"X-Aggregation-Token": valid_token},
        )
        data = response.json()
        assert data["items_added"] == 0
        assert data["items_updated"] == 2

        with sessionmaker_fixture() as session:
            assert session.query(ContentItem).count() == 2

    def test_ingest_updates_existing_items(self, client, valid_token, sessionmaker_fixture):
        with sessionmaker_fixture() as session:
            session.add(ContentItem(
                id=str(uuid4()),
                type="research_lab",
                title="Old Title",
                url="https://example.com/post",
                published_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
                meta_data={"source_name": "Test"},
            ))
            session.commit()

        updated_item = {
            "title": "New Title",
            "url": "https://example.com/post",
            "author": "New Author",
            "published_at": "2025-01-10T12:00:00",
            "thumbnail_url": "https://example.com/thumb.jpg",
            "type": "research_lab",
            "meta_data": {"source_name": "Test", "extra": "data"},
        }

        response = client.post(
            "/api/v1/aggregation/ingest",
            json={"source_key": "scrape_test", "items": [updated_item]},
            headers={"X-Aggregation-Token": valid_token},
        )
        data = response.json()
        assert data["items_added"] == 0
        assert data["items_updated"] == 1

        with sessionmaker_fixture() as session:
            stored = session.query(ContentItem).one()
            assert stored.author == "New Author"
            assert stored.thumbnail_url == "https://example.com/thumb.jpg"
            assert stored.meta_data["extra"] == "data"
            assert stored.source_key == "scrape_test"

    def test_ingest_parses_iso_datetime_strings(self, client, valid_token, sessionmaker_fixture):
        item = {
            "title": "Date Test",
            "url": "https://example.com/date-test",
            "published_at": "2025-06-15T08:30:00",
            "type": "article",
        }
        response = client.post(
            "/api/v1/aggregation/ingest",
            json={"source_key": "scrape_test", "items": [item]},
            headers={"X-Aggregation-Token": valid_token},
        )
        assert response.status_code == 200

        with sessionmaker_fixture() as session:
            stored = session.query(ContentItem).one()
            assert stored.published_at == datetime(2025, 6, 15, 8, 30, 0)

    def test_ingest_handles_null_optional_fields(self, client, valid_token, sessionmaker_fixture):
        item = {
            "title": "Minimal Item",
            "url": "https://example.com/minimal",
            "author": None,
            "published_at": None,
            "thumbnail_url": None,
            "type": "research_lab",
            "meta_data": None,
        }
        response = client.post(
            "/api/v1/aggregation/ingest",
            json={"source_key": "scrape_test", "items": [item]},
            headers={"X-Aggregation-Token": valid_token},
        )
        assert response.status_code == 200
        assert response.json()["items_added"] == 1

    def test_ingest_strips_tracking_params_from_urls(self, client, valid_token, sessionmaker_fixture):
        item = {
            "title": "Tracked URL",
            "url": "https://example.com/post?utm_source=twitter&utm_medium=social&ref=abc",
            "type": "article",
        }
        response = client.post(
            "/api/v1/aggregation/ingest",
            json={"source_key": "scrape_test", "items": [item]},
            headers={"X-Aggregation-Token": valid_token},
        )
        assert response.status_code == 200

        with sessionmaker_fixture() as session:
            stored = session.query(ContentItem).one()
            assert "utm_source" not in stored.url
            assert "ref=" not in stored.url


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
