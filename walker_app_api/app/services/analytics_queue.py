"""In-process analytics event queue with background worker."""

from __future__ import annotations

import atexit
import logging
import threading
from datetime import datetime, timezone
from queue import Empty, Full, Queue
from typing import Any, Dict, Iterable, List, Tuple
from uuid import uuid4

from app.core.config import settings
from app.crud.analytics import AnalyticsCRUD
from app.db.base import SessionLocal

logger = logging.getLogger(__name__)

_SENTINEL = object()


class AnalyticsQueueFullError(RuntimeError):
    """Raised when the analytics queue cannot accept more events."""


EventPayload = Dict[str, Any]
QueuedEvent = Tuple[str, EventPayload]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


class AnalyticsQueue:
    """Simple background worker that batches analytics events."""

    def __init__(self) -> None:
        self._queue: "Queue[Any]" = Queue(maxsize=settings.ANALYTICS_QUEUE_MAXSIZE)
        self._stop_event = threading.Event()
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="analytics-event-worker",
            daemon=True,
        )
        self._worker.start()
        atexit.register(self.shutdown)

    # ------------------------------------------------------------------
    # Public API
    def enqueue_interaction(self, payload: EventPayload) -> Dict[str, Any]:
        interaction_id = payload.get("interaction_id") or str(uuid4())
        timestamp = payload.get("timestamp") or _utcnow_iso()
        event_payload = {
            **payload,
            "interaction_id": interaction_id,
            "timestamp": timestamp,
        }
        self._offer("interaction", event_payload)
        return {
            "interaction_id": interaction_id,
            "content_id": event_payload.get("content_id"),
            "interaction_type": event_payload.get("interaction_type"),
            "timestamp": timestamp,
        }

    def enqueue_interactions(self, payloads: Iterable[EventPayload]) -> List[Dict[str, Any]]:
        return [self.enqueue_interaction(payload) for payload in payloads]

    def enqueue_search(self, payload: EventPayload) -> Dict[str, Any]:
        search_id = payload.get("search_id") or str(uuid4())
        timestamp = payload.get("timestamp") or _utcnow_iso()
        event_payload = {
            **payload,
            "search_id": search_id,
            "timestamp": timestamp,
        }
        self._offer("search", event_payload)
        return {
            "search_id": search_id,
            "query": event_payload.get("query"),
            "timestamp": timestamp,
        }

    def enqueue_searches(self, payloads: Iterable[EventPayload]) -> List[Dict[str, Any]]:
        return [self.enqueue_search(payload) for payload in payloads]

    def enqueue_search_click(self, payload: EventPayload) -> Dict[str, Any]:
        self._offer("search_click", dict(payload))
        return {
            "search_id": payload.get("search_id"),
            "clicked_result_id": payload.get("clicked_result_id"),
            "clicked_position": payload.get("clicked_position"),
        }

    def enqueue_search_clicks(self, payloads: Iterable[EventPayload]) -> Dict[str, Any]:
        accepted = []
        for payload in payloads:
            accepted.append(self.enqueue_search_click(payload))
        return {
            "updated_count": len(accepted),
            "updated": accepted,
            "missing": [],
        }

    def shutdown(self) -> None:
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        try:
            self._queue.put_nowait(_SENTINEL)
        except Full:  # pragma: no cover - defensive fallback
            self._queue.put(_SENTINEL)
        self._worker.join(timeout=settings.BACKGROUND_TASK_SHUTDOWN_TIMEOUT)

    # ------------------------------------------------------------------
    def _offer(self, event_type: str, payload: EventPayload) -> None:
        if self._stop_event.is_set():
            raise AnalyticsQueueFullError("Analytics queue shutting down")
        try:
            self._queue.put_nowait((event_type, payload))
        except Full as exc:
            logger.warning("Analytics queue full; dropping event", extra={"event_type": event_type})
            raise AnalyticsQueueFullError("Analytics queue is full") from exc

    def _worker_loop(self) -> None:
        batch: List[QueuedEvent] = []
        flush_interval = max(settings.ANALYTICS_QUEUE_FLUSH_SECONDS, 0.1)
        max_batch = max(settings.ANALYTICS_QUEUE_BATCH_SIZE, 1)

        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=flush_interval)
            except Empty:
                if batch:
                    self._flush(batch)
                    batch.clear()
                continue

            if item is _SENTINEL:
                self._queue.task_done()
                break

            batch.append(item)
            if len(batch) >= max_batch:
                self._flush(batch)
                batch.clear()

        if batch:
            self._flush(batch)
            batch.clear()

        # Drain any remaining sentinel markers
        while True:
            try:
                item = self._queue.get_nowait()
            except Empty:
                break
            if item is _SENTINEL:
                self._queue.task_done()
                break

    def _flush(self, batch: List[QueuedEvent]) -> None:
        if not batch:
            return

        interactions: List[EventPayload] = []
        searches: List[EventPayload] = []
        search_clicks: List[EventPayload] = []

        for event_type, payload in batch:
            if event_type == "interaction":
                interactions.append(payload)
            elif event_type == "search":
                searches.append(payload)
            elif event_type == "search_click":
                search_clicks.append(payload)

        if not (interactions or searches or search_clicks):
            for _ in batch:
                self._queue.task_done()
            return

        db = SessionLocal()
        try:
            if interactions:
                AnalyticsCRUD.batch_track_interactions(db, events=interactions)
            if searches:
                AnalyticsCRUD.batch_track_searches(db, searches=searches)
            if search_clicks:
                result = AnalyticsCRUD.batch_update_search_clicks(db, updates=search_clicks)
                missing = result.get("missing") if isinstance(result, dict) else None
                if missing:
                    logger.info(
                        "Analytics queue reported missing search IDs during click update",
                        extra={"missing": missing},
                    )
        except Exception:
            db.rollback()
            logger.exception(
                "Failed to flush analytics batch",
                extra={
                    "interactions": len(interactions),
                    "searches": len(searches),
                    "search_clicks": len(search_clicks),
                },
            )
        finally:
            db.close()
            for _ in batch:
                self._queue.task_done()


analytics_queue = AnalyticsQueue()
