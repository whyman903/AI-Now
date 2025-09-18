#!/usr/bin/env python3
import asyncio
import sys
import os
import json
from dotenv import load_dotenv
import httpx

# Load .env next to this script
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=dotenv_path)

# Ensure app imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.base import create_tables, SessionLocal, ensure_content_items_compat_schema
from app.db.models import ContentItem
from app.services.content_aggregator import get_content_aggregator


async def main():
    print("Starting unified content aggregation...")
    print("=" * 70)

    # Ensure tables exist (idempotent)
    try:
        create_tables()
        ensure_content_items_compat_schema()
    except Exception as e:
        print(f"WARN: create_tables/ensure schema failed or skipped: {e}")

    # Prepare shared HTTP client and inject
    client = httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers={'User-Agent': 'TrendCurate/1.0'})
    aggregator = get_content_aggregator()
    aggregator.set_http_client(client)

    try:
        results = await aggregator.aggregate_all_content()
        print("\nAggregation Results Summary:")
        print(json.dumps(results, indent=2))

        # Final database stats
        db = SessionLocal()
        try:
            total_items = db.query(ContentItem).count()
            with_thumbs = db.query(ContentItem).filter(ContentItem.thumbnail_url.isnot(None)).count()
            print("\nFinal Database Stats:")
            print(f"   Total items: {total_items}")
            print(f"   Items with thumbnails: {with_thumbs}")
            if total_items:
                print(f"   Overall thumbnail coverage: {with_thumbs/total_items*100:.1f}%")
        finally:
            db.close()

        print("\nUnified aggregation completed successfully!")
    except Exception as e:
        print(f"ERROR: Error during aggregation: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
