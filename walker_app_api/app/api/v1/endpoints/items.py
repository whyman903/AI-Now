from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any
from app.services.content_aggregator import get_content_aggregator

LAB_FILTER_WHITELIST = {
    "Anthropic",
    "Google DeepMind",
    "OpenAI",
    "xAI",
    "Qwen",
    "Moonshot",
    "DeepSeek",
    "Thinking Machines",
}

router = APIRouter()
aggregator = get_content_aggregator()


def _slugify(name: str) -> str:
    return name.lower().replace(" ", "-")

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


@router.get("/filters/labs")
def get_lab_filters():
    """Return available lab-style sources for client-side filtering."""

    combined_sources = (
        aggregator.web_scraper_sources
        + aggregator.youtube_channels
        + aggregator.rss_sources
    )

    seen = set()
    labs = []
    for source in combined_sources:
        label = source.get("name")
        if not label or label not in LAB_FILTER_WHITELIST:
            continue
        if not label or label in seen:
            continue
        seen.add(label)
        labs.append(
            {
                "id": _slugify(label),
                "label": label,
                "category": source.get("category"),
                "source_type": source.get("type") or source.get("category"),
            }
        )

    labs.sort(key=lambda entry: entry["label"].lower())
    return {"labs": labs}
