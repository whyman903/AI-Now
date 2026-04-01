from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.crud.analytics import AnalyticsCRUD
from app.db.models import ContentInteraction, ContentItem, SearchQuery

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class DummyAggregator:
    def __init__(self):
        self.rss_sources = []
        self.youtube_channels = []
        self.web_scraper_sources = []
        self.aggregate_all_content = AsyncMock(return_value={"total_new_items": 0, "sources": {}})

    def configure(self, low_memory: bool = False):
        self.low_memory_mode = low_memory

    def set_http_client(self, client):
        self.client = client


@pytest.fixture
def api_client(sessionmaker_fixture, analytics_queue_stub, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from app.api.v1.endpoints import items as items_module
    from app.services.aggregation import aggregator as agg_module
    from app.crud import analytics as analytics_crud
    from walker_app_api import main

    dummy = DummyAggregator()
    monkeypatch.setattr(agg_module, "get_content_aggregator", lambda: dummy)
    items_module.aggregator = dummy
    monkeypatch.setattr(
        analytics_crud.AnalyticsCRUD,
        "get_interaction_timeline",
        staticmethod(lambda db, hours_back=24, bucket_minutes=60: [
            {"timestamp": None, "interaction_type": "click", "count": 0}
        ]),
    )

    return TestClient(main.app)


VALID_ORIGIN_HEADERS = {"origin": "https://ai-now.vercel.app"}


def test_track_events_through_queue(api_client: TestClient, analytics_queue_stub):
    interaction = api_client.post(
        "/api/v1/analytics/track/interaction",
        json={"content_id": "abc", "interaction_type": "click", "session_id": "s1"},
        headers={**VALID_ORIGIN_HEADERS, "user-agent": "pytest"},
    )
    assert interaction.status_code == 200
    assert len(analytics_queue_stub["interactions"]) == 1

    batch = api_client.post(
        "/api/v1/analytics/track/interactions/batch",
        json={
            "interactions": [
                {"content_id": "abc", "interaction_type": "view", "session_id": "s1"},
                {"content_id": "def", "interaction_type": "click", "session_id": "s1"},
            ]
        },
        headers=VALID_ORIGIN_HEADERS,
    )
    assert batch.status_code == 200
    assert batch.json()["count"] == 2
    assert len(analytics_queue_stub["interactions"]) == 3

    search = api_client.post(
        "/api/v1/analytics/track/search",
        json={"query": "ai", "results_count": 10, "session_id": "s1"},
        headers=VALID_ORIGIN_HEADERS,
    )
    assert search.status_code == 200
    assert len(analytics_queue_stub["searches"]) == 1

    search_batch = api_client.post(
        "/api/v1/analytics/track/searches/batch",
        json={"searches": [{"query": "llms", "session_id": "s1"}, {"query": "agents", "session_id": "s2"}]},
        headers=VALID_ORIGIN_HEADERS,
    )
    assert search_batch.status_code == 200
    assert search_batch.json()["count"] == 2
    assert len(analytics_queue_stub["searches"]) == 3

    click = api_client.post(
        "/api/v1/analytics/track/search-click",
        json={"search_id": "search-1", "clicked_result_id": "res-1", "clicked_position": 1},
        headers=VALID_ORIGIN_HEADERS,
    )
    assert click.status_code == 200

    click_batch = api_client.post(
        "/api/v1/analytics/track/search-click/batch",
        json={
            "updates": [
                {"search_id": "search-1", "clicked_result_id": "r1"},
                {"search_id": "search-2", "clicked_result_id": "r2", "clicked_position": 2},
            ]
        },
        headers=VALID_ORIGIN_HEADERS,
    )
    assert click_batch.status_code == 200
    assert click_batch.json()["updated_count"] == 2
    assert len(analytics_queue_stub["clicks"]) == 3


def test_analytics_blocked_without_valid_origin(api_client: TestClient, analytics_queue_stub):
    """Requests without a valid Origin/Referer are rejected with 403."""
    # No origin at all
    resp = api_client.post(
        "/api/v1/analytics/track/interaction",
        json={"content_id": "abc", "interaction_type": "click", "session_id": "s1"},
    )
    assert resp.status_code == 403

    # Wrong origin
    resp = api_client.post(
        "/api/v1/analytics/track/interaction",
        json={"content_id": "abc", "interaction_type": "click", "session_id": "s1"},
        headers={"origin": "https://evil.com"},
    )
    assert resp.status_code == 403

    # Wrong referer
    resp = api_client.post(
        "/api/v1/analytics/session",
        json={"session_id": "s1"},
        headers={"referer": "https://evil.com/page"},
    )
    assert resp.status_code == 403

    # Valid referer works
    resp = api_client.post(
        "/api/v1/analytics/session",
        json={"session_id": "s1"},
        headers={"referer": "https://ai-now.vercel.app/dashboard"},
    )
    assert resp.status_code == 200

    # Localhost origin works (dev)
    resp = api_client.post(
        "/api/v1/analytics/track/interaction",
        json={"content_id": "abc", "interaction_type": "click", "session_id": "s1"},
        headers={"origin": "http://localhost:5173"},
    )
    assert resp.status_code == 200

    # Nothing was enqueued from the rejected requests
    assert len(analytics_queue_stub["interactions"]) == 1


def test_session_id_required_on_tracking(api_client: TestClient, analytics_queue_stub):
    """session_id is now required on interaction and search payloads."""
    # Missing session_id on interaction
    resp = api_client.post(
        "/api/v1/analytics/track/interaction",
        json={"content_id": "abc", "interaction_type": "click"},
        headers=VALID_ORIGIN_HEADERS,
    )
    assert resp.status_code == 422

    # Missing session_id on search
    resp = api_client.post(
        "/api/v1/analytics/track/search",
        json={"query": "test"},
        headers=VALID_ORIGIN_HEADERS,
    )
    assert resp.status_code == 422

    # Missing session_id in batch item
    resp = api_client.post(
        "/api/v1/analytics/track/interactions/batch",
        json={"interactions": [{"content_id": "abc", "interaction_type": "click"}]},
        headers=VALID_ORIGIN_HEADERS,
    )
    assert resp.status_code == 422


def test_analytics_reporting_endpoints(api_client: TestClient, sessionmaker_fixture):
    now = datetime.now(timezone.utc)
    with sessionmaker_fixture() as session:
        item = ContentItem(
            id="item-1",
            type="article",
            title="A great post",
            url="https://example.com/post",
            author="OpenAI",
            published_at=now - timedelta(hours=1),
            clicks=0,
        )
        session.add(item)
        session.commit()

        AnalyticsCRUD.batch_track_interactions(
            session,
            events=[
                {"content_id": item.id, "interaction_type": "click", "timestamp": now.isoformat()},
                {"content_id": item.id, "interaction_type": "view", "timestamp": (now - timedelta(minutes=10)).isoformat()},
            ],
        )
        AnalyticsCRUD.batch_track_searches(
            session,
            searches=[
                {"search_id": "search-1", "query": "ai now", "results_count": 5, "timestamp": now.isoformat()},
                {"search_id": "search-2", "query": "ai now", "results_count": 3, "timestamp": now.isoformat()},
            ],
        )
        AnalyticsCRUD.batch_update_search_clicks(
            session,
            updates=[{"search_id": "search-1", "clicked_result_id": "c1", "clicked_position": 1}],
        )

    content_stats = api_client.get("/api/v1/analytics/content/item-1", params={"days_back": 7})
    assert content_stats.status_code == 200
    body = content_stats.json()
    assert body["total_interactions"] == 2
    assert body["interactions_by_type"]["click"] == 1
    assert body["total_clicks"] == 1

    trending = api_client.get("/api/v1/analytics/trending", params={"hours_back": 24, "limit": 5})
    assert trending.status_code == 200
    assert trending.json()["results"][0]["interaction_count"] == 2

    popular_searches = api_client.get("/api/v1/analytics/popular-searches", params={"days_back": 7, "limit": 10})
    assert popular_searches.status_code == 200
    top_query = popular_searches.json()["results"][0]
    assert top_query["query"] == "ai now"
    assert top_query["search_count"] == 2
    assert top_query["click_count"] == 1

    session_stats = api_client.get("/api/v1/analytics/session-stats", params={"days_back": 7})
    assert session_stats.status_code == 200

    timeline = api_client.get("/api/v1/analytics/timeline", params={"hours_back": 24, "bucket_minutes": 60})
    assert timeline.status_code == 200
