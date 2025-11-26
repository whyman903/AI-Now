from __future__ import annotations

import asyncio
import gc
import inspect
import logging
import os
import re
import shutil
import time
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser
import httpx
from dateutil import parser as dateparser
from sqlalchemy import or_

from app.core.config import settings
from app.crud.analytics import AnalyticsCRUD
from app.db.base import SessionLocal
from app.db.models import ContentItem, FeedState
from app.services.aggregation_sources import (
    anthropic_agg,
    deepmind_agg,
    deepseek_agg,
    dwarkesh_podcast_agg,
    huggingface_agg,
    moonshot_agg,
    nvidia_podcast_agg,
    openai_agg,
    perplexity_agg,
    qwen_agg,
    tavily_trending,
    thinkingmachines_agg,
    xai_agg,
)
from app.services.source_registry import SOURCES_BY_KEY

logger = logging.getLogger(__name__)


class ContentAggregator:
    """Aggregate content from multiple sources and load into the database."""

    def __init__(self) -> None:
        self.client: Optional[httpx.AsyncClient] = None
        self._per_host_limit = 4
        self._host_limiters: Dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(self._per_host_limit)
        )
        self._thumb_cache: OrderedDict[str, Optional[str]] = OrderedDict()
        self._thumb_cache_size = 256
        self._youtube_duration_cache: Dict[str, Optional[int]] = {}

        # Default batching + mode configuration
        self.low_memory_mode = False
        self.web_scraper_batch_size = 3
        self.youtube_batch_size = 4
        self.rss_batch_size = 6

        self._initialize_rss_sources()
        self._initialize_youtube_sources()
        self._selenium_enabled = self._detect_selenium_support()
        self._initialize_web_scraper_sources()

    def configure(self, *, low_memory: bool = False) -> None:
        """Adjust batching strategy for the next run."""

        if low_memory:
            self.low_memory_mode = True
            self.web_scraper_batch_size = 1
            self.youtube_batch_size = 2
            self.rss_batch_size = 3
        else:
            self.low_memory_mode = False
            self.web_scraper_batch_size = 3
            self.youtube_batch_size = 4
            self.rss_batch_size = 6

    def _source_config(self, source_key: str, **overrides: Any) -> Dict[str, Any]:
        definition = SOURCES_BY_KEY.get(source_key)
        if not definition:
            raise ValueError(f"Unknown source key '{source_key}'")
        config: Dict[str, Any] = {
            "source_key": definition.key,
            "name": definition.name,
            "category": definition.category,
        }
        if definition.content_types and "type" not in overrides:
            config["type"] = definition.content_types[0]
        config.update(overrides)
        return config

    def _detect_selenium_support(self) -> bool:
        if settings.DISABLE_SELENIUM_AGENTS:
            logger.warning("Selenium-based scrapers disabled via settings")
            return False

        chrome_candidates = [
            settings.CHROME_BINARY_PATH,
            os.environ.get("GOOGLE_CHROME_BIN"),
            os.environ.get("CHROME_BINARY"),
        ]
        for candidate in chrome_candidates:
            if candidate and os.path.exists(candidate):
                return True

        for binary in ("google-chrome", "chromium", "chromium-browser", "chrome"):
            if shutil.which(binary):
                return True

        logger.warning(
            "Chrome/Chromium binary not found; Selenium-based scrapers will be skipped."
        )
        return False

    def _initialize_rss_sources(self) -> None:
        self.rss_sources: List[Dict[str, Any]] = [
            self._source_config(
                "rss_sequoia_capital",
                url="https://www.sequoiacap.com/feed/",
            ),
        ]

    def _initialize_youtube_sources(self) -> None:
        self.youtube_channels: List[Dict[str, Any]] = [
            self._source_config("yt_openai", channel_id="UCXZCJLdBC09xxGZ6gcdrc6A"),
            self._source_config("yt_anthropic", channel_id="UCrDwWp7EBBv4NwvScIpBDOA"),
            self._source_config("yt_ai_engineer", channel_id="UCLKPca3kwwd-B59HNr-_lvA"),
            self._source_config("yt_google_deepmind", channel_id="UCP7jMXSY2xbc3KCAE0MHQ-A"),
            self._source_config("yt_andrej_karpathy", channel_id="UCXUPKJO5MZQN11PqgIvyuvQ"),
            self._source_config("yt_y_combinator", channel_id="UCcefcZRL2oaA_uBNeo5UOWg"),
            self._source_config("yt_sequoia_capital", channel_id="UCWrF0oN6unbXrWsTN7RctTw"),
            self._source_config("yt_a16z", channel_id="UC9cn0TuPq4dnbTY-CBsm8XA"),
        ]

    def _initialize_web_scraper_sources(self) -> None:
        configured_sources = [
            self._source_config("scrape_anthropic", scrape_func=anthropic_agg.scrape, requires_selenium=True),
            self._source_config("scrape_deepseek", scrape_func=deepseek_agg.scrape, requires_selenium=True),
            self._source_config("scrape_xai", scrape_func=xai_agg.scrape, requires_selenium=True),
            self._source_config("scrape_qwen", scrape_func=qwen_agg.scrape),
            self._source_config("scrape_moonshot", scrape_func=moonshot_agg.scrape, requires_selenium=True),
            self._source_config("scrape_openai", scrape_func=openai_agg.scrape, requires_selenium=True),
            self._source_config("scrape_google_deepmind", scrape_func=deepmind_agg.scrape),
            self._source_config("scrape_perplexity", scrape_func=perplexity_agg.scrape, requires_selenium=True),
            self._source_config("scrape_thinking_machines", scrape_func=thinkingmachines_agg.scrape),
            self._source_config(
                "scrape_hugging_face_papers",
                scrape_func=huggingface_agg.scrape_trending_papers,
                type="research_paper",
            ),
            self._source_config("scrape_tavily_trends", scrape_func=tavily_trending.scrape_async),
            self._source_config(
                "scrape_nvidia_podcast",
                scrape_func=nvidia_podcast_agg.scrape,
                type="podcast",
                requires_selenium=True,
            ),
            self._source_config(
                "scrape_dwarkesh_podcast",
                scrape_func=dwarkesh_podcast_agg.scrape,
                type="podcast",
                requires_selenium=True,
            ),
        ]

        skipped: List[str] = []
        self.web_scraper_sources = []
        for source in configured_sources:
            requires_selenium = source.pop("requires_selenium", False)
            if requires_selenium and not self._selenium_enabled:
                skipped.append(source["name"])
                continue
            self.web_scraper_sources.append(source)

        if skipped:
            logger.warning(
                "Skipping Selenium scrapers: %s (Chrome/Chromium binary unavailable)",
                ", ".join(skipped),
            )


    def set_http_client(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def _execute_source_groups(
        self,
        groups: List[Tuple[str, Callable[[], Awaitable[Dict[str, Any]]]]],
    ) -> List[Tuple[str, Any]]:
        if not groups:
            return []

        if self.low_memory_mode:
            logger.info(
                "Running %s source group(s) sequentially (low-memory mode)",
                len(groups),
            )
            outcomes: List[Tuple[str, Any]] = []
            for name, func in groups:
                try:
                    result = await func()
                except Exception as exc:  # pragma: no cover - logged below
                    result = exc
                outcomes.append((name, result))
                gc.collect()
            return outcomes

        tasks = [func() for _, func in groups]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        names = [name for name, _ in groups]
        return list(zip(names, responses, strict=False))

    async def aggregate_all_content(self) -> Dict[str, Any]:
        logger.info(
            "Starting unified content aggregation (low_memory=%s, web_batch=%s, yt_batch=%s, rss_batch=%s)...",
            self.low_memory_mode,
            self.web_scraper_batch_size,
            self.youtube_batch_size,
            self.rss_batch_size,
        )
        start = self._utcnow_naive()
        results: Dict[str, Any] = {
            "started_at": start.isoformat(),
            "sources": {},
            "total_new_items": 0,
            "total_items_updated": 0,
            "items_with_thumbnails": 0,
            "errors": [],
        }

        groups: List[Tuple[str, Callable[[], Awaitable[Dict[str, Any]]]]] = [
            ("rss_feeds", self._aggregate_rss_feeds),
            ("youtube_channels", self._aggregate_youtube_channels),
            ("web_scrapers", self._aggregate_web_scrapers),
        ]

        for name, outcome in await self._execute_source_groups(groups):
            if isinstance(outcome, Exception):
                msg = f"Error in {name}: {outcome}"
                logger.error(msg)
                results["errors"].append(msg)
                results["sources"][name] = {"error": str(outcome)}
                continue

            results["sources"][name] = outcome
            results["total_new_items"] += outcome.get("items_added", 0)
            results["total_items_updated"] += outcome.get("items_updated", 0)
            results["items_with_thumbnails"] += outcome.get("items_with_thumbnails", 0)

        end = self._utcnow_naive()
        results["completed_at"] = end.isoformat()
        results["duration_seconds"] = (end - start).total_seconds()
        logger.info(
            "Aggregation completed: %s new items in %.2fs",
            results["total_new_items"],
            results["duration_seconds"],
        )
        self._record_run_metrics(
            summary=results,
            context={"mode": "full", "low_memory": self.low_memory_mode},
        )
        return results

    async def aggregate_selective(self, rss: bool, youtube: bool, all_scrapers: bool, scrapers: Optional[List[str]]) -> Dict[str, Any]:
        start = self._utcnow_naive()
        logger.info(
            "Starting selective aggregation (rss=%s, youtube=%s, all_scrapers=%s, requested_scrapers=%s, low_memory=%s)",
            rss,
            youtube,
            all_scrapers,
            scrapers,
            self.low_memory_mode,
        )
        results = {
            "started_at": start.isoformat(),
            "sources": {},
            "total_new_items": 0,
            "total_items_updated": 0,
            "items_with_thumbnails": 0,
            "errors": [],
        }

        groups: List[Tuple[str, Callable[[], Awaitable[Dict[str, Any]]]]] = []
        if rss:
            groups.append(("rss_feeds", self._aggregate_rss_feeds))
        if youtube:
            groups.append(("youtube_channels", self._aggregate_youtube_channels))
        if all_scrapers:
            groups.append(("web_scrapers", self._aggregate_web_scrapers))
        elif scrapers:
            selected = [s for s in self.web_scraper_sources if s["name"] in scrapers]
            if selected:
                groups.append(("web_scrapers", lambda selected=selected: self._run_scrapers_batch(selected)))

        for name, outcome in await self._execute_source_groups(groups):
            if isinstance(outcome, Exception):
                results["errors"].append(f"{name}: {outcome}")
                results["sources"][name] = {"error": str(outcome)}
            else:
                results["sources"][name] = outcome
                results["total_new_items"] += outcome.get("items_added", 0)
                results["total_items_updated"] += outcome.get("items_updated", 0)
                results["items_with_thumbnails"] += outcome.get("items_with_thumbnails", 0)

        end = self._utcnow_naive()
        results["completed_at"] = end.isoformat()
        results["duration_seconds"] = (end - start).total_seconds()
        self._record_run_metrics(
            summary=results,
            context={
                "mode": "selective",
                "rss": rss,
                "youtube": youtube,
                "all_scrapers": all_scrapers,
                "scrapers": scrapers or [],
                "low_memory": self.low_memory_mode,
            },
        )
        return results
    
    async def _run_scrapers_batch(self, scrapers: List[Dict[str, Any]]) -> Dict[str, Any]:
        items_processed = items_added = items_with_thumbnails = items_updated = 0
        logger.info("Running targeted scraper batch with %s sources (batch_size=%s)", len(scrapers), self.web_scraper_batch_size)
        start = time.perf_counter()
        
        slow_scrapers = [s for s in scrapers if "Tavily" in s["name"]]
        fast_scrapers = [s for s in scrapers if "Tavily" not in s["name"]]
        
        slow_tasks: List[asyncio.Task[List[Dict[str, Any]]]] = []
        for source in slow_scrapers:
            logger.info(
                "Launching slow scraper %s as background task",
                source["name"],
            )
            slow_tasks.append(asyncio.create_task(self._process_web_scraper(source)))
        
        batch_size = self.web_scraper_batch_size
        total_batches = (len(fast_scrapers) + batch_size - 1) // batch_size if fast_scrapers else 0
        for i in range(0, len(fast_scrapers), batch_size):
            batch = fast_scrapers[i : i + batch_size]
            batch_names = ", ".join(source["name"] for source in batch)
            batch_index = (i // batch_size) + 1
            logger.info(
                "Running fast scraper batch %s/%s: %s",
                batch_index,
                total_batches,
                batch_names,
            )
            batch_start = time.perf_counter()
            tasks = [self._process_web_scraper(source) for source in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            batch_elapsed = time.perf_counter() - batch_start
            logger.info(
                "Fast scraper batch %s/%s finished in %.2fs",
                batch_index,
                total_batches,
                batch_elapsed,
            )
            
            for source_config, result in zip(batch, batch_results, strict=False):
                if isinstance(result, Exception):
                    logger.error("Scraper %s failed: %s", source_config["name"], result)
                    continue
                if not result:
                    continue
                
                items_processed += len(result)
                stats = await self._persist_items(result)
                items_added += stats.get("items_added", 0)
                items_with_thumbnails += stats.get("items_with_thumbnails", 0)
                items_updated += stats.get("items_updated", 0)
                logger.info(
                    "Processed %s: %s items, %s new",
                    source_config["name"],
                    len(result),
                    stats.get("items_added", 0),
                )
            
            if self.low_memory_mode:
                gc.collect()
        
        if slow_tasks:
            logger.info(
                "Waiting for slow scrapers to complete: %s",
                ", ".join(source["name"] for source in slow_scrapers),
            )
            slow_results = await asyncio.gather(*slow_tasks, return_exceptions=True)
            
            for source, result in zip(slow_scrapers, slow_results, strict=False):
                if isinstance(result, Exception):
                    logger.error("Scraper %s failed: %s", source["name"], result)
                    continue
                if result:
                    items_processed += len(result)
                    stats = await self._persist_items(result)
                    items_added += stats.get("items_added", 0)
                    items_with_thumbnails += stats.get("items_with_thumbnails", 0)
                    items_updated += stats.get("items_updated", 0)
                    logger.info(
                        "Processed %s: %s items, %s new",
                        source["name"],
                        len(result),
                        stats.get("items_added", 0),
                    )
        
        elapsed = time.perf_counter() - start
        logger.info(
            "Targeted scraper batch finished in %.2fs (processed=%s, added=%s, updated=%s)",
            elapsed,
            items_processed,
            items_added,
            items_updated,
        )
        return {
            "items_processed": items_processed,
            "items_added": items_added,
            "items_with_thumbnails": items_with_thumbnails,
            "items_updated": items_updated,
        }

    def _record_run_metrics(self, summary: Dict[str, Any], context: Dict[str, Any]) -> None:
        """Persist aggregation run metrics without interrupting callers."""

        db = None
        try:
            db = SessionLocal()
            AnalyticsCRUD.record_aggregation_run(db=db, summary=summary, context=context)
        except Exception:
            logger.exception(
                "Failed to record aggregation run metrics for start=%s",
                summary.get("started_at"),
            )
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass

    async def _aggregate_rss_feeds(self) -> Dict[str, Any]:
        logger.info("Aggregating RSS feeds...")
        start = time.perf_counter()
        items_processed = items_added = items_with_thumbnails = items_updated = 0

        batch_size = self.rss_batch_size
        logger.info("Total RSS sources queued: %s (batch_size=%s)", len(self.rss_sources), batch_size)
        total_batches = (len(self.rss_sources) + batch_size - 1) // batch_size if self.rss_sources else 0
        for i in range(0, len(self.rss_sources), batch_size):
            batch = self.rss_sources[i : i + batch_size]
            batch_names = ", ".join(feed["name"] for feed in batch)
            batch_index = (i // batch_size) + 1
            logger.info(
                "Running RSS batch %s/%s: %s",
                batch_index,
                total_batches,
                batch_names,
            )
            tasks = [self._process_rss_feed(feed) for feed in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            for feed_config, result in zip(batch, batch_results, strict=False):
                if isinstance(result, Exception):
                    logger.error("Error processing RSS feed %s: %s", feed_config["name"], result)
                    continue
                if not result:
                    continue
                items_processed += len(result)
                stats = await self._persist_items(result)
                items_added += stats.get("items_added", 0)
                items_with_thumbnails += stats.get("items_with_thumbnails", 0)
                items_updated += stats.get("items_updated", 0)
                logger.info(
                    "Processed %s RSS feed: %s entries, %s new",
                    feed_config["name"],
                    len(result),
                    stats.get("items_added", 0),
                )
            
            if self.low_memory_mode:
                gc.collect()

        elapsed = time.perf_counter() - start
        logger.info(
            "RSS aggregation finished in %.2fs (processed=%s, added=%s, updated=%s)",
            elapsed,
            items_processed,
            items_added,
            items_updated,
        )
        return {
            "items_processed": items_processed,
            "items_added": items_added,
            "items_with_thumbnails": items_with_thumbnails,
            "items_updated": items_updated,
        }

    async def _aggregate_youtube_channels(self) -> Dict[str, Any]:
        logger.info("Aggregating YouTube channels...")
        start = time.perf_counter()
        items_processed = items_added = items_with_thumbnails = items_updated = 0

        batch_size = self.youtube_batch_size
        logger.info("Total YouTube channels queued: %s (batch_size=%s)", len(self.youtube_channels), batch_size)
        total_batches = (len(self.youtube_channels) + batch_size - 1) // batch_size if self.youtube_channels else 0
        for i in range(0, len(self.youtube_channels), batch_size):
            batch = self.youtube_channels[i : i + batch_size]
            batch_names = ", ".join(channel["name"] for channel in batch)
            batch_index = (i // batch_size) + 1
            logger.info(
                "Running YouTube batch %s/%s: %s",
                batch_index,
                total_batches,
                batch_names,
            )
            tasks = [self._process_youtube_channel(channel) for channel in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for channel_config, result in zip(batch, batch_results, strict=False):
                if isinstance(result, Exception):
                    logger.error("Error processing YouTube channel %s: %s", channel_config["name"], result)
                    continue
                if not result:
                    continue
                
                items_processed += len(result)
                stats = await self._persist_items(result)
                items_added += stats.get("items_added", 0)
                items_with_thumbnails += stats.get("items_with_thumbnails", 0)
                items_updated += stats.get("items_updated", 0)
                logger.info(
                    "Processed YouTube channel %s: %s entries, %s new",
                    channel_config["name"],
                    len(result),
                    stats.get("items_added", 0),
                )
            
            if self.low_memory_mode:
                gc.collect()

        elapsed = time.perf_counter() - start
        logger.info(
            "YouTube aggregation finished in %.2fs (processed=%s, added=%s, updated=%s)",
            elapsed,
            items_processed,
            items_added,
            items_updated,
        )
        return {
            "items_processed": items_processed,
            "items_added": items_added,
            "items_with_thumbnails": items_with_thumbnails,
            "items_updated": items_updated,
        }

    async def _process_youtube_channel(self, channel: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process a single YouTube channel and return items."""
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel['channel_id']}"
        start = time.perf_counter()
        logger.info("Fetching YouTube channel %s (%s)", channel["name"], rss_url)
        try:
            response = await self._get(rss_url)
        except Exception as exc:
            elapsed = time.perf_counter() - start
            logger.error(
                "Error fetching YouTube channel %s after %.2fs: %s",
                channel["name"],
                elapsed,
                exc,
            )
            return []
        
        if response.status_code != 200:
            elapsed = time.perf_counter() - start
            logger.error(
                "Failed to fetch %s: HTTP %s in %.2fs",
                channel["name"],
                response.status_code,
                elapsed,
            )
            return []

        feed = feedparser.parse(response.text)
        channel_items: List[Dict[str, Any]] = []
        
        for entry in feed.entries[:10]:
            video_id = getattr(entry, "yt_videoid", None)
            if not video_id and hasattr(entry, "id") and isinstance(entry.id, str):
                parts = entry.id.split(":")
                if parts and parts[-1]:
                    video_id = parts[-1]
            
            duration_seconds: Optional[int] = None
            if video_id:
                duration_seconds = await self._fetch_youtube_duration(video_id)
            
            if duration_seconds is None:
                logger.debug(
                    "Skipping YouTube video %s from %s due to unknown duration",
                    video_id,
                    channel["name"],
                )
                continue
            
            if duration_seconds < 180:
                logger.debug(
                    "Skipping YouTube video %s from %s due to duration %s seconds",
                    video_id,
                    channel["name"],
                    duration_seconds,
                )
                continue
            
            thumb = None
            thumbs = getattr(entry, "media_thumbnail", None) or getattr(entry, "media_thumbnails", None)
            if thumbs and isinstance(thumbs, list) and thumbs[0].get("url"):
                thumb = thumbs[0]["url"]
            if not thumb and video_id:
                thumb = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

            published_at = self._utcnow_naive()
            if getattr(entry, "published_parsed", None):
                try:
                    published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).replace(tzinfo=None)
                except Exception:
                    pass
            source_key = channel.get("source_key")
            meta = {
                "source_name": channel["name"],
                "category": channel["category"],
                "video_id": video_id,
                "channel_id": channel["channel_id"],
                "duration_seconds": duration_seconds,
                "extraction_method": "youtube_rss",
            }
            if source_key:
                meta["source_key"] = source_key
            channel_items.append(
                {
                    "type": "youtube_video",
                    "title": entry.get("title"),
                    "url": entry.get("link"),
                    "author": channel["name"],
                    "published_at": published_at,
                    "thumbnail_url": thumb,
                    "source_key": source_key,
                    "meta_data": meta,
                }
            )
        elapsed = time.perf_counter() - start
        logger.info(
            "YouTube channel %s yielded %s videos in %.2fs",
            channel["name"],
            len(channel_items),
            elapsed,
        )

        return channel_items

    async def _fetch_youtube_duration(self, video_id: str) -> Optional[int]:
        if not video_id:
            return None
        if video_id in self._youtube_duration_cache:
            return self._youtube_duration_cache[video_id]

        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            response = await self._get(watch_url)
        except Exception as exc:
            logger.debug("Failed to fetch YouTube duration for %s: %s", video_id, exc)
            self._youtube_duration_cache[video_id] = None
            return None

        if response.status_code != 200:
            logger.debug(
                "YouTube watch page request failed for %s with HTTP %s",
                video_id,
                response.status_code,
            )
            self._youtube_duration_cache[video_id] = None
            return None

        text = response.text
        match = re.search(r'"lengthSeconds":"(\d+)"', text)
        duration: Optional[int]
        if match:
            duration = int(match.group(1))
        else:
            approx = re.search(r'"approxDurationMs":"(\d+)"', text)
            if approx:
                duration = int(approx.group(1)) // 1000
            else:
                duration = None

        if duration is not None and duration <= 0:
            duration = None

        self._youtube_duration_cache[video_id] = duration
        return duration

    async def _aggregate_web_scrapers(self) -> Dict[str, Any]:
        logger.info("Aggregating Selenium/BeautifulSoup sources...")
        start = time.perf_counter()
        items_processed = items_added = items_with_thumbnails = items_updated = 0

        slow_scrapers = [s for s in self.web_scraper_sources if "Tavily" in s["name"]]
        fast_scrapers = [s for s in self.web_scraper_sources if "Tavily" not in s["name"]]
        logger.info(
            "Total web scrapers queued: %s (batch_size=%s, low_memory=%s)",
            len(self.web_scraper_sources),
            self.web_scraper_batch_size,
            self.low_memory_mode,
        )
        logger.info(
            "Web scraper queue prepared: %s fast, %s slow",
            len(fast_scrapers),
            len(slow_scrapers),
        )
        
        slow_tasks: List[asyncio.Task[List[Dict[str, Any]]]] = []
        for source in slow_scrapers:
            logger.info(
                "Launching slow scraper %s as background task",
                source["name"],
            )
            slow_tasks.append(asyncio.create_task(self._process_web_scraper(source)))
        
        batch_size = self.web_scraper_batch_size
        total_batches = (len(fast_scrapers) + batch_size - 1) // batch_size if fast_scrapers else 0
        for i in range(0, len(fast_scrapers), batch_size):
            batch = fast_scrapers[i : i + batch_size]
            batch_names = ", ".join(source["name"] for source in batch)
            batch_index = (i // batch_size) + 1
            logger.info(
                "Running web scraper batch %s/%s: %s",
                batch_index,
                total_batches,
                batch_names,
            )
            batch_start = time.perf_counter()
            tasks = [self._process_web_scraper(source) for source in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            batch_elapsed = time.perf_counter() - batch_start
            logger.info(
                "Web scraper batch %s/%s finished in %.2fs",
                batch_index,
                total_batches,
                batch_elapsed,
            )
            
            for source_config, result in zip(batch, batch_results, strict=False):
                if isinstance(result, Exception):
                    logger.error("Error scraping %s: %s", source_config["name"], result)
                    continue
                if not result:
                    continue
                
                items_processed += len(result)
                stats = await self._persist_items(result)
                items_added += stats.get("items_added", 0)
                items_with_thumbnails += stats.get("items_with_thumbnails", 0)
                items_updated += stats.get("items_updated", 0)
                logger.info(
                    "Processed %s: %s items, %s new",
                    source_config["name"],
                    len(result),
                    stats.get("items_added", 0),
                )
            
            if self.low_memory_mode:
                gc.collect()
        
        if slow_tasks:
            logger.info(
                "Waiting for slow scrapers to complete: %s",
                ", ".join(source["name"] for source in slow_scrapers),
            )
            slow_results = await asyncio.gather(*slow_tasks, return_exceptions=True)
            
            for source, result in zip(slow_scrapers, slow_results, strict=False):
                if isinstance(result, Exception):
                    logger.error("Error scraping %s: %s", source["name"], result)
                    continue
                if result:
                    items_processed += len(result)
                    stats = await self._persist_items(result)
                    items_added += stats.get("items_added", 0)
                    items_with_thumbnails += stats.get("items_with_thumbnails", 0)
                    items_updated += stats.get("items_updated", 0)
                    logger.info(
                        "Processed %s: %s items, %s new",
                        source["name"],
                        len(result),
                        stats.get("items_added", 0),
                    )

        elapsed = time.perf_counter() - start
        logger.info(
            "Web scraper aggregation finished in %.2fs (processed=%s, added=%s, updated=%s)",
            elapsed,
            items_processed,
            items_added,
            items_updated,
        )
        return {
            "items_processed": items_processed,
            "items_added": items_added,
            "items_with_thumbnails": items_with_thumbnails,
            "items_updated": items_updated,
        }

    async def _process_web_scraper(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process a single web scraper and return normalized items."""
        name = source["name"]
        scrape = source["scrape_func"]
        
        start = time.perf_counter()
        logger.info("Starting scrape for %s", name)
        try:
            if inspect.iscoroutinefunction(scrape):
                raw_items = await scrape()
            else:
                raw_items = await asyncio.to_thread(scrape)
        except Exception as exc:
            elapsed = time.perf_counter() - start
            logger.error("Error scraping %s after %.2fs: %s", name, elapsed, exc)
            raise

        normalized: List[Dict[str, Any]] = []
        source_key = source.get("source_key")
        for item in raw_items or []:
            if not item or not item.get("title") or not item.get("url"):
                continue
            published_at = item.get("published_at") or self._utcnow_naive()
            if isinstance(published_at, datetime):
                published_at = self._to_utc_naive(published_at)
            meta_data = dict(item.get("meta_data", {}) or {})
            if source_key:
                meta_data.setdefault("source_key", source_key)
            meta_data.setdefault("source_name", source.get("name"))
            meta_data.setdefault("category", source.get("category"))
            normalized.append(
                {
                    "type": item.get("type", "article"),
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "author": item.get("author"),
                    "published_at": published_at,
                    "thumbnail_url": item.get("thumbnail_url"),
                    "source_key": source_key,
                    "meta_data": meta_data,
                }
            )

        elapsed = time.perf_counter() - start
        logger.info(
            "Finished scrape for %s: %s items in %.2fs",
            name,
            len(normalized),
            elapsed,
        )

        return normalized

    async def _process_rss_feed(self, feed_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        start = time.perf_counter()
        logger.info(
            "Fetching RSS feed %s (%s)",
            feed_config.get("name"),
            feed_config.get("url"),
        )

        headers: Dict[str, str] = {}
        db = SessionLocal()
        try:
            state = db.query(FeedState).filter(FeedState.feed_url == feed_config["url"]).first()
            if state:
                if state.etag:
                    headers["If-None-Match"] = state.etag
                if state.last_modified:
                    headers["If-Modified-Since"] = state.last_modified
        except Exception:
            pass
        finally:
            db.close()

        response = await self._get(feed_config["url"], headers=headers)
        if response.status_code == 304:
            self._update_feed_state(feed_config["url"], response)
            elapsed = time.perf_counter() - start
            logger.info(
                "RSS feed %s returned 304 (unchanged) in %.2fs",
                feed_config.get("name"),
                elapsed,
            )
            return []
        response.raise_for_status()
        self._update_feed_state(feed_config["url"], response)

        feed = feedparser.parse(response.text)
        items: List[Dict[str, Any]] = []
        for entry in feed.entries[:15]:
            title = entry.get("title")
            link = entry.get("link")
            if not title or not link:
                continue

            published_at = self._utcnow_naive()
            try:
                if getattr(entry, "published_parsed", None):
                    published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).replace(tzinfo=None)
            except Exception:
                pass

            thumb = None
            media = getattr(entry, "media_thumbnail", None) or getattr(entry, "media_content", None)
            if media and isinstance(media, list) and media[0].get("url"):
                thumb = media[0]["url"]

            source_key = feed_config.get("source_key")
            meta = {
                "source_name": feed_config.get("name"),
                "category": feed_config.get("category"),
                "extraction_method": "rss",
                "summary": entry.get("summary"),
            }
            if source_key:
                meta["source_key"] = source_key
            items.append(
                {
                    "type": feed_config.get("type", "article"),
                    "title": title,
                    "url": link,
                    "author": feed_config.get("name"),
                    "published_at": published_at,
                    "thumbnail_url": thumb,
                    "source_key": source_key,
                    "meta_data": meta,
                }
            )
        elapsed = time.perf_counter() - start
        logger.info(
            "RSS feed %s yielded %s items in %.2fs",
            feed_config.get("name"),
            len(items),
            elapsed,
        )
        return items

    def _update_feed_state(self, feed_url: str, response: httpx.Response) -> None:
        try:
            db = SessionLocal()
            state = db.query(FeedState).filter(FeedState.feed_url == feed_url).first()
            if not state:
                state = FeedState(feed_url=feed_url)
                db.add(state)
            state.etag = response.headers.get("ETag") or state.etag
            state.last_modified = response.headers.get("Last-Modified") or state.last_modified
            state.last_status = str(response.status_code)
            db.commit()
        except Exception:
            pass
        finally:
            db.close()

    async def _persist_items(self, items: List[Dict[str, Any]]) -> Dict[str, int]:
        if not items:
            return {"items_added": 0, "items_with_thumbnails": 0, "items_updated": 0}

        normalized: List[Dict[str, Any]] = []
        original_urls: Set[str] = set()
        for item in items:
            url = item.get("url")
            title = item.get("title")
            if not url or not title:
                continue
            url = self.canonicalize(url)
            published_at = self._resolve_published_at(item)
            if not published_at:
                published_at = self._utcnow_naive()
            meta_data = dict(item.get("meta_data", {}) or {})
            source_key = item.get("source_key") or meta_data.get("source_key")
            if source_key:
                meta_data["source_key"] = source_key
            original_url = meta_data.get("original_url")
            if original_url:
                canonical_original = self.canonicalize(original_url)
                meta_data["original_url"] = canonical_original
                original_urls.add(canonical_original)
            normalized.append(
                {
                    "type": item.get("type", "article"),
                    "title": title,
                    "url": url,
                    "author": item.get("author"),
                    "published_at": published_at,
                    "thumbnail_url": item.get("thumbnail_url"),
                    "source_key": source_key,
                    "meta_data": meta_data,
                }
            )

        if not normalized:
            return {"items_added": 0, "items_with_thumbnails": 0, "items_updated": 0}

        urls = [item["url"] for item in normalized]
        db = SessionLocal()
        try:
            filters = []
            if urls:
                filters.append(ContentItem.url.in_(urls))
            if original_urls:
                filters.append(
                    ContentItem.meta_data["original_url"].as_string().in_(list(original_urls))
                )
            query = db.query(ContentItem)
            if filters:
                if len(filters) == 1:
                    query = query.filter(filters[0])
                else:
                    query = query.filter(or_(*filters))
            existing_rows = query.all()

            existing_by_url: Dict[str, ContentItem] = {}
            existing_by_original: Dict[str, ContentItem] = {}
            survivors_by_original: Dict[str, ContentItem] = {}
            for row in existing_rows:
                canonical_url = self.canonicalize(row.url) if row.url else None
                if canonical_url and canonical_url not in existing_by_url:
                    existing_by_url[canonical_url] = row
                meta = row.meta_data or {}
                orig = meta.get("original_url")
                if isinstance(orig, str) and orig:
                    canonical_orig = self.canonicalize(orig)
                    existing_by_original.setdefault(canonical_orig, row)

            items_added = items_updated = items_with_thumbnails = 0
            for payload in normalized:
                meta = payload.get("meta_data") or {}
                original_key = meta.get("original_url")
                existing = existing_by_url.get(payload["url"])
                if not existing and original_key:
                    existing = existing_by_original.get(original_key)
                if existing:
                    changed = False
                    payload_source_key = payload.get("source_key")
                    if existing.url != payload["url"]:
                        old_url = existing.url
                        canonical_old_url = self.canonicalize(old_url) if old_url else None
                        if canonical_old_url and canonical_old_url in existing_by_url and existing_by_url[canonical_old_url] is existing:
                            del existing_by_url[canonical_old_url]
                        existing.url = payload["url"]
                        existing_by_url[payload["url"]] = existing
                        changed = True
                    if payload_source_key and existing.source_key != payload_source_key:
                        existing.source_key = payload_source_key
                        changed = True
                    new_published = payload.get("published_at")
                    if new_published and (
                        not getattr(existing, "published_at", None)
                        or existing.published_at != new_published
                    ):
                        existing.published_at = new_published
                        changed = True
                    if payload.get("author") and not existing.author:
                        existing.author = payload["author"]
                        changed = True
                    if payload.get("thumbnail_url") and not existing.thumbnail_url:
                        existing.thumbnail_url = payload["thumbnail_url"]
                        changed = True
                    if meta:
                        merged_meta = dict(existing.meta_data or {})
                        merged_meta.update(meta)
                        if payload_source_key:
                            merged_meta.setdefault("source_key", payload_source_key)
                        canonical_original = merged_meta.get("original_url")
                        if isinstance(canonical_original, str) and canonical_original:
                            canonical_original = self.canonicalize(canonical_original)
                            merged_meta["original_url"] = canonical_original
                            existing_by_original[canonical_original] = existing
                            survivors_by_original[canonical_original] = existing
                            original_key = canonical_original
                        existing.meta_data = merged_meta
                        changed = True
                    if changed:
                        items_updated += 1
                    if original_key:
                        survivors_by_original.setdefault(original_key, existing)
                    continue

                if not payload.get("thumbnail_url"):
                    thumb = await self._extract_thumbnail(payload["url"])
                    if thumb:
                        payload["thumbnail_url"] = thumb
                if payload.get("thumbnail_url"):
                    items_with_thumbnails += 1
                new_item = ContentItem(**payload)
                db.add(new_item)
                existing_by_url[payload["url"]] = new_item
                original_key = meta.get("original_url")
                if original_key:
                    existing_by_original[original_key] = new_item
                    survivors_by_original[original_key] = new_item
                items_added += 1

            if survivors_by_original:
                processed_keys = set(survivors_by_original.keys())
                for row in existing_rows:
                    meta = row.meta_data or {}
                    orig = meta.get("original_url")
                    if not isinstance(orig, str) or not orig:
                        continue
                    canonical_orig = self.canonicalize(orig)
                    if canonical_orig not in processed_keys:
                        continue
                    survivor = survivors_by_original.get(canonical_orig)
                    if survivor is None or survivor is row:
                        continue
                    db.delete(row)

            db.commit()
            return {
                "items_added": items_added,
                "items_with_thumbnails": items_with_thumbnails,
                "items_updated": items_updated,
            }
        finally:
            db.close()

    def canonicalize(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            scheme = (parsed.scheme or "https").lower()
            netloc = parsed.netloc.lower()
            if netloc.endswith(":80") and scheme == "http":
                netloc = netloc[:-3]
            if netloc.endswith(":443") and scheme == "https":
                netloc = netloc[:-4]
            path = parsed.path or "/"
            if path != "/" and path.endswith("/"):
                path = path[:-1]
            fragment = ""
            tracking = {
                "utm_source",
                "utm_medium",
                "utm_campaign",
                "utm_term",
                "utm_content",
                "gclid",
                "fbclid",
                "igshid",
                "mc_cid",
                "mc_eid",
                "ref",
                "ref_",
                "yclid",
            }
            query = urlencode([(k, v) for k, v in parse_qsl(parsed.query) if k not in tracking])
            return urlunparse((scheme, netloc, path, "", query, fragment))
        except Exception:
            return url

    async def _get(self, url: str, headers: Optional[Dict[str, str]] = None) -> httpx.Response:
        if not self.client:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as temp:
                return await temp.get(url, headers=headers)
        host = urlparse(url).netloc.lower()
        sem = self._host_limiters[host]
        async with sem:
            return await self.client.get(url, headers=headers)

    def _resolve_published_at(self, item: Dict[str, Any]) -> Optional[datetime]:
        dt = self._coerce_datetime(item.get("published_at"))
        if dt:
            return dt

        meta = item.get("meta_data") or {}
        for key in ("published_at", "date_iso", "date", "scraped_date", "date_display"):
            if key not in meta or not meta[key]:
                continue
            dt = self._coerce_datetime(meta[key])
            if dt:
                meta[key] = dt.isoformat()
                return dt
        return None

    def _coerce_datetime(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return self._to_utc_naive(value)
        if isinstance(value, (int, float)):
            try:
                return self._to_utc_naive(datetime.fromtimestamp(float(value), tz=timezone.utc))
            except Exception:
                return None
        if isinstance(value, str):
            try:
                dt = dateparser.parse(value)
            except Exception:
                return None
            if not dt:
                return None
            return self._to_utc_naive(dt)
        return None

    def _utcnow_naive(self) -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def _to_utc_naive(self, dt: datetime) -> datetime:
        try:
            if dt.tzinfo:
                return dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except Exception:
            return self._utcnow_naive()

    async def _extract_thumbnail(self, url: str) -> Optional[str]:
        if url in self._thumb_cache:
            value = self._thumb_cache.pop(url)
            self._thumb_cache[url] = value
            return value
        try:
            response = await self._get(url)
            if response.status_code != 200:
                return None
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(response.text, "html.parser")
            for tag in ("og:image", "twitter:image", "twitter:image:src"):
                meta = soup.find("meta", attrs={"property": tag}) or soup.find(
                    "meta", attrs={"name": tag}
                )
                if meta and meta.get("content"):
                    thumb = meta["content"]
                    self._thumb_cache[url] = thumb
                    if len(self._thumb_cache) > self._thumb_cache_size:
                        self._thumb_cache.popitem(last=False)
                    return thumb
            self._thumb_cache[url] = None
            if len(self._thumb_cache) > self._thumb_cache_size:
                self._thumb_cache.popitem(last=False)
            return None
        except Exception as exc:
            logger.debug("Failed extracting thumbnail from %s: %s", url, exc)
            return None


_aggregator: Optional[ContentAggregator] = None


def get_content_aggregator() -> ContentAggregator:
    global _aggregator
    if _aggregator is None:
        _aggregator = ContentAggregator()
    return _aggregator
