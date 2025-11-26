import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Generator
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
for path in (BACKEND_ROOT, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    module=r"^feedparser\.encodings$",
)
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    module=r"^dateutil\.tz\.tz$",
)
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    module=r"^fastavro\._(read|write)_py$",
)
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    module=r"^importlib\._bootstrap$",
    message=r".*Snappy compression will use `cramjam`.*",
)

_original_create_engine = sa.create_engine


def _safe_create_engine(*args, **kwargs):
    url = args[0] if args else kwargs.get("url", "")
    if isinstance(url, str) and url.startswith("sqlite"):
        kwargs.pop("pool_size", None)
        kwargs.pop("max_overflow", None)
        kwargs.pop("pool_timeout", None)
    return _original_create_engine(*args, **kwargs)


sa.create_engine = _safe_create_engine

from app.db import base, models  # noqa: E402
from app.services import analytics_queue as analytics_queue_module  # noqa: E402
from app.services import content_aggregator as content_aggregator_module  # noqa: E402


def _sqlite_engine(db_file: Path) -> sa.Engine:
    engine = sa.create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    sa.event.listen(
        engine,
        "connect",
        lambda conn, record: conn.create_function("gen_random_uuid", 0, lambda: str(uuid4())),
    )
    return engine


def _coerce_uuid_columns_to_string() -> None:
    for table in models.Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, PG_UUID):
                column.type = sa.String(36)


@pytest.fixture
def sessionmaker_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[sessionmaker, None, None]:
    """
    Patch application session factory to use the temporary SQLite engine.

    Returns a sessionmaker so tests can seed data easily.
    """
    engine = _sqlite_engine(tmp_path / "test.db")
    _coerce_uuid_columns_to_string()

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr(base, "engine", engine)
    monkeypatch.setattr(base, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(content_aggregator_module, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(analytics_queue_module, "SessionLocal", TestingSessionLocal)
    content_aggregator_module._aggregator = None
    from app.crud import analytics as analytics_crud
    monkeypatch.setattr(
        analytics_crud,
        "_coerce_uuid",
        lambda value=None: str(value) if value is not None else str(uuid4()),
    )

    # SQLite does not like re-creating indexes between runs; strip all indexes for isolated tests
    for table in models.Base.metadata.tables.values():
        for idx in list(table.indexes):
            table.indexes.discard(idx)

    # Fresh schema per test for isolation
    models.Base.metadata.drop_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(sa.text("PRAGMA writable_schema = 1"))
        conn.execute(sa.text("DELETE FROM sqlite_master WHERE type = 'index'"))
        conn.execute(sa.text("PRAGMA writable_schema = 0"))
    models.Base.metadata.create_all(bind=engine)
    yield TestingSessionLocal
    engine.dispose()


@pytest.fixture
def analytics_queue_stub(monkeypatch: pytest.MonkeyPatch) -> Dict[str, list]:
    """
    Replace the analytics queue with a lightweight stub to avoid background threads.
    Collects all payloads for assertions.
    """
    events: Dict[str, list] = {"interactions": [], "searches": [], "clicks": []}
    from app.api.v1.endpoints import analytics as analytics_endpoints

    class StubQueue:
        def enqueue_interaction(self, payload):
            events["interactions"].append(payload)
            return {
                "interaction_id": payload.get("interaction_id") or "interaction-1",
                "content_id": payload.get("content_id"),
                "interaction_type": payload.get("interaction_type"),
                "timestamp": payload.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            }

        def enqueue_interactions(self, payloads):
            return [self.enqueue_interaction(p) for p in payloads]

        def enqueue_search(self, payload):
            events["searches"].append(payload)
            return {
                "search_id": payload.get("search_id") or "search-1",
                "query": payload.get("query"),
                "timestamp": payload.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            }

        def enqueue_searches(self, payloads):
            return [self.enqueue_search(p) for p in payloads]

        def enqueue_search_click(self, payload):
            events["clicks"].append(payload)
            return {
                "search_id": payload.get("search_id"),
                "clicked_result_id": payload.get("clicked_result_id"),
                "clicked_position": payload.get("clicked_position"),
            }

        def enqueue_search_clicks(self, payloads):
            accepted = [self.enqueue_search_click(p) for p in payloads]
            return {"updated_count": len(accepted), "updated": accepted, "missing": []}

    # Stop the real background worker and swap in the stub everywhere endpoints reference it
    try:
        analytics_queue_module.analytics_queue.shutdown()
    except Exception:
        pass

    stub = StubQueue()
    monkeypatch.setattr(analytics_queue_module, "analytics_queue", stub)
    monkeypatch.setattr(analytics_endpoints, "analytics_queue", stub)
    return events
