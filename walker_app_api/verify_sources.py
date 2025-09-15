#!/usr/bin/env python3
"""
Verify all content sources without writing to the database.
Checks:
- RSS feeds (feedparser)
- YouTube channels via RSS
- Firecrawl-backed scrapers (Anthropic, Qwen, HF Papers)
- BeautifulSoup Hugging Face trending PDF collector

Results are printed as JSON for easy inspection.
"""

import os
import sys
import json
import asyncio
from typing import Any, Dict, List

import httpx
import feedparser
from dotenv import load_dotenv


def _load_env():
    # Ensure we don't touch the real DB
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    # Load project .env for API keys
    dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)


async def verify_rss(client: httpx.AsyncClient, sources: List[Dict[str, Any]]):
    results = []
    for src in sources:
        name, url = src["name"], src["url"]
        try:
            r = await client.get(url)
            status = r.status_code
            if status == 200:
                feed = feedparser.parse(r.text)
                entries = len(feed.entries)
                results.append({"name": name, "url": url, "ok": entries > 0, "status": status, "entries": entries})
            else:
                results.append({"name": name, "url": url, "ok": False, "status": status, "error": f"HTTP {status}"})
        except Exception as e:
            results.append({"name": name, "url": url, "ok": False, "error": str(e)})
    return results


async def verify_youtube(client: httpx.AsyncClient, channels: List[Dict[str, Any]]):
    results = []
    for ch in channels:
        name = ch["name"]
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={ch['channel_id']}"
        try:
            r = await client.get(rss_url)
            status = r.status_code
            if status == 200:
                feed = feedparser.parse(r.text)
                entries = len(feed.entries)
                results.append({"name": name, "rss": rss_url, "ok": entries > 0, "status": status, "entries": entries})
            else:
                results.append({"name": name, "rss": rss_url, "ok": False, "status": status, "error": f"HTTP {status}"})
        except Exception as e:
            results.append({"name": name, "rss": rss_url, "ok": False, "error": str(e)})
    return results


async def verify_firecrawl(sources: List[Dict[str, Any]]):
    # Lazy import to avoid DB config on module import time
    from app.services.firecrawl_service import FirecrawlService
    fc = FirecrawlService()
    if not fc.firecrawl:
        return {"firecrawl_available": False, "error": "Firecrawl not initialized (missing or invalid API key)"}

    per_source = []
    for src in sources:
        try:
            arts = await fc.extract_articles_from_page(src["url"], src)
            per_source.append({
                "name": src["name"],
                "url": src["url"],
                "ok": len(arts) > 0,
                "items": len(arts)
            })
        except Exception as e:
            per_source.append({
                "name": src["name"],
                "url": src["url"],
                "ok": False,
                "error": str(e)
            })
    return {"firecrawl_available": True, "sources": per_source}


async def verify_hf_bs4():
    # Test BeautifulSoup-based HF trending collector
    try:
        from huggingface_agg import gather_pdfs
        pdfs = await gather_pdfs(limit=5, concurrency=5)
        return {"ok": len(pdfs) > 0, "pdf_count": len(pdfs)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def main():
    _load_env()

    # Avoid importing aggregator until env is set
    from app.services.content_aggregator_firecrawl import ContentAggregatorFirecrawl

    ag = ContentAggregatorFirecrawl()

    # Shared HTTP client
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers={'User-Agent': 'SourceVerifier/1.0'}) as client:
        rss_res = await verify_rss(client, ag.rss_sources)
        yt_res = await verify_youtube(client, ag.youtube_channels)

    fc_res = await verify_firecrawl(ag.web_scraper_sources)
    hf_res = await verify_hf_bs4()

    out = {
        "rss": rss_res,
        "youtube": yt_res,
        "firecrawl": fc_res,
        "huggingface_bs4": hf_res,
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

