"""
Content aggregation endpoints for triggering and monitoring content collection.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Body
from typing import Dict, Any
import logging

from app.services.content_aggregator import get_content_aggregator
from app.crud.content import ContentCRUD
from app.db.base import get_db
from fastapi import Depends
from sqlalchemy.orm import Session

from app.api.deps import require_aggregation_token

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/trigger",
    dependencies=[Depends(require_aggregation_token)],
)
async def trigger_aggregation(
    background_tasks: BackgroundTasks,
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
        
        background_tasks.add_task(
            aggregator.aggregate_all_content
        )
        
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
            'rss_feeds': len(agg.rss_sources),
            'youtube_channels': len(agg.youtube_channels),
            'web_scrapers': len(agg.web_scraper_sources),
            'total': len(agg.rss_sources) + len(agg.youtube_channels) + len(agg.web_scraper_sources),
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
