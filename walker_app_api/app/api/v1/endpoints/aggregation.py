"""
Content aggregation endpoints for triggering and monitoring content collection.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict, Any
import logging

from app.services.content_aggregator import get_content_aggregator
from app.crud.content import ContentCRUD
from app.db.base import get_db
from fastapi import Depends
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/trigger")
async def trigger_aggregation(
    background_tasks: BackgroundTasks,
    hours_back: int = 24
) -> Dict[str, Any]:
    """
    Trigger content aggregation from all sources.
    
    Args:
        hours_back: How many hours back to fetch content (default: 24)
        
    Returns:
        Dict with aggregation trigger status
    """
    try:
        aggregator = get_content_aggregator()
        background_tasks.add_task(
            aggregator.aggregate_all_content
        )
        
        logger.info(f"Content aggregation triggered for last {hours_back} hours")
        
        return {
            "status": "triggered",
            "message": f"Content aggregation started for last {hours_back} hours",
            "hours_back": hours_back
        }
        
    except Exception as e:
        logger.error(f"Error triggering content aggregation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/aggregate-now")
async def aggregate_now(hours_back: int = 24) -> Dict[str, Any]:
    """
    Immediately aggregate content from all sources (synchronous).
    
    Args:
        hours_back: How many hours back to fetch content (default: 24)
        
    Returns:
        Dict with detailed aggregation results
    """
    try:
        logger.info(f"Starting immediate content aggregation for last {hours_back} hours")
        
        aggregator = get_content_aggregator()
        results = await aggregator.aggregate_all_content()
        
        return {
            "status": "completed",
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Error during immediate content aggregation: {e}")
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
