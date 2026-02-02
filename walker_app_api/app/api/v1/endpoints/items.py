from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from app.services.aggregation.aggregator import get_content_aggregator
from app.api.deps import require_aggregation_token
from app.services.aggregation.registry import (
    PluginSource,
    get_all_plugins,
    get_plugin,
)

LAB_FILTER_KEYS = {
    "scrape_anthropic",
    "scrape_google_deepmind",
    "scrape_openai",
    "scrape_xai",
    "scrape_qwen",
    "scrape_moonshot",
    "scrape_deepseek",
    "scrape_thinking_machines",
    "scrape_perplexity",
}

router = APIRouter()


def _slugify(name: str) -> str:
    return name.lower().replace(" ", "-")


def _channel_for_key(key: str) -> str:
    if key.startswith("rss_"):
        return "rss"
    if key.startswith("yt_"):
        return "youtube"
    return "scraper"


def _serialize_plugin(plugin: PluginSource) -> Dict[str, Any]:
    return {
        "key": plugin.key,
        "name": plugin.name,
        "channel": _channel_for_key(plugin.key),
        "category": plugin.category,
        "contentTypes": plugin.content_types,
        "defaultEnabled": True,
    }


@router.get("")
def get_content_sources():
    """Return all known aggregation sources."""
    plugins = get_all_plugins()
    return {
        "total": len(plugins),
        "sources": [_serialize_plugin(p) for p in plugins],
    }


@router.get("/sources", include_in_schema=False)
def get_content_sources_legacy():
    return get_content_sources()


@router.get("/status")
async def get_sources_status():
    """Get status of content aggregation."""
    return {
        "status": "active",
        "sources": len(get_all_plugins()),
    }


@router.get("/types")
def get_source_types():
    """Return available content types emitted by sources."""
    plugins = get_all_plugins()
    content_types = sorted(
        {ct for plugin in plugins for ct in plugin.content_types}
    )
    return {"types": content_types}


@router.post(
    "/refresh/{source_identifier}",
    dependencies=[Depends(require_aggregation_token)],
)
async def refresh_specific_source(source_identifier: str):
    """Manually refresh a specific source (by key or slug)."""
    identifier = source_identifier.lower()

    plugins = get_all_plugins()
    matched = next(
        (p for p in plugins if identifier in {p.key.lower(), _slugify(p.name)}),
        None,
    )

    if not matched:
        raise HTTPException(status_code=404, detail="Source not found.")

    aggregator = get_content_aggregator()
    result = await aggregator.aggregate_selective(
        rss=False, youtube=False, all_scrapers=False, scrapers=[matched.name],
    )
    return {
        "source": matched.key,
        "items_fetched": result.get("total_new_items", 0),
        "status": "success",
    }


@router.get("/filters/labs")
def get_lab_filters():
    """Return available lab-style sources for client-side filtering."""

    labs: List[Dict[str, Any]] = []
    for key in LAB_FILTER_KEYS:
        plugin = get_plugin(key)
        if not plugin:
            continue
        labs.append(
            {
                "id": _slugify(plugin.name),
                "label": plugin.name,
                "category": plugin.category,
                "source_type": _channel_for_key(plugin.key),
                "sourceKey": plugin.key,
            }
        )

    labs.sort(key=lambda entry: entry["label"].lower())
    return {"labs": labs}
