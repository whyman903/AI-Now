from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core import config
from app.db.models import ContentItem

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class DummyAggregator:
    def __init__(self):
        self.rss_sources = [{"name": "Sequoia Capital", "source_key": "rss_sequoia_capital", "category": "venture"}]
        self.youtube_channels = [{"name": "OpenAI", "source_key": "yt_openai", "category": "frontier_model"}]
        self.web_scraper_sources = [
            {"name": "Qwen", "source_key": "scrape_qwen", "category": "frontier_model"},
            {"name": "Google DeepMind", "source_key": "scrape_google_deepmind", "category": "frontier_model"},
        ]
        self.aggregate_all_content = AsyncMock(
            return_value={
                "total_new_items": 2,
                "total_items_updated": 1,
                "items_with_thumbnails": 1,
                "sources": {},
            }
        )
        self.low_memory_mode = False

    def configure(self, low_memory: bool = False):
        self.low_memory_mode = low_memory

    def set_http_client(self, client):
        self.client = client


@pytest.fixture
def api_client(sessionmaker_fixture, analytics_queue_stub, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from app.services.aggregation import aggregator as new_agg_module
    from walker_app_api import main

    dummy = DummyAggregator()
    monkeypatch.setattr(new_agg_module, "get_content_aggregator", lambda: dummy)

    # Ensure token-dependent routes accept our header
    monkeypatch.setattr(config.settings, "AGGREGATION_SERVICE_TOKEN", "valid-token-" + "x" * 32)

    client = TestClient(main.app)
    return client


def _seed_content(session_factory, published_at: datetime) -> list[str]:
    ids = []
    with session_factory() as session:
        items = [
            ContentItem(
                type="article",
                title="Qwen launch",
                url="https://qwen.ai/blog",
                author="Qwen",
                published_at=published_at,
                thumbnail_url="images/qwen.png",
                meta_data={"source_name": "Qwen"},
            ),
            ContentItem(
                type="youtube_video",
                title="OpenAI demo",
                url="https://youtube.com/watch?v=123",
                author="OpenAI",
                published_at=published_at - timedelta(hours=1),
                thumbnail_url="https://img.youtube.com/demo.jpg",
                meta_data={},
            ),
            ContentItem(
                type="research_paper",
                title="HF paper A",
                url="https://hf.co/paper/a",
                author="Hugging Face Papers",
                published_at=published_at - timedelta(days=1),
                thumbnail_url=None,
                meta_data={"rank": 2, "scraped_date": "2024-05-02T00:00:00"},
            ),
            ContentItem(
                type="research_paper",
                title="HF paper B",
                url="https://hf.co/paper/b",
                author="Hugging Face Papers",
                published_at=published_at - timedelta(days=2),
                thumbnail_url=None,
                meta_data={"rank": 1, "scraped_date": "2024-05-03T00:00:00"},
            ),
        ]
        session.add_all(items)
        session.commit()
        ids = [item.id for item in items]
    return ids


def test_get_content_filters_and_serializes(api_client: TestClient, sessionmaker_fixture, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config.settings, "PUBLIC_BASE_URL", "https://cdn.example.com")
    now = datetime.now(timezone.utc)
    ids = _seed_content(sessionmaker_fixture, now)

    response = api_client.get(
        "/api/v1/content",
        params={
            "limit": 5,
            "source_keys": ["scrape_qwen"],
            "types": ["article"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["sourceKey"] == "scrape_qwen"
    assert item["thumbnailUrl"] == "https://cdn.example.com/images/qwen.png"
    assert item["url"] == "https://qwen.ai/blog"
    assert item["publishedAt"].endswith("Z")

    # Research papers should be ordered by scraped_date then rank
    papers = api_client.get(
        "/api/v1/content",
        params={"content_type": "research_paper", "order": "recent", "limit": 2},
    ).json()["items"]
    assert [p["title"] for p in papers] == ["HF paper B", "HF paper A"]

    # Item lookup by id
    detail = api_client.get(f"/api/v1/content/{ids[1]}")
    assert detail.status_code == 200
    assert detail.json()["id"] == ids[1]

    missing = api_client.get("/api/v1/content/nonexistent")
    assert missing.status_code == 404


def test_content_types_and_trending(api_client: TestClient, sessionmaker_fixture):
    now = datetime.now(timezone.utc)
    _seed_content(sessionmaker_fixture, now)

    # Trending filters by published_at within window
    recent = api_client.get("/api/v1/content/trending", params={"hours": 2, "limit": 10})
    assert recent.status_code == 200
    assert len(recent.json()["items"]) == 2  # article + video inside window

    types_resp = api_client.get("/api/v1/content/types")
    assert types_resp.status_code == 200
    assert set(types_resp.json()["types"]) >= {"article", "youtube_video", "research_paper"}


def test_source_endpoints_and_refresh(api_client: TestClient, sessionmaker_fixture):
    from app.services.aggregation.registry import get_all_plugins

    sources = api_client.get("/api/v1/sources")
    assert sources.status_code == 200
    assert sources.json()["total"] >= 1

    status = api_client.get("/api/v1/sources/status")
    assert status.status_code == 200
    assert status.json()["sources"] == len(get_all_plugins())

    labs = api_client.get("/api/v1/sources/filters/labs")
    assert labs.status_code == 200
    assert any(lab["sourceKey"] == "scrape_qwen" for lab in labs.json()["labs"])

    refresh = api_client.post(
        "/api/v1/sources/refresh/qwen",
        headers={"X-Aggregation-Token": config.settings.AGGREGATION_SERVICE_TOKEN},
    )
    assert refresh.status_code == 200
    assert refresh.json()["status"] == "success"
