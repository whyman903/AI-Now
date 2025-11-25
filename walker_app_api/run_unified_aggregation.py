#!/usr/bin/env python3
import argparse
import asyncio
import sys
import os
import json
import resource
from dotenv import load_dotenv
import httpx

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=dotenv_path)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.base import create_tables, SessionLocal, ensure_content_items_compat_schema
from app.db.models import ContentItem
from app.services.content_aggregator import get_content_aggregator

SCRAPER_MAP = {
    'anthropic': 'Anthropic', 'deepseek': 'DeepSeek', 'xai': 'xAI', 'qwen': 'Qwen',
    'moonshot': 'Moonshot', 'openai': 'OpenAI', 'perplexity': 'Perplexity',
    'thinking_machines': 'Thinking Machines', 'huggingface': 'Hugging Face Papers',
    'tavily_trending': 'Tavily AI Trends', 'nvidia_podcast': 'NVIDIA AI Podcast',
    'dwarkesh_podcast': 'Dwarkesh Podcast',
}

async def main():
    parser = argparse.ArgumentParser(description="Run content aggregation")
    parser.add_argument('--rss', action='store_true')
    parser.add_argument('--youtube', action='store_true')
    parser.add_argument('--scrapers', action='store_true')
    parser.add_argument('--low-memory', action='store_true',
                       help='Run in low-memory mode (sequential + reduced batch sizes).')
    parser.add_argument('--memory-stats', action='store_true',
                       help='Print RSS memory usage (MB) before/after aggregation (posix only).')
    for key in SCRAPER_MAP:
        parser.add_argument(f'--{key}', action='store_true')
    
    args = parser.parse_args()
    scrapers = [SCRAPER_MAP[k] for k, v in vars(args).items() if k in SCRAPER_MAP and v]
    run_all = not any([v for k, v in vars(args).items() if k in ['rss', 'youtube', 'scrapers'] + list(SCRAPER_MAP.keys())])
    
    print(f"Running: {'ALL' if run_all else ', '.join([k for k, v in vars(args).items() if v and k not in ['low_memory', 'memory_stats']])}")
    print(f"Low-memory mode: {args.low_memory}")
    if args.memory_stats and sys.platform == 'win32':
        print("[mem] WARNING: resource.ru_maxrss is not supported on Windows; skipping memory stats.")
        args.memory_stats = False
    print("=" * 70)

    def _print_memory(label: str) -> None:
        if not args.memory_stats:
            return
        try:
            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if sys.platform == 'darwin':
                usage_mb = usage / (1024 * 1024)
            else:
                usage_mb = usage / 1024
            print(f"[mem] {label}: {usage_mb:.1f} MB RSS")
        except Exception as exc:
            print(f"[mem] {label}: unable to determine memory usage ({exc})")

    try:
        create_tables()
        ensure_content_items_compat_schema()
    except Exception as e:
        print(f"WARN: {e}")

    _print_memory("baseline")
    client = httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers={'User-Agent': 'AI-Now/1.0'})
    aggregator = get_content_aggregator()
    aggregator.configure(low_memory=args.low_memory)
    print(
        f"Batches -> web={aggregator.web_scraper_batch_size}, youtube={aggregator.youtube_batch_size}, rss={aggregator.rss_batch_size}"
    )
    aggregator.set_http_client(client)

    try:
        if run_all:
            results = await aggregator.aggregate_all_content()
        else:
            results = await aggregator.aggregate_selective(
                args.rss, args.youtube, args.scrapers, scrapers or None
            )
        _print_memory("after aggregation")

        print("\nResults:", json.dumps(results, indent=2))

        db = SessionLocal()
        try:
            total = db.query(ContentItem).count()
            with_thumbs = db.query(ContentItem).filter(ContentItem.thumbnail_url.isnot(None)).count()
            print(f"\nDB: {total} items, {with_thumbs} with thumbnails ({with_thumbs/total*100:.1f}%)")
        finally:
            db.close()
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        _print_memory("shutdown")
        await client.aclose()

if __name__ == "__main__":
    asyncio.run(main())
