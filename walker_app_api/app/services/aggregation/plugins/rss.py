"""Generic RSS feed scraper plugin."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import feedparser
import httpx

from app.db.base import SessionLocal
from app.db.models import FeedState
from app.services.aggregation.registry import register

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(30.0)


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _scrape_rss_feed(
    *,
    feed_url: str,
    source_name: str,
    source_key: str,
    category: str,
    item_type: str = "article",
    max_entries: int = 15,
) -> List[Dict[str, Any]]:
    headers: Dict[str, str] = {}
    db = SessionLocal()
    try:
        state = db.query(FeedState).filter(FeedState.feed_url == feed_url).first()
        if state:
            if state.etag:
                headers["If-None-Match"] = state.etag
            if state.last_modified:
                headers["If-Modified-Since"] = state.last_modified
    except Exception:
        pass
    finally:
        db.close()

    try:
        response = httpx.get(feed_url, headers=headers, timeout=TIMEOUT, follow_redirects=True)
    except httpx.HTTPError as exc:
        logger.error("Failed to fetch RSS feed %s: %s", source_name, exc)
        return []

    if response.status_code == 304:
        _update_feed_state(feed_url, response)
        logger.info("RSS feed %s returned 304 (unchanged)", source_name)
        return []

    if response.status_code != 200:
        logger.error("RSS feed %s returned HTTP %s", source_name, response.status_code)
        return []

    _update_feed_state(feed_url, response)

    feed = feedparser.parse(response.text)
    items: List[Dict[str, Any]] = []

    for entry in feed.entries[:max_entries]:
        title = entry.get("title")
        link = entry.get("link")
        if not title or not link:
            continue

        published_at = _utcnow_naive()
        try:
            if getattr(entry, "published_parsed", None):
                published_at = datetime(
                    *entry.published_parsed[:6], tzinfo=timezone.utc
                ).replace(tzinfo=None)
        except Exception:
            pass

        thumb = None
        media = getattr(entry, "media_thumbnail", None) or getattr(entry, "media_content", None)
        if media and isinstance(media, list) and media[0].get("url"):
            thumb = media[0]["url"]

        meta: Dict[str, Any] = {
            "source_name": source_name,
            "source_key": source_key,
            "category": category,
            "extraction_method": "rss",
            "summary": entry.get("summary"),
        }

        items.append({
            "type": item_type,
            "title": title,
            "url": link,
            "author": source_name,
            "published_at": published_at,
            "thumbnail_url": thumb,
            "source_key": source_key,
            "meta_data": meta,
        })

    return items


def _update_feed_state(feed_url: str, response: httpx.Response) -> None:
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


# --- Registered RSS sources ---

@register(
    key="rss_sequoia_capital",
    name="Sequoia Capital",
    category="venture",
    content_types=["blog"],
)
def scrape_sequoia() -> List[Dict[str, Any]]:
    return _scrape_rss_feed(
        feed_url="https://www.sequoiacap.com/feed/",
        source_name="Sequoia Capital",
        source_key="rss_sequoia_capital",
        category="venture",
        item_type="blog",
    )
