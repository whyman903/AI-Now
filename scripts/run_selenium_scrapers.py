#!/usr/bin/env python3
"""Run Selenium-based scrapers and POST results to the Render ingest endpoint.

Designed to run in GitHub Actions where Chrome is pre-installed with sufficient
memory (7 GB). Results are sent to the /api/v1/aggregation/ingest endpoint on
the Render backend for persistence.
"""

import json
import os
import sys
from datetime import datetime

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "walker_app_api"))

from app.services.aggregation_sources import (  # noqa: E402
    anthropic_agg,
    dwarkesh_podcast_agg,
    moonshot_agg,
    nvidia_podcast_agg,
    openai_agg,
    perplexity_agg,
    xai_agg,
)

BACKEND_URL = os.environ["BACKEND_URL"]
TOKEN = os.environ["AGGREGATION_SERVICE_TOKEN"]
INGEST_URL = f"{BACKEND_URL}/api/v1/aggregation/ingest"

SCRAPERS = [
    ("scrape_anthropic", anthropic_agg.scrape),
    ("scrape_openai", openai_agg.scrape),
    ("scrape_xai", xai_agg.scrape),
    ("scrape_perplexity", perplexity_agg.scrape),
    ("scrape_moonshot", moonshot_agg.scrape),
    ("scrape_nvidia_podcast", nvidia_podcast_agg.scrape),
    ("scrape_dwarkesh_podcast", dwarkesh_podcast_agg.scrape),
]


class _DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def _serialize_items(items):
    return json.loads(json.dumps(items, cls=_DateTimeEncoder))


def _ingest(source_key: str, items: list) -> dict:
    payload = {"source_key": source_key, "items": _serialize_items(items)}
    resp = httpx.post(
        INGEST_URL,
        json=payload,
        headers={
            "X-Aggregation-Token": TOKEN,
            "Content-Type": "application/json",
        },
        timeout=120.0,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    results = {}
    failures = []

    for source_key, scrape_func in SCRAPERS:
        print(f"[{source_key}] Scraping...")
        try:
            items = scrape_func()
            print(f"[{source_key}] Got {len(items)} items")
        except Exception as exc:
            print(f"[{source_key}] Scrape failed: {exc}")
            failures.append(source_key)
            continue

        if not items:
            results[source_key] = {"scraped": 0, "added": 0, "updated": 0}
            continue

        try:
            resp = _ingest(source_key, items)
            results[source_key] = {
                "scraped": len(items),
                "added": resp.get("items_added", 0),
                "updated": resp.get("items_updated", 0),
            }
            print(f"[{source_key}] Ingested: added={resp.get('items_added')}, updated={resp.get('items_updated')}")
        except Exception as exc:
            print(f"[{source_key}] Ingest failed: {exc}")
            failures.append(source_key)

    print("\n--- Summary ---")
    for key, stats in results.items():
        print(f"  {key}: scraped={stats['scraped']}, added={stats['added']}, updated={stats['updated']}")
    if failures:
        print(f"  FAILED: {', '.join(failures)}")
        sys.exit(1)
    print("All scrapers completed successfully.")


if __name__ == "__main__":
    main()
