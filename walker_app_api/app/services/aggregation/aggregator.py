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

import httpx
from dateutil import parser as dateparser
from sqlalchemy import or_

from app.core.config import settings
from app.crud.analytics import AnalyticsCRUD
from app.db.base import SessionLocal
from app.db.models import AggregationSource, ContentItem
from app.services.aggregation.registry import (
    PluginSource,
    get_all_plugins,
    get_non_selenium_plugins,
    get_selenium_plugins,
)
from app.services.aggregation.user_source_engine import scrape_user_source

logger = logging.getLogger(__name__)


class ContentAggregator:
    """Aggregate content from plugin sources and persist into the database."""

    def __init__(self) -> None:
        self.client: Optional[httpx.AsyncClient] = None
        self._per_host_limit = 4
        self._host_limiters: Dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(self._per_host_limit)
        )
        self._thumb_cache: OrderedDict[str, Optional[str]] = OrderedDict()
        self._thumb_cache_size = 256

        self.low_memory_mode = False
        self.plugin_batch_size = 3

        self._selenium_enabled = self._detect_selenium_support()

    def configure(self, *, low_memory: bool = False) -> None:
        if low_memory:
            self.low_memory_mode = True
            self.plugin_batch_size = 1
        else:
            self.low_memory_mode = False
            self.plugin_batch_size = 3

    # ---- Source Counts ----

    @property
    def source_count(self) -> int:
        return len(get_all_plugins())

    @property
    def selenium_source_count(self) -> int:
        return len(get_selenium_plugins())

    @property
    def non_selenium_source_count(self) -> int:
        return len(get_non_selenium_plugins())

    # ---- Selenium Detection ----

    def _detect_selenium_support(self) -> bool:
        if settings.DISABLE_SELENIUM_AGENTS:
            logger.warning("Selenium-based scrapers disabled via settings")
            return False

        chrome_candidates = [
            settings.CHROME_BINARY_PATH,
            os.environ.get("GOOGLE_CHROME_BIN"),
            os.environ.get("CHROME_BINARY"),
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
        for candidate in chrome_candidates:
            if candidate and os.path.exists(candidate):
                logger.info("Found Chrome/Chromium at: %s", candidate)
                if not settings.CHROME_BINARY_PATH:
                    settings.CHROME_BINARY_PATH = candidate
                return True

        for binary in ("google-chrome", "chromium", "chromium-browser", "chrome", "google-chrome-stable"):
            path = shutil.which(binary)
            if path:
                logger.info("Found Chrome/Chromium in PATH: %s", path)
                if not settings.CHROME_BINARY_PATH:
                    settings.CHROME_BINARY_PATH = path
                return True

        logger.warning(
            "Chrome/Chromium binary not found; Selenium-based scrapers will be skipped."
        )
        return False

    # ---- HTTP Client ----

    def set_http_client(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def _get(self, url: str, headers: Optional[Dict[str, str]] = None) -> httpx.Response:
        if not self.client:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as temp:
                return await temp.get(url, headers=headers)
        host = urlparse(url).netloc.lower()
        sem = self._host_limiters[host]
        async with sem:
            return await self.client.get(url, headers=headers)

    # ---- Aggregation Orchestration ----

    async def aggregate_all_content(self) -> Dict[str, Any]:
        logger.info(
            "Starting content aggregation (low_memory=%s, batch_size=%s)...",
            self.low_memory_mode,
            self.plugin_batch_size,
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

        non_selenium = get_non_selenium_plugins()
        selenium = get_selenium_plugins() if self._selenium_enabled else []

        if not self._selenium_enabled and get_selenium_plugins():
            skipped = [p.name for p in get_selenium_plugins()]
            logger.warning(
                "Skipping Selenium scrapers: %s (Chrome/Chromium unavailable)",
                ", ".join(skipped),
            )

        all_plugins = non_selenium + selenium
        outcome = await self._run_plugin_batch(all_plugins)
        results["sources"]["plugins"] = outcome
        results["total_new_items"] += outcome.get("items_added", 0)
        results["total_items_updated"] += outcome.get("items_updated", 0)
        results["items_with_thumbnails"] += outcome.get("items_with_thumbnails", 0)

        # Run user-defined sources
        user_outcome = await self._run_user_sources()
        results["sources"]["user"] = user_outcome
        results["total_new_items"] += user_outcome.get("items_added", 0)
        results["total_items_updated"] += user_outcome.get("items_updated", 0)
        results["items_with_thumbnails"] += user_outcome.get("items_with_thumbnails", 0)

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

    async def aggregate_selective(
        self,
        rss: bool,
        youtube: bool,
        all_scrapers: bool,
        scrapers: Optional[List[str]],
    ) -> Dict[str, Any]:
        start = self._utcnow_naive()
        logger.info(
            "Starting selective aggregation (rss=%s, youtube=%s, all_scrapers=%s, scrapers=%s)",
            rss, youtube, all_scrapers, scrapers,
        )
        results: Dict[str, Any] = {
            "started_at": start.isoformat(),
            "sources": {},
            "total_new_items": 0,
            "total_items_updated": 0,
            "items_with_thumbnails": 0,
            "errors": [],
        }

        selected_plugins: List[PluginSource] = []
        all_available = get_all_plugins()

        if rss:
            selected_plugins.extend(p for p in all_available if p.key.startswith("rss_"))
        if youtube:
            selected_plugins.extend(p for p in all_available if p.key.startswith("yt_"))
        if all_scrapers:
            scraper_plugins = [
                p for p in all_available
                if p.key.startswith("scrape_")
                and (not p.requires_selenium or self._selenium_enabled)
            ]
            selected_plugins.extend(scraper_plugins)
        elif scrapers:
            name_set = set(scrapers)
            selected_plugins.extend(
                p for p in all_available
                if p.name in name_set
                and (not p.requires_selenium or self._selenium_enabled)
            )

        # Deduplicate
        seen_keys: set[str] = set()
        unique: List[PluginSource] = []
        for p in selected_plugins:
            if p.key not in seen_keys:
                unique.append(p)
                seen_keys.add(p.key)

        if unique:
            outcome = await self._run_plugin_batch(unique)
            results["sources"]["plugins"] = outcome
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

    async def _run_user_sources(self) -> Dict[str, Any]:
        """Scrape all enabled user-defined sources and persist results."""
        db = SessionLocal()
        try:
            sources = (
                db.query(AggregationSource)
                .filter(
                    AggregationSource.source_type == "user",
                    AggregationSource.enabled.is_(True),
                )
                .all()
            )
            # Eagerly access all attributes before closing the session to
            # avoid DetachedInstanceError if the ORM objects are used later.
            for s in sources:
                _ = s.key, s.url, s.selectors, s.name, s.category
                _ = s.content_types, s.url_prefix
                _ = s.extraction_method, s.feed_url
            db.expunge_all()
        finally:
            db.close()

        if not sources:
            return {"items_added": 0, "items_updated": 0, "items_with_thumbnails": 0, "sources_run": 0}

        logger.info("Running %s user-defined sources", len(sources))
        total_added = total_updated = total_thumbs = 0

        for source in sources:
            # Skip Selenium user sources when Chrome is not available
            method = getattr(source, "extraction_method", "css_selectors")
            if method == "selenium" and not self._selenium_enabled:
                logger.warning(
                    "Skipping user source %s (extraction_method=selenium, Chrome unavailable)",
                    source.key,
                )
                self._update_source_run_state(
                    source.key,
                    error="Selenium unavailable — Chrome/Chromium not found",
                )
                continue

            try:
                items = await asyncio.to_thread(scrape_user_source, source)
            except Exception as exc:
                logger.error("User source %s failed: %s", source.key, exc)
                self._update_source_run_state(source.key, error=str(exc))
                continue

            if items:
                # Inject source_key so items are filterable in the content API
                for item in items:
                    item["source_key"] = source.key
                    meta = item.get("meta_data")
                    if isinstance(meta, dict):
                        meta["source_key"] = source.key
                stats = await self._persist_items(items)
                total_added += stats.get("items_added", 0)
                total_updated += stats.get("items_updated", 0)
                total_thumbs += stats.get("items_with_thumbnails", 0)
                logger.info(
                    "User source %s: %s items, %s new",
                    source.key, len(items), stats.get("items_added", 0),
                )

            self._update_source_run_state(
                source.key,
                item_count=len(items) if items else 0,
            )

        return {
            "items_added": total_added,
            "items_updated": total_updated,
            "items_with_thumbnails": total_thumbs,
            "sources_run": len(sources),
        }

    def _update_source_run_state(
        self,
        key: str,
        *,
        item_count: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update run metadata on an AggregationSource row."""
        db = SessionLocal()
        try:
            source = db.query(AggregationSource).filter(AggregationSource.key == key).first()
            if not source:
                return
            source.last_run_at = self._utcnow_naive()
            source.run_count = (source.run_count or 0) + 1
            if item_count is not None:
                source.last_item_count = item_count
                source.last_error = None
                # Flag for refresh if selectors returned nothing
                if item_count == 0 and (source.run_count or 0) > 1:
                    source.needs_refresh = True
            if error:
                source.last_error = error
            db.commit()
        except Exception:
            logger.exception("Failed to update run state for source %s", key)
        finally:
            db.close()

    async def _run_plugin_batch(self, plugins: List[PluginSource]) -> Dict[str, Any]:
        items_processed = items_added = items_with_thumbnails = items_updated = 0
        batch_size = self.plugin_batch_size
        start = time.perf_counter()

        logger.info(
            "Running %s plugins (batch_size=%s, low_memory=%s)",
            len(plugins),
            batch_size,
            self.low_memory_mode,
        )

        # Separate slow scrapers (Tavily) to run concurrently with fast ones
        slow = [p for p in plugins if "tavily" in p.key.lower()]
        fast = [p for p in plugins if "tavily" not in p.key.lower()]

        slow_tasks: List[asyncio.Task[List[Dict[str, Any]]]] = []
        for plugin in slow:
            logger.info("Launching slow plugin %s as background task", plugin.name)
            slow_tasks.append(asyncio.create_task(self._run_single_plugin(plugin)))

        total_batches = (len(fast) + batch_size - 1) // batch_size if fast else 0
        for i in range(0, len(fast), batch_size):
            batch = fast[i : i + batch_size]
            batch_names = ", ".join(p.name for p in batch)
            batch_index = (i // batch_size) + 1
            logger.info("Running plugin batch %s/%s: %s", batch_index, total_batches, batch_names)

            batch_start = time.perf_counter()
            tasks = [self._run_single_plugin(p) for p in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            batch_elapsed = time.perf_counter() - batch_start
            logger.info("Plugin batch %s/%s finished in %.2fs", batch_index, total_batches, batch_elapsed)

            for plugin, result in zip(batch, batch_results, strict=False):
                if isinstance(result, Exception):
                    logger.error("Plugin %s failed: %s", plugin.name, result)
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
                    plugin.name, len(result), stats.get("items_added", 0),
                )

            if self.low_memory_mode:
                gc.collect()

        if slow_tasks:
            logger.info("Waiting for slow plugins: %s", ", ".join(p.name for p in slow))
            slow_results = await asyncio.gather(*slow_tasks, return_exceptions=True)
            for plugin, result in zip(slow, slow_results, strict=False):
                if isinstance(result, Exception):
                    logger.error("Plugin %s failed: %s", plugin.name, result)
                    continue
                if result:
                    items_processed += len(result)
                    stats = await self._persist_items(result)
                    items_added += stats.get("items_added", 0)
                    items_with_thumbnails += stats.get("items_with_thumbnails", 0)
                    items_updated += stats.get("items_updated", 0)
                    logger.info(
                        "Processed %s: %s items, %s new",
                        plugin.name, len(result), stats.get("items_added", 0),
                    )

        elapsed = time.perf_counter() - start
        logger.info(
            "Plugin batch finished in %.2fs (processed=%s, added=%s, updated=%s)",
            elapsed, items_processed, items_added, items_updated,
        )
        return {
            "items_processed": items_processed,
            "items_added": items_added,
            "items_with_thumbnails": items_with_thumbnails,
            "items_updated": items_updated,
        }

    async def _run_single_plugin(self, plugin: PluginSource) -> List[Dict[str, Any]]:
        name = plugin.name
        scrape = plugin.scrape_func
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
        for item in raw_items or []:
            if not item or not item.get("title") or not item.get("url"):
                continue
            published_at = item.get("published_at") or self._utcnow_naive()
            if isinstance(published_at, datetime):
                published_at = self._to_utc_naive(published_at)
            meta_data = dict(item.get("meta_data", {}) or {})
            source_key = item.get("source_key") or meta_data.get("source_key") or plugin.key
            meta_data.setdefault("source_key", source_key)
            meta_data.setdefault("source_name", plugin.name)
            meta_data.setdefault("category", plugin.category)
            normalized.append({
                "type": item.get("type", "article"),
                "title": item.get("title"),
                "url": item.get("url"),
                "author": item.get("author"),
                "published_at": published_at,
                "thumbnail_url": item.get("thumbnail_url"),
                "source_key": source_key,
                "meta_data": meta_data,
            })

        elapsed = time.perf_counter() - start
        logger.info("Finished scrape for %s: %s items in %.2fs", name, len(normalized), elapsed)
        return normalized

    # ---- Persistence ----

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
            normalized.append({
                "type": item.get("type", "article"),
                "title": title,
                "url": url,
                "author": item.get("author"),
                "published_at": published_at,
                "thumbnail_url": item.get("thumbnail_url"),
                "source_key": source_key,
                "meta_data": meta_data,
            })

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
                    if payload.get("thumbnail_url") and existing.thumbnail_url != payload["thumbnail_url"]:
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

    # ---- URL Canonicalization ----

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
                "utm_source", "utm_medium", "utm_campaign", "utm_term",
                "utm_content", "gclid", "fbclid", "igshid",
                "mc_cid", "mc_eid", "ref", "ref_", "yclid",
            }
            query = urlencode([(k, v) for k, v in parse_qsl(parsed.query) if k not in tracking])
            return urlunparse((scheme, netloc, path, "", query, fragment))
        except Exception:
            return url

    # ---- Date Helpers ----

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

    # ---- Thumbnail Extraction ----

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

    # ---- Metrics ----

    def _record_run_metrics(self, summary: Dict[str, Any], context: Dict[str, Any]) -> None:
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


_aggregator: Optional[ContentAggregator] = None


def get_content_aggregator() -> ContentAggregator:
    global _aggregator
    if _aggregator is None:
        _aggregator = ContentAggregator()
    return _aggregator
