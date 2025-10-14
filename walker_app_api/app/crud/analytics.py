"""CRUD helpers for analytics, tracking, and aggregation logging."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID, uuid4

from sqlalchemy import and_, func, desc
from sqlalchemy.orm import Session

from app.db.models import (
    AggregationRun,
    AggregationRunSource,
    ContentInteraction,
    ContentItem,
    SearchQuery,
    UserSession,
)


class AnalyticsCRUD:
    """Database helpers for analytics and tracking events."""

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    # ------------------------------------------------------------------
    # Session helpers
    @staticmethod
    def get_or_create_session(
        db: Session,
        *,
        session_id: str,
        user_id: Optional[str] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
        referrer: Optional[str] = None,
        commit: bool = True,
    ) -> UserSession:
        now = AnalyticsCRUD._utcnow()
        session = db.get(UserSession, session_id)

        if session:
            session.last_seen = now
            if user_id and not session.user_id:
                session.user_id = user_id
            if user_agent:
                session.user_agent = user_agent
            if ip_address:
                session.ip_address = ip_address
            if referrer and not session.referrer:
                session.referrer = referrer
        else:
            session = UserSession(
                session_id=session_id,
                user_id=user_id,
                first_seen=now,
                last_seen=now,
                user_agent=user_agent,
                ip_address=ip_address,
                referrer=referrer,
                page_views=0,
                interactions=0,
            )
            db.add(session)

        if commit:
            db.commit()
            db.refresh(session)
        else:
            db.flush()
        return session

    @staticmethod
    def _record_interaction(
        db: Session,
        *,
        interaction_id: Optional[Any] = None,
        content_id: str,
        interaction_type: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        source_page: Optional[str] = None,
        position: Optional[int] = None,
        referrer: Optional[str] = None,
        user_agent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        timestamp: Optional[Any] = None,
    ) -> ContentInteraction:
        interaction_timestamp = AnalyticsCRUD._parse_datetime(timestamp) if timestamp else None
        recorded_at = interaction_timestamp or AnalyticsCRUD._utcnow()
        interaction_uuid = _coerce_uuid(interaction_id)

        tracked_session: Optional[UserSession] = None
        if session_id:
            tracked_session = AnalyticsCRUD.get_or_create_session(
                db,
                session_id=session_id,
                user_id=user_id,
                user_agent=user_agent,
                referrer=referrer,
                ip_address=ip_address,
                commit=False,
            )

        interaction = ContentInteraction(
            id=interaction_uuid,
            content_id=content_id,
            session_id=session_id,
            user_id=user_id,
            interaction_type=interaction_type,
            timestamp=recorded_at,
            source_page=source_page,
            position=position,
            referrer=referrer,
            user_agent=user_agent,
            meta_data=dict(metadata) if metadata else {},
        )
        db.add(interaction)

        if tracked_session:
            tracked_session.interactions = (tracked_session.interactions or 0) + 1
            tracked_session.last_seen = recorded_at
            if (interaction_type or "").lower() == "view":
                tracked_session.page_views = (tracked_session.page_views or 0) + 1

        if (interaction_type or "").lower() == "click":
            content_item = db.get(ContentItem, content_id)
            if content_item:
                content_item.clicks = (content_item.clicks or 0) + 1

        return interaction

    @staticmethod
    def batch_track_interactions(
        db: Session,
        *,
        events: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not events:
            return []

        recorded: List[Dict[str, Any]] = []
        for event in events:
            interaction = AnalyticsCRUD._record_interaction(
                db,
                interaction_id=event.get("interaction_id"),
                content_id=event["content_id"],
                interaction_type=event["interaction_type"],
                session_id=event.get("session_id"),
                user_id=event.get("user_id"),
                source_page=event.get("source_page"),
                position=event.get("position"),
                referrer=event.get("referrer"),
                user_agent=event.get("user_agent"),
                metadata=event.get("metadata"),
                ip_address=event.get("ip_address"),
                timestamp=event.get("timestamp"),
            )
            recorded.append(
                {
                    "interaction_id": str(interaction.id),
                    "content_id": interaction.content_id,
                    "interaction_type": interaction.interaction_type,
                    "timestamp": interaction.timestamp.isoformat() if interaction.timestamp else None,
                }
            )

        db.commit()
        return recorded

    @staticmethod
    def _record_search(
        db: Session,
        *,
        search_id: Optional[Any] = None,
        query: str,
        results_count: Optional[int] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        referrer: Optional[str] = None,
        user_agent: Optional[str] = None,
        timestamp: Optional[Any] = None,
    ) -> SearchQuery:
        search_timestamp = AnalyticsCRUD._parse_datetime(timestamp) if timestamp else None
        recorded_at = search_timestamp or AnalyticsCRUD._utcnow()
        search_uuid = _coerce_uuid(search_id)

        tracked_session: Optional[UserSession] = None
        if session_id:
            tracked_session = AnalyticsCRUD.get_or_create_session(
                db,
                session_id=session_id,
                user_id=user_id,
                user_agent=user_agent,
                referrer=referrer,
                commit=False,
            )

        search = SearchQuery(
            id=search_uuid,
            query=query,
            session_id=session_id,
            user_id=user_id,
            results_count=results_count,
            filters=dict(filters) if filters else {},
            referrer=referrer,
            user_agent=user_agent,
            timestamp=recorded_at,
        )
        db.add(search)

        if tracked_session:
            tracked_session.last_seen = recorded_at

        return search

    @staticmethod
    def batch_track_searches(
        db: Session,
        *,
        searches: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not searches:
            return []

        recorded: List[Dict[str, Any]] = []
        for payload in searches:
            search = AnalyticsCRUD._record_search(
                db,
                search_id=payload.get("search_id"),
                query=payload["query"],
                results_count=payload.get("results_count"),
                session_id=payload.get("session_id"),
                user_id=payload.get("user_id"),
                filters=payload.get("filters"),
                referrer=payload.get("referrer"),
                user_agent=payload.get("user_agent"),
                timestamp=payload.get("timestamp"),
            )
            recorded.append(
                {
                    "search_id": str(search.id),
                    "query": search.query,
                    "timestamp": search.timestamp.isoformat() if search.timestamp else None,
                }
            )

        db.commit()
        return recorded

    @staticmethod
    def update_search_click(
        db: Session,
        *,
        search_id: str,
        clicked_result_id: str,
        clicked_position: Optional[int] = None,
        commit: bool = True,
    ) -> Optional[Dict[str, Any]]:
        search = db.get(SearchQuery, search_id)
        if not search:
            return None
        search.clicked_result_id = clicked_result_id
        search.clicked_position = clicked_position
        if commit:
            db.commit()
        else:
            db.flush()
        return {
            "search_id": str(search.id),
            "clicked_result_id": search.clicked_result_id,
            "clicked_position": search.clicked_position,
        }

    @staticmethod
    def batch_update_search_clicks(
        db: Session,
        *,
        updates: Sequence[Dict[str, Any]],
    ) -> Dict[str, List[Any]]:
        if not updates:
            return {"updated": [], "missing": []}

        updated: List[Dict[str, Any]] = []
        missing: List[str] = []

        for payload in updates:
            result = AnalyticsCRUD.update_search_click(
                db,
                search_id=payload["search_id"],
                clicked_result_id=payload["clicked_result_id"],
                clicked_position=payload.get("clicked_position"),
                commit=False,
            )
            if result is None:
                missing.append(payload["search_id"])
            else:
                updated.append(result)

        db.commit()
        return {"updated": updated, "missing": missing}

    # ------------------------------------------------------------------
    # Aggregation analytics
    @staticmethod
    def record_aggregation_run(
        db: Session,
        *,
        summary: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> AggregationRun:
        started_at = AnalyticsCRUD._parse_datetime(summary.get("started_at")) or AnalyticsCRUD._utcnow()
        completed_at = AnalyticsCRUD._parse_datetime(summary.get("completed_at"))
        duration_seconds = summary.get("duration_seconds")
        errors = summary.get("errors") or []

        run = AggregationRun(
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=float(duration_seconds) if duration_seconds is not None else None,
            status="failed" if errors else "completed",
            total_new_items=int(summary.get("total_new_items", 0)),
            total_items_updated=int(summary.get("total_items_updated", 0)),
            items_with_thumbnails=int(summary.get("items_with_thumbnails", 0)),
            error_count=len(errors),
        )

        context_payload: Optional[Dict[str, Any]] = None
        if context:
            context_payload = dict(context)
            context_payload.setdefault("errors", errors)
            context_payload.setdefault(
                "summary",
                {
                    "total_new_items": int(summary.get("total_new_items", 0)),
                    "total_items_updated": int(summary.get("total_items_updated", 0)),
                },
            )
            context_payload.setdefault("duration_seconds", duration_seconds)
            context_payload.setdefault("items_with_thumbnails", int(summary.get("items_with_thumbnails", 0)))
            context_payload.setdefault("error_count", len(errors))
            context_payload.setdefault("completed_at", completed_at.isoformat() if completed_at else None)
            context_payload.setdefault("started_at", started_at.isoformat())
            context_payload.setdefault("status", run.status)
            context_payload.setdefault("total_sources", len(summary.get("sources") or {}))

        db.add(run)
        db.flush()

        source_payloads = summary.get("sources") or {}
        sources: List[AggregationRunSource] = []
        for key, payload in source_payloads.items():
            metrics = None
            error_message = None
            items_added = items_updated = items_with_thumbnails = 0

            if isinstance(payload, dict):
                metrics = {k: v for k, v in payload.items() if isinstance(v, (int, float, str, list, dict))}
                items_added = int(payload.get("items_added", 0))
                items_updated = int(payload.get("items_updated", 0))
                items_with_thumbnails = int(payload.get("items_with_thumbnails", 0))
                error_message = payload.get("error")
            else:
                error_message = str(payload)

            source = AggregationRunSource(
                run_id=run.id,
                source_name=key,
                source_type=_classify_source(key),
                items_added=items_added,
                items_updated=items_updated,
                items_with_thumbnails=items_with_thumbnails,
                error_message=error_message,
                metrics=metrics,
            )
            sources.append(source)

        if context_payload:
            sources.append(
                AggregationRunSource(
                    run_id=run.id,
                    source_name="run_context",
                    source_type="meta",
                    items_added=0,
                    items_updated=0,
                    items_with_thumbnails=0,
                    error_message=None,
                    metrics=context_payload,
                )
            )

        db.add_all(sources)
        db.commit()
        db.refresh(run)
        return run

    # ------------------------------------------------------------------
    # Reporting helpers
    @staticmethod
    def get_content_analytics(
        db: Session,
        *,
        content_id: str,
        days_back: int = 30,
    ) -> Dict[str, Any]:
        since = AnalyticsCRUD._utcnow() - timedelta(days=days_back)

        base_query = db.query(ContentInteraction).filter(
            and_(
                ContentInteraction.content_id == content_id,
                ContentInteraction.timestamp >= since,
            )
        )

        totals = base_query.count()
        by_type = dict(
            db.query(
                ContentInteraction.interaction_type,
                func.count(ContentInteraction.id),
            )
            .filter(
                and_(
                    ContentInteraction.content_id == content_id,
                    ContentInteraction.timestamp >= since,
                )
            )
            .group_by(ContentInteraction.interaction_type)
            .all()
        )

        content = db.get(ContentItem, content_id)

        return {
            "content_id": content_id,
            "total_interactions": totals,
            "interactions_by_type": by_type,
            "total_clicks": content.clicks if content else 0,
            "period_days": days_back,
        }

    @staticmethod
    def get_trending_content(
        db: Session,
        *,
        hours_back: int = 24,
        limit: int = 20,
        interaction_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        since = AnalyticsCRUD._utcnow() - timedelta(hours=hours_back)

        query = (
            db.query(
                ContentInteraction.content_id,
                ContentItem.title,
                ContentItem.url,
                ContentItem.author,
                ContentItem.type,
                func.count(ContentInteraction.id).label("interaction_count"),
                func.max(ContentItem.clicks).label("total_clicks"),
            )
            .join(ContentItem, ContentItem.id == ContentInteraction.content_id)
            .filter(ContentInteraction.timestamp >= since)
        )

        if interaction_type:
            query = query.filter(ContentInteraction.interaction_type == interaction_type)

        results = (
            query.group_by(
                ContentInteraction.content_id,
                ContentItem.title,
                ContentItem.url,
                ContentItem.author,
                ContentItem.type,
                ContentItem.clicks,
            )
            .order_by(desc("interaction_count"))
            .limit(limit)
            .all()
        )

        return [
            {
                "content_id": content_id,
                "title": title,
                "url": url,
                "author": author,
                "type": content_type,
                "interaction_count": int(interactions),
                "total_clicks": int(total_clicks or 0),
            }
            for content_id, title, url, author, content_type, interactions, total_clicks in results
        ]

    @staticmethod
    def get_popular_searches(
        db: Session,
        *,
        days_back: int = 7,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        since = AnalyticsCRUD._utcnow() - timedelta(days=days_back)

        rows = (
            db.query(
                SearchQuery.query,
                func.count(SearchQuery.id).label("search_count"),
                func.avg(SearchQuery.results_count).label("avg_results"),
                func.count(SearchQuery.clicked_result_id).label("click_count"),
            )
            .filter(SearchQuery.timestamp >= since)
            .group_by(SearchQuery.query)
            .order_by(desc("search_count"))
            .limit(limit)
            .all()
        )

        return [
            {
                "query": query,
                "search_count": int(search_count),
                "avg_results": float(avg_results) if avg_results is not None else 0.0,
                "click_count": int(click_count),
                "click_through_rate": (float(click_count) / search_count * 100.0) if search_count else 0.0,
            }
            for query, search_count, avg_results, click_count in rows
        ]

    @staticmethod
    def get_session_stats(
        db: Session,
        *,
        days_back: int = 7,
    ) -> Dict[str, Any]:
        since = AnalyticsCRUD._utcnow() - timedelta(days=days_back)

        total_sessions = db.query(UserSession).filter(UserSession.first_seen >= since).count()
        total_interactions = db.query(ContentInteraction).filter(ContentInteraction.timestamp >= since).count()
        total_searches = db.query(SearchQuery).filter(SearchQuery.timestamp >= since).count()

        durations = (
            db.query(UserSession.first_seen, UserSession.last_seen)
            .filter(UserSession.first_seen >= since)
            .all()
        )
        total_duration = 0.0
        counted = 0
        for first_seen, last_seen in durations:
            if first_seen and last_seen:
                total_duration += max((last_seen - first_seen).total_seconds(), 0)
                counted += 1

        avg_duration = total_duration / counted if counted else 0.0

        return {
            "period_days": days_back,
            "total_sessions": total_sessions,
            "total_interactions": total_interactions,
            "total_searches": total_searches,
            "avg_session_duration_seconds": avg_duration,
            "avg_interactions_per_session": (total_interactions / total_sessions) if total_sessions else 0.0,
        }

    @staticmethod
    def get_interaction_timeline(
        db: Session,
        *,
        hours_back: int = 24,
        bucket_minutes: int = 60,
    ) -> List[Dict[str, Any]]:
        since = AnalyticsCRUD._utcnow() - timedelta(hours=hours_back)
        bucket_seconds = max(bucket_minutes, 1) * 60

        bucket_expr = func.to_timestamp(
            func.floor(func.extract("epoch", ContentInteraction.timestamp) / bucket_seconds) * bucket_seconds
        )

        rows = (
            db.query(
                bucket_expr.label("bucket"),
                ContentInteraction.interaction_type,
                func.count(ContentInteraction.id).label("count"),
            )
            .filter(ContentInteraction.timestamp >= since)
            .group_by("bucket", ContentInteraction.interaction_type)
            .order_by("bucket")
            .all()
        )

        return [
            {
                "timestamp": bucket.isoformat() if bucket else None,
                "interaction_type": interaction_type,
                "count": int(count),
            }
            for bucket, interaction_type, count in rows
        ]

    @staticmethod
    def get_dashboard(
        db: Session,
        *,
        days_back: int = 7,
    ) -> Dict[str, Any]:
        session_stats = AnalyticsCRUD.get_session_stats(db=db, days_back=days_back)
        trending = AnalyticsCRUD.get_trending_content(db=db, hours_back=24, limit=10)
        popular_searches = AnalyticsCRUD.get_popular_searches(db=db, days_back=days_back, limit=10)
        timeline = AnalyticsCRUD.get_interaction_timeline(db=db, hours_back=24, bucket_minutes=60)

        return {
            "period_days": days_back,
            "session_stats": session_stats,
            "trending_content": trending,
            "popular_searches": popular_searches,
            "interaction_timeline": timeline,
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc).replace(tzinfo=None)
        if isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value)
                if dt.tzinfo:
                    return dt.astimezone(timezone.utc).replace(tzinfo=None)
                return dt
            except ValueError:
                return None
        return None


def _coerce_uuid(value: Optional[Any]) -> UUID:
    if isinstance(value, UUID):
        return value
    if value is not None:
        try:
            return UUID(str(value))
        except (TypeError, ValueError):
            pass
    return uuid4()


def _classify_source(key: str) -> str:
    """Best-effort classification for aggregation source keys."""

    key_lower = key.lower()
    if "rss" in key_lower:
        return "rss"
    if "youtube" in key_lower:
        return "youtube"
    if "scraper" in key_lower:
        return "scraper"
    return key_lower
