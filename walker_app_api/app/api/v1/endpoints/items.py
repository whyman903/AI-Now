from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any
from app.services.content_aggregator_firecrawl import get_aggregator_firecrawl

router = APIRouter()
aggregator = get_aggregator_firecrawl()

@router.get("/sources")
def get_content_sources():
    """Get all configured RSS sources from the aggregator"""
    sources = aggregator.rss_sources
    
    return {
        "total": len(sources),
        "sources": [
            {
                "name": source["name"],
                "url": source["url"],
                "type": source["type"],
                "category": source["category"],
                "active": True  # Assumed active as they are in the aggregator list
            }
            for source in sources
        ]
    }

@router.get("/sources/status")
async def get_sources_status():
    """Get status of content aggregation"""
    return {"status": "active", "sources": len(aggregator.rss_sources + aggregator.youtube_channels + aggregator.web_scraper_sources)}

@router.get("/sources/types")
def get_source_types():
    """Get available source types from the aggregator"""
    source_types = set(s['type'] for s in aggregator.rss_sources)
    return {
        "types": list(source_types)
    }

@router.get("/categories")
def get_available_categories():
    """Get available content categories"""
    return {
        "categories": [
            {"id": "ai_ml", "name": "AI & Machine Learning"},
            {"id": "programming", "name": "Programming"},
            {"id": "startup", "name": "Startups"},
            {"id": "tech_news", "name": "Tech News"},
            {"id": "blockchain", "name": "Blockchain"},
            {"id": "cybersecurity", "name": "Cybersecurity"}
        ]
    }

@router.post("/sources/refresh/{source_name}")
async def refresh_specific_source(source_name: str):
    """Manually refresh a specific source"""
    sources = aggregator.rss_sources
    source = next((s for s in sources if s["name"] == source_name), None)
    
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    # Run the content aggregator (simplified for single source)
    result = await aggregator.aggregate_all_content()
    
    return {
        "source": source_name,
        "items_fetched": result.get('total_new_items', 0),
        "status": "success"
    }
