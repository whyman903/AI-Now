"""Analytics tracking and reporting endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.crud.analytics import AnalyticsCRUD
from app.db.base import get_db
from app.services.analytics_queue import AnalyticsQueueFullError, analytics_queue

logger = logging.getLogger(__name__)

router = APIRouter()


class SessionPayload(BaseModel):
    session_id: str = Field(..., description="Unique client session identifier")
    user_id: Optional[str] = Field(None, description="Optional authenticated user id")


class InteractionPayload(BaseModel):
    content_id: str = Field(..., description="Content item identifier")
    interaction_type: str = Field(..., description="E.g. click, view, share")
    session_id: Optional[str] = Field(None, description="Associated session id")
    user_id: Optional[str] = Field(None, description="Optional user id")
    source_page: Optional[str] = Field(None, description="Page where interaction happened")
    position: Optional[int] = Field(None, description="Position of the content in UI")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class SearchPayload(BaseModel):
    query: str
    results_count: Optional[int] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None


class SearchClickPayload(BaseModel):
    search_id: str
    clicked_result_id: str
    clicked_position: Optional[int] = None


class InteractionBatchPayload(BaseModel):
    interactions: List[InteractionPayload] = Field(
        ...,
        min_items=1,
        max_items=200,
        description="Collection of interaction events to persist in a single request",
    )


class SearchBatchPayload(BaseModel):
    searches: List[SearchPayload] = Field(
        ...,
        min_items=1,
        max_items=200,
        description="Collection of search events to persist in a single request",
    )


class SearchClickBatchPayload(BaseModel):
    updates: List[SearchClickPayload] = Field(
        ...,
        min_items=1,
        max_items=200,
        description="Collection of search click updates to apply",
    )


@router.post("/session", tags=["analytics"])
async def create_or_update_session(
    payload: SessionPayload,
    request: Request,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        forwarded_for = request.headers.get("x-forwarded-for")
        ip_address = forwarded_for.split(",")[0].strip() if forwarded_for else request.client.host if request.client else None
        record = AnalyticsCRUD.get_or_create_session(
            db,
            session_id=payload.session_id,
            user_id=payload.user_id,
            user_agent=request.headers.get("user-agent"),
            ip_address=ip_address,
            referrer=request.headers.get("referer"),
        )
        return {
            "session_id": record.session_id,
            "user_id": record.user_id,
            "first_seen": record.first_seen.isoformat() if record.first_seen else None,
            "last_seen": record.last_seen.isoformat() if record.last_seen else None,
            "page_views": record.page_views,
            "interactions": record.interactions,
        }
    except SQLAlchemyError as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail="Unable to persist session.") from exc


@router.post("/track/interaction", tags=["analytics"])
async def track_interaction(
    payload: InteractionPayload,
    request: Request,
) -> Dict[str, Any]:
    referer = request.headers.get("referer")
    user_agent = request.headers.get("user-agent")
    forwarded_for = request.headers.get("x-forwarded-for")
    ip_address = forwarded_for.split(",")[0].strip() if forwarded_for else request.client.host if request.client else None

    try:
        return analytics_queue.enqueue_interaction(
            {
                "content_id": payload.content_id,
                "interaction_type": payload.interaction_type,
                "session_id": payload.session_id,
                "user_id": payload.user_id,
                "source_page": payload.source_page,
                "position": payload.position,
                "referrer": referer,
                "user_agent": user_agent,
                "metadata": payload.metadata,
                "ip_address": ip_address,
            }
        )
    except AnalyticsQueueFullError as exc:
        logger.warning(
            "Analytics queue full; dropping interaction",
            extra={
                "content_id": payload.content_id,
                "interaction_type": payload.interaction_type,
                "session_id": payload.session_id,
            },
        )
        raise HTTPException(status_code=503, detail="Analytics queue is busy. Try again later.") from exc


@router.post("/track/interactions/batch", tags=["analytics"])
async def track_interactions_batch(
    payload: InteractionBatchPayload,
    request: Request,
) -> Dict[str, Any]:
    try:
        referer = request.headers.get("referer")
        user_agent = request.headers.get("user-agent")
        forwarded_for = request.headers.get("x-forwarded-for")
        ip_address = forwarded_for.split(",")[0].strip() if forwarded_for else request.client.host if request.client else None

        results = analytics_queue.enqueue_interactions(
            {
                "content_id": item.content_id,
                "interaction_type": item.interaction_type,
                "session_id": item.session_id,
                "user_id": item.user_id,
                "source_page": item.source_page,
                "position": item.position,
                "referrer": referer,
                "user_agent": user_agent,
                "metadata": item.metadata,
                "ip_address": ip_address,
            }
            for item in payload.interactions
        )
        return {"count": len(results), "results": results}
    except AnalyticsQueueFullError as exc:
        logger.warning("Analytics queue full; dropping interaction batch", extra={"batch_size": len(payload.interactions)})
        raise HTTPException(status_code=503, detail="Analytics queue is busy. Try again later.") from exc


@router.post("/track/search", tags=["analytics"])
async def track_search(
    payload: SearchPayload,
    request: Request,
) -> Dict[str, Any]:
    referer = request.headers.get("referer")
    user_agent = request.headers.get("user-agent")
    try:
        return analytics_queue.enqueue_search(
            {
                "query": payload.query,
                "results_count": payload.results_count,
                "session_id": payload.session_id,
                "user_id": payload.user_id,
                "filters": payload.filters,
                "referrer": referer,
                "user_agent": user_agent,
            }
        )
    except AnalyticsQueueFullError as exc:
        raise HTTPException(status_code=503, detail="Analytics queue is busy. Try again later.") from exc


@router.post("/track/searches/batch", tags=["analytics"])
async def track_searches_batch(
    payload: SearchBatchPayload,
    request: Request,
) -> Dict[str, Any]:
    referer = request.headers.get("referer")
    user_agent = request.headers.get("user-agent")
    try:
        results = analytics_queue.enqueue_searches(
            {
                "query": item.query,
                "results_count": item.results_count,
                "session_id": item.session_id,
                "user_id": item.user_id,
                "filters": item.filters,
                "referrer": referer,
                "user_agent": user_agent,
            }
            for item in payload.searches
        )
        return {"count": len(results), "results": results}
    except AnalyticsQueueFullError as exc:
        raise HTTPException(status_code=503, detail="Analytics queue is busy. Try again later.") from exc


@router.post("/track/search-click", tags=["analytics"])
async def track_search_click(
    payload: SearchClickPayload,
) -> Dict[str, Any]:
    try:
        return analytics_queue.enqueue_search_click(
            {
                "search_id": payload.search_id,
                "clicked_result_id": payload.clicked_result_id,
                "clicked_position": payload.clicked_position,
            }
        )
    except AnalyticsQueueFullError as exc:
        raise HTTPException(status_code=503, detail="Analytics queue is busy. Try again later.") from exc


@router.post("/track/search-click/batch", tags=["analytics"])
async def track_search_click_batch(
    payload: SearchClickBatchPayload,
) -> Dict[str, Any]:
    try:
        return analytics_queue.enqueue_search_clicks(
            {
                "search_id": item.search_id,
                "clicked_result_id": item.clicked_result_id,
                "clicked_position": item.clicked_position,
            }
            for item in payload.updates
        )
    except AnalyticsQueueFullError as exc:
        raise HTTPException(status_code=503, detail="Analytics queue is busy. Try again later.") from exc


@router.get("/content/{content_id}", tags=["analytics"])
async def get_content_analytics(
    content_id: str,
    days_back: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        return AnalyticsCRUD.get_content_analytics(
            db,
            content_id=content_id,
            days_back=days_back,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Unable to fetch content analytics.") from exc


@router.get("/trending", tags=["analytics"])
async def get_trending_content(
    hours_back: int = Query(24, ge=1, le=168),
    limit: int = Query(20, ge=1, le=100),
    interaction_type: Optional[str] = Query(None, description="Filter by interaction type"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        return {
            "hours_back": hours_back,
            "limit": limit,
            "interaction_type": interaction_type,
            "results": AnalyticsCRUD.get_trending_content(
                db,
                hours_back=hours_back,
                limit=limit,
                interaction_type=interaction_type,
            ),
        }
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Unable to fetch trending content.") from exc


@router.get("/popular-searches", tags=["analytics"])
async def get_popular_searches(
    days_back: int = Query(7, ge=1, le=90),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        return {
            "days_back": days_back,
            "limit": limit,
            "results": AnalyticsCRUD.get_popular_searches(
                db,
                days_back=days_back,
                limit=limit,
            ),
        }
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Unable to fetch popular searches.") from exc


@router.get("/session-stats", tags=["analytics"])
async def get_session_stats(
    days_back: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        return AnalyticsCRUD.get_session_stats(db=db, days_back=days_back)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Unable to fetch session stats.") from exc


@router.get("/timeline", tags=["analytics"])
async def get_interaction_timeline(
    hours_back: int = Query(24, ge=1, le=168),
    bucket_minutes: int = Query(60, ge=5, le=1440),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        return {
            "hours_back": hours_back,
            "bucket_minutes": bucket_minutes,
            "timeline": AnalyticsCRUD.get_interaction_timeline(
                db,
                hours_back=hours_back,
                bucket_minutes=bucket_minutes,
            ),
        }
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Unable to fetch interaction timeline.") from exc


@router.get("/dashboard", tags=["analytics"])
async def get_dashboard(
    days_back: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        return AnalyticsCRUD.get_dashboard(db=db, days_back=days_back)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Unable to fetch analytics dashboard.") from exc
