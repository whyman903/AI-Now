"""
Content aggregation endpoints for triggering and monitoring content collection.
"""

import asyncio
import logging
from typing import Any, Awaitable, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_aggregation_token
from app.crud.content import ContentCRUD
from app.db.base import get_db
from app.services.aggregation.aggregator import get_content_aggregator

logger = logging.getLogger(__name__)
router = APIRouter()


class IngestItem(BaseModel):
    title: str
    url: str
    author: Optional[str] = None
    published_at: Optional[str] = None
    thumbnail_url: Optional[str] = None
    type: str = "article"
    meta_data: Optional[Dict[str, Any]] = None
    source_key: Optional[str] = None


class IngestRequest(BaseModel):
    source_key: str
    items: List[IngestItem]


def _track_background_task(request: Request, coro: Awaitable[Any]) -> None:
    task = asyncio.create_task(coro)
    background_tasks = getattr(request.app.state, "background_tasks", None)
    if isinstance(background_tasks, set):
        background_tasks.add(task)

    def _cleanup(done_task: asyncio.Task[Any]) -> None:
        if isinstance(background_tasks, set):
            background_tasks.discard(done_task)
        try:
            done_task.result()
        except asyncio.CancelledError:
            logger.warning("Content aggregation task cancelled")
        except Exception:
            logger.exception("Content aggregation task failed")

    task.add_done_callback(_cleanup)


@router.post(
    "/trigger",
    dependencies=[Depends(require_aggregation_token)],
)
async def trigger_aggregation(
    request: Request,
    hours_back: int = 24,
    low_memory: bool = Body(False, embed=True),
) -> Dict[str, Any]:
    """
    Trigger content aggregation from all sources.
    
    Args:
        hours_back: How many hours back to fetch content (default: 24)
        low_memory: Run aggregation sequentially with reduced batch sizes (default: False)
        
    Returns:
        Dict with aggregation trigger status
    """
    try:
        aggregator = get_content_aggregator()
        aggregator.configure(low_memory=low_memory)

        _track_background_task(request, aggregator.aggregate_all_content())
        
        logger.info(
            "Content aggregation triggered for last %s hours (low_memory=%s)",
            hours_back,
            low_memory,
        )
        
        return {
            "status": "triggered",
            "message": f"Content aggregation started for last {hours_back} hours",
            "hours_back": hours_back,
            "low_memory": low_memory,
        }
        
    except Exception as e:
        logger.error(f"Error triggering content aggregation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_aggregation_status(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Get current status of content aggregation including statistics.
    
    Returns:
        Dict with aggregation status and content statistics
    """
    try:
        stats = ContentCRUD.get_content_stats(db)

        agg = get_content_aggregator()
        sources_summary = {
            'non_selenium': agg.non_selenium_source_count,
            'selenium': agg.selenium_source_count,
            'total': agg.source_count,
        }

        return {
            "status": "success",
            "data": {
                **stats,
                'sources': sources_summary,
            },
        }
        
    except Exception as e:
        logger.error(f"Error getting aggregation status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/ingest",
    dependencies=[Depends(require_aggregation_token)],
)
async def ingest_scraped_content(payload: IngestRequest) -> Dict[str, Any]:
    """Accept pre-scraped items (e.g. from GitHub Actions) and persist them."""
    items = [
        {**item.model_dump(), "source_key": payload.source_key}
        for item in payload.items
    ]

    aggregator = get_content_aggregator()
    stats = await aggregator._persist_items(items)

    logger.info(
        "Ingested %d items for source %s (added=%d, updated=%d)",
        len(items),
        payload.source_key,
        stats["items_added"],
        stats["items_updated"],
    )

    return {
        "status": "success",
        "source_key": payload.source_key,
        **stats,
    }
