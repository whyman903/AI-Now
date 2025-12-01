import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

# Ensure the backend package is importable when tests are run from the repo root
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Configure an in-memory default for settings before importing application code
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

# Patch create_engine before the application modules import it so SQLite accepts
# the pool-related keyword arguments that are tuned for Postgres in production.
_original_create_engine = sa.create_engine


def _safe_create_engine(*args, **kwargs):
    url = args[0] if args else kwargs.get("url", "")
    if isinstance(url, str) and url.startswith("sqlite"):
        kwargs.pop("pool_size", None)
        kwargs.pop("max_overflow", None)
        kwargs.pop("pool_timeout", None)
    return _original_create_engine(*args, **kwargs)


sa.create_engine = _safe_create_engine

from app.db import base  # noqa: E402
from app.db.models import ContentItem, FeedState  # noqa: E402
from app.services import content_aggregator  # noqa: E402
from app.services.content_aggregator import ContentAggregator  # noqa: E402

# Restore the original engine factory for test fixtures
sa.create_engine = _original_create_engine


@pytest.fixture
def db_session_factory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Generator[sessionmaker, None, None]:
    """Provide a SQLite-backed session factory wired into the aggregator module."""

    db_file = tmp_path / "test.db"
    engine = sa.create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )

    # Provide gen_random_uuid() for SQLite to mirror Postgres defaults
    def _install_functions(dbapi_connection, connection_record):
        dbapi_connection.create_function("gen_random_uuid", 0, lambda: str(uuid4()))

    sa.event.listen(engine, "connect", _install_functions)

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Create only the tables needed for aggregator persistence tests
    for table in (ContentItem.__table__, FeedState.__table__):
        table.drop(bind=engine, checkfirst=True)
        table.create(bind=engine)
    monkeypatch.setattr(base, "engine", engine)
    monkeypatch.setattr(base, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(content_aggregator, "SessionLocal", TestingSessionLocal)

    yield TestingSessionLocal

    engine.dispose()


@pytest.fixture
def aggregator(monkeypatch: pytest.MonkeyPatch, db_session_factory: sessionmaker, tmp_path: Path) -> ContentAggregator:
    """Create a fresh aggregator instance with isolated caches and patched thumbnail extraction."""

    agg = ContentAggregator()
    
    thumb_mock = AsyncMock(return_value="http://thumbs.local/example.jpg")
    monkeypatch.setattr(agg, "_extract_thumbnail", thumb_mock)
    return agg


def test_canonicalize_strips_tracking_and_normalizes(aggregator: ContentAggregator):
    url = "https://Example.COM:443/path/to/post/?utm_source=newsletter&ref=abc#section"
    assert aggregator.canonicalize(url) == "https://example.com/path/to/post"


def test_resolve_published_at_prefers_metadata(aggregator: ContentAggregator):
    item = {"meta_data": {"published_at": "2024-02-03T10:15:30Z"}}

    resolved = aggregator._resolve_published_at(item)

    assert resolved == datetime(2024, 2, 3, 10, 15, 30)
    assert item["meta_data"]["published_at"].startswith("2024-02-03T10:15:30")


@pytest.mark.asyncio
async def test_persist_items_inserts_and_updates(
    aggregator: ContentAggregator,
    db_session_factory: sessionmaker,
):
    first_payload = [
        {
            "type": "article",
            "title": "Post One",
            "url": "https://example.com/post-one/?utm_source=news",
            "author": None,
            "published_at": datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
            "thumbnail_url": None,
            "meta_data": {"original_url": "https://example.com/post-one?utm_medium=email", "extra": "v1"},
        }
    ]

    stats_first = await aggregator._persist_items(first_payload)

    assert stats_first["items_added"] == 1
    assert stats_first["items_updated"] == 0
    assert stats_first["items_with_thumbnails"] == 1
    assert aggregator._extract_thumbnail.await_count == 1

    with db_session_factory() as session:  # type: Session
        stored = session.query(ContentItem).one()
        assert stored.url == "https://example.com/post-one"
        assert stored.thumbnail_url == "http://thumbs.local/example.jpg"
        assert stored.meta_data["original_url"] == "https://example.com/post-one"
        assert stored.meta_data["extra"] == "v1"
        assert stored.author is None

    updated_payload = [
        {
            "type": "article",
            "title": "Post One",
            "url": "https://example.com/post-one",
            "author": "Updated Author",
            "published_at": datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
            "thumbnail_url": None,
            "meta_data": {"original_url": "https://example.com/post-one", "note": "refreshed"},
        }
    ]

    stats_second = await aggregator._persist_items(updated_payload)

    assert stats_second["items_added"] == 0
    assert stats_second["items_updated"] == 1
    assert stats_second["items_with_thumbnails"] == 0
    assert aggregator._extract_thumbnail.await_count == 1

    with db_session_factory() as session:  # type: Session
        stored = session.query(ContentItem).one()
        assert stored.url == "https://example.com/post-one"
        assert stored.author == "Updated Author"
        assert stored.thumbnail_url == "http://thumbs.local/example.jpg"
        assert stored.meta_data["original_url"] == "https://example.com/post-one"
        assert stored.meta_data["extra"] == "v1"
        assert stored.meta_data["note"] == "refreshed"


@pytest.mark.asyncio
async def test_persist_items_dedupes_by_original_url(
    aggregator: ContentAggregator,
    db_session_factory: sessionmaker,
):
    # Seed an existing mirrored item that should be updated using original_url matching
    with db_session_factory() as session:  # type: Session
        session.add(
            ContentItem(
                id=str(uuid4()),
                type="article",
                title="Mirror Story",
                url="https://mirror.example.com/story?ref=feed",
                published_at=datetime(2024, 1, 5, 9, 0, tzinfo=timezone.utc),
                meta_data={"original_url": "https://source.example.com/story"},
            )
        )
        session.commit()

    payload = [
        {
            "type": "article",
            "title": "Source Story",
            "url": "https://source.example.com/story?utm_campaign=newsletter",
            "author": "Canonical Author",
            "published_at": datetime(2024, 1, 6, 14, 30, tzinfo=timezone.utc),
            "thumbnail_url": None,
            "meta_data": {"original_url": "https://source.example.com/story", "source": "origin"},
        }
    ]

    stats = await aggregator._persist_items(payload)

    assert stats["items_added"] == 0
    assert stats["items_updated"] == 1
    assert aggregator._extract_thumbnail.await_count == 0

    with db_session_factory() as session:  # type: Session
        rows = session.query(ContentItem).all()
        assert len(rows) == 1
        stored = rows[0]
        assert stored.url == "https://source.example.com/story"
        assert stored.meta_data["original_url"] == "https://source.example.com/story"
        assert stored.meta_data["source"] == "origin"
        assert stored.published_at == datetime(2024, 1, 6, 14, 30)
        # Title remains from the existing row, confirming an update instead of insert
        assert stored.title == "Mirror Story"
