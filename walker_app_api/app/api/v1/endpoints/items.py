from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from app.services.content_aggregator import get_content_aggregator
from app.api.deps import require_aggregation_token
from app.services.source_registry import SourceDefinition, list_sources, SOURCES_BY_KEY

LAB_FILTER_KEYS = {
    "scrape_anthropic",
    "rss_google_deepmind",
    "scrape_openai",
    "scrape_xai",
    "scrape_qwen",
    "scrape_moonshot",
    "scrape_deepseek",
    "scrape_thinking_machines",
    "scrape_perplexity",
}

router = APIRouter()
aggregator = get_content_aggregator()


def _slugify(name: str) -> str:
    return name.lower().replace(" ", "-")

def _serialize_source(definition: SourceDefinition) -> Dict[str, Any]:
    return {
        "key": definition.key,
        "name": definition.name,
        "channel": definition.channel,
        "category": definition.category,
        "contentTypes": definition.content_types,
        "defaultEnabled": definition.default_enabled,
    }

def _all_source_configs() -> List[Dict[str, Any]]:
    return (
        aggregator.rss_sources
        + aggregator.youtube_channels
        + aggregator.web_scraper_sources
    )


@router.get("")
def get_content_sources():
    """Return all known aggregation sources."""
    definitions = list_sources()
    return {
        "total": len(definitions),
        "sources": [_serialize_source(defn) for defn in definitions],
    }


@router.get("/sources", include_in_schema=False)
def get_content_sources_legacy():
    return get_content_sources()


@router.get("/status")
async def get_sources_status():
    """Get status of content aggregation."""
    return {
        "status": "active",
        "sources": len(_all_source_configs()),
    }


@router.get("/types")
def get_source_types():
    """Return available content types emitted by sources."""
    definitions = list_sources()
    content_types = sorted(
        {value for definition in definitions for value in definition.content_types}
    )
    return {"types": content_types}

@router.post(
    "/refresh/{source_identifier}",
    dependencies=[Depends(require_aggregation_token)],
)
async def refresh_specific_source(source_identifier: str):
    """Manually refresh a specific source (by key or slug)."""
    identifier = source_identifier.lower()

    def _matches(source: Dict[str, Any]) -> bool:
        key = source.get("source_key", "").lower()
        name_slug = _slugify(source.get("name", ""))
        return identifier in {key, name_slug}

    sources = _all_source_configs()
    source = next((s for s in sources if _matches(s)), None)

    if not source:
        raise HTTPException(status_code=404, detail="Source not found.")

    # For now, refresh executes a full aggregation cycle.
    result = await aggregator.aggregate_all_content()
    return {
        "source": source.get("source_key") or source.get("name"),
        "items_fetched": result.get("total_new_items", 0),
        "status": "success",
    }


@router.get("/filters/labs")
def get_lab_filters():
    """Return available lab-style sources for client-side filtering."""

    labs: List[Dict[str, Any]] = []
    for key in LAB_FILTER_KEYS:
        definition = SOURCES_BY_KEY.get(key)
        if not definition:
            continue
        labs.append(
            {
                "id": _slugify(definition.name),
                "label": definition.name,
                "category": definition.category,
                "source_type": definition.channel,
                "sourceKey": definition.key,
            }
        )

    labs.sort(key=lambda entry: entry["label"].lower())
    return {"labs": labs}
