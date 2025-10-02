from __future__ import annotations

import asyncio
import logging
import re
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser
import httpx
from dateutil import parser as dateparser
from sqlalchemy import or_

from app.db.base import SessionLocal
from app.db.models import ContentItem, FeedState
from app.services.aggregation_sources import (
    anthropic_agg,
    deepseek_agg,
    huggingface_agg,
    moonshot_agg,
    openai_agg,
    perplexity_agg,
    qwen_agg,
    thinkingmachines_agg,
    xai_agg,
)

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

        self._initialize_rss_sources()
        self._initialize_youtube_sources()
        self._initialize_web_scraper_sources()

    def _initialize_rss_sources(self) -> None:
        self.rss_sources: List[Dict[str, Any]] = [
            # {"name": "OpenAI Blog", "url": "https://openai.com/blog/rss.xml", "category": "ai_ml", "type": "blog"},
           # {"name": "Google AI Blog", "url": "https://research.google/blog/rss", "category": "ai_ml", "type": "blog"},
            {"name": "Google DeepMind", "url": "https://deepmind.google/blog/rss.xml", "category": "ai_ml", "type": "research_lab"},
            #{"name": "Microsoft Research", "url": "https://www.microsoft.com/en-us/research/feed/", "category": "ai_ml", "type": "blog"},
            # {"name": "NVIDIA Developer Blog", "url": "https://developer.nvidia.com/blog/feed/", "category": "ai_ml", "type": "blog"},
            #{"name": "Y Combinator Podcast", "url": "https://www.ycombinator.com/blog/feed/", "category": "startup", "type": "podcast"},
           # {"name": "Sequoia Capital", "url": "https://www.sequoiacap.com/feed/", "category": "startup", "type": "blog"},
        ]

    def _initialize_youtube_sources(self) -> None:
        self.youtube_channels: List[Dict[str, Any]] = [
            # {"name": "3Blue1Brown", "channel_id": "UCYO_jab_esuFRV4b17AJtAw", "category": "ai_ml"},
            # {"name": "Two Minute Papers", "channel_id": "UCbfYPyITQ-7l4upoX8nvctg", "category": "ai_ml"},
            # {"name": "Yannic Kilcher", "channel_id": "UCZHmQk67mSJgfCCTn7xBfew", "category": "ai_ml"},
            # {"name": "AI Explained", "channel_id": "UCNJ1Ymd5yFuUPtn21xtRbbw", "category": "ai_ml"},
            # {"name": "Machine Learning Street Talk", "channel_id": "UCMLtBahI5DMrt0NPvDSoIRQ", "category": "ai_ml"},
            # {"name": "Lex Fridman", "channel_id": "UCSHZKyawb77ixDdsGog4iWA", "category": "ai_ml"},
            {"name": "OpenAI", "channel_id": "UCXZCJLdBC09xxGZ6gcdrc6A", "category": "ai_ml"},
            {"name": "Anthropic", "channel_id": "UCrDwWp7EBBv4NwvScIpBDOA", "category": "ai_ml"},
            {"name": "AI Engineer", "channel_id": "UCLKPca3kwwd-B59HNr-_lvA", "category": "ai_ml"},
            {"name": "Google DeepMind", "channel_id": "UCP7jMXSY2xbc3KCAE0MHQ-A", "category": "ai_ml"},
            {"name": "Andrej Karpathy", "channel_id": "UCXUPKJO5MZQN11PqgIvyuvQ", "category": "ai_ml"},
            # {"name": "Y Combinator", "channel_id": "UCcefcZRL2oaA_uBNeo5UOWg", "category": "startup"},
        ]

    def _initialize_web_scraper_sources(self) -> None:
        self.web_scraper_sources: List[Dict[str, Any]] = [
            {"name": "Anthropic", "category": "ai_ml", "scrape_func": anthropic_agg.scrape},
            {"name": "DeepSeek", "category": "ai_ml", "scrape_func": deepseek_agg.scrape},
            {"name": "xAI", "category": "ai_ml", "scrape_func": xai_agg.scrape},
            {"name": "Qwen", "category": "ai_ml", "scrape_func": qwen_agg.scrape},
            {"name": "Moonshot", "category": "ai_ml", "scrape_func": moonshot_agg.scrape},
            {"name": "OpenAI", "category": "ai_ml", "scrape_func": openai_agg.scrape},
            {"name": "Perplexity", "category": "ai_ml", "scrape_func": perplexity_agg.scrape},
            {
                "name": "Thinking Machines",
                "category": "ai_ml",
                "scrape_func": thinkingmachines_agg.scrape,
            },
            {"name": "Hugging Face Papers", "category": "ai_ml", "scrape_func": huggingface_agg.scrape_trending_papers},
        ]


    def set_http_client(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def aggregate_all_content(self) -> Dict[str, Any]:
        logger.info("Starting unified content aggregation...")
        start = self._utcnow_naive()
        results: Dict[str, Any] = {
            "started_at": start.isoformat(),
            "sources": {},
            "total_new_items": 0,
            "total_items_updated": 0,
            "items_with_thumbnails": 0,
            "errors": [],
        }

        tasks = [
            self._aggregate_rss_feeds(),
            self._aggregate_youtube_channels(),
            self._aggregate_web_scrapers(),
        ]

        source_names = ["rss_feeds", "youtube_channels", "web_scrapers"]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        for name, outcome in zip(source_names, responses, strict=False):
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
        return results

    async def _aggregate_rss_feeds(self) -> Dict[str, Any]:
        logger.info("Aggregating RSS feeds...")
        items_processed = items_added = items_with_thumbnails = items_updated = 0

        batch_size = 6
        for i in range(0, len(self.rss_sources), batch_size):
            batch = self.rss_sources[i : i + batch_size]
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

        return {
            "items_processed": items_processed,
            "items_added": items_added,
            "items_with_thumbnails": items_with_thumbnails,
            "items_updated": items_updated,
        }

    async def _aggregate_youtube_channels(self) -> Dict[str, Any]:
        logger.info("Aggregating YouTube channels...")
        items_processed = items_added = items_with_thumbnails = items_updated = 0

        for channel in self.youtube_channels:
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel['channel_id']}"
            try:
                response = await self._get(rss_url)
            except Exception as exc:
                logger.error("Error fetching YouTube channel %s: %s", channel["name"], exc)
                continue
            if response.status_code != 200:
                logger.error(
                    "Failed to fetch %s: HTTP %s",
                    channel["name"],
                    response.status_code,
                )
                continue

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

                channel_items.append(
                    {
                        "type": "youtube_video",
                        "title": entry.get("title"),
                        "url": entry.get("link"),
                        "author": channel["name"],
                        "published_at": published_at,
                        "thumbnail_url": thumb,
                        "meta_data": {
                            "source_name": channel["name"],
                            "category": channel["category"],
                            "video_id": video_id,
                            "channel_id": channel["channel_id"],
                            "duration_seconds": duration_seconds,
                            "extraction_method": "youtube_rss",
                        },
                    }
                )

            items_processed += len(channel_items)
            stats = await self._persist_items(channel_items)
            items_added += stats.get("items_added", 0)
            items_with_thumbnails += stats.get("items_with_thumbnails", 0)
            items_updated += stats.get("items_updated", 0)
            logger.info(
                "Processed YouTube channel %s: %s entries, %s new",
                channel["name"],
                len(channel_items),
                stats.get("items_added", 0),
            )

        return {
            "items_processed": items_processed,
            "items_added": items_added,
            "items_with_thumbnails": items_with_thumbnails,
            "items_updated": items_updated,
        }

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
        items_processed = items_added = items_with_thumbnails = items_updated = 0

        for source in self.web_scraper_sources:
            name = source["name"]
            scrape: Callable[[], List[Dict[str, Any]]] = source["scrape_func"]
            try:
                raw_items = await asyncio.to_thread(scrape)
            except Exception as exc:
                logger.error("Error scraping %s: %s", name, exc)
                continue

            normalized: List[Dict[str, Any]] = []
            for item in raw_items or []:
                if not item or not item.get("title") or not item.get("url"):
                    continue
                published_at = item.get("published_at") or self._utcnow_naive()
                if isinstance(published_at, datetime):
                    published_at = self._to_utc_naive(published_at)
                normalized.append(
                    {
                        "type": item.get("type", "article"),
                        "title": item.get("title"),
                        "url": item.get("url"),
                        "author": item.get("author"),
                        "published_at": published_at,
                        "thumbnail_url": item.get("thumbnail_url"),
                        "meta_data": item.get("meta_data", {}),
                    }
                )

            if not normalized:
                continue

            items_processed += len(normalized)
            stats = await self._persist_items(normalized)
            items_added += stats.get("items_added", 0)
            items_with_thumbnails += stats.get("items_with_thumbnails", 0)
            items_updated += stats.get("items_updated", 0)
            logger.info(
                "Processed %s: %s items, %s new",
                name,
                len(normalized),
                stats.get("items_added", 0),
            )

        return {
            "items_processed": items_processed,
            "items_added": items_added,
            "items_with_thumbnails": items_with_thumbnails,
            "items_updated": items_updated,
        }

    async def _process_rss_feed(self, feed_config: Dict[str, Any]) -> List[Dict[str, Any]]:
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

            items.append(
                {
                    "type": feed_config.get("type", "article"),
                    "title": title,
                    "url": link,
                    "author": entry.get("author") or feed_config.get("name"),
                    "published_at": published_at,
                    "thumbnail_url": thumb,
                    "meta_data": {
                        "source_name": feed_config.get("name"),
                        "category": feed_config.get("category"),
                        "extraction_method": "rss",
                        "summary": entry.get("summary"),
                    },
                }
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
                    if existing.url != payload["url"]:
                        old_url = existing.url
                        canonical_old_url = self.canonicalize(old_url) if old_url else None
                        if canonical_old_url and canonical_old_url in existing_by_url and existing_by_url[canonical_old_url] is existing:
                            del existing_by_url[canonical_old_url]
                        existing.url = payload["url"]
                        existing_by_url[payload["url"]] = existing
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
                # Store normalized ISO string back so we keep the useful metadata
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
