"""YouTube channel scraper plugin via RSS feeds."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import feedparser
import httpx

from app.services.aggregation.registry import register

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(30.0)

_duration_cache: Dict[str, Optional[int]] = {}


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fetch_youtube_duration(video_id: str, client: httpx.Client) -> Optional[int]:
    if not video_id:
        return None
    if video_id in _duration_cache:
        return _duration_cache[video_id]

    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        response = client.get(watch_url, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        logger.debug("Failed to fetch YouTube duration for %s: %s", video_id, exc)
        _duration_cache[video_id] = None
        return None

    if response.status_code != 200:
        _duration_cache[video_id] = None
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

    _duration_cache[video_id] = duration
    return duration


def _scrape_youtube_channel(
    *,
    channel_id: str,
    source_name: str,
    source_key: str,
    category: str,
    max_entries: int = 10,
    min_duration: int = 180,
) -> List[Dict[str, Any]]:
    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

    try:
        response = httpx.get(rss_url, timeout=TIMEOUT, follow_redirects=True)
    except httpx.HTTPError as exc:
        logger.error("Failed to fetch YouTube channel %s: %s", source_name, exc)
        return []

    if response.status_code != 200:
        logger.error("YouTube channel %s returned HTTP %s", source_name, response.status_code)
        return []

    feed = feedparser.parse(response.text)
    items: List[Dict[str, Any]] = []

    with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
        for entry in feed.entries[:max_entries]:
            video_id = getattr(entry, "yt_videoid", None)
            if not video_id and hasattr(entry, "id") and isinstance(entry.id, str):
                parts = entry.id.split(":")
                if parts and parts[-1]:
                    video_id = parts[-1]

            duration_seconds: Optional[int] = None
            if video_id:
                duration_seconds = _fetch_youtube_duration(video_id, client)

            if duration_seconds is None:
                logger.debug(
                    "Skipping YouTube video %s from %s (unknown duration)",
                    video_id,
                    source_name,
                )
                continue

            if duration_seconds < min_duration:
                logger.debug(
                    "Skipping YouTube video %s from %s (duration %ss < %ss)",
                    video_id,
                    source_name,
                    duration_seconds,
                    min_duration,
                )
                continue

            thumb = None
            thumbs = getattr(entry, "media_thumbnail", None) or getattr(
                entry, "media_thumbnails", None
            )
            if thumbs and isinstance(thumbs, list) and thumbs[0].get("url"):
                thumb = thumbs[0]["url"]
            if not thumb and video_id:
                thumb = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

            published_at = _utcnow_naive()
            if getattr(entry, "published_parsed", None):
                try:
                    published_at = datetime(
                        *entry.published_parsed[:6], tzinfo=timezone.utc
                    ).replace(tzinfo=None)
                except Exception:
                    pass

            meta: Dict[str, Any] = {
                "source_name": source_name,
                "source_key": source_key,
                "category": category,
                "video_id": video_id,
                "channel_id": channel_id,
                "duration_seconds": duration_seconds,
                "extraction_method": "youtube_rss",
            }

            items.append({
                "type": "youtube_video",
                "title": entry.get("title"),
                "url": entry.get("link"),
                "author": source_name,
                "published_at": published_at,
                "thumbnail_url": thumb,
                "source_key": source_key,
                "meta_data": meta,
            })

    logger.info("YouTube channel %s yielded %s videos", source_name, len(items))
    return items


# --- Registered YouTube sources ---

@register(
    key="yt_openai",
    name="OpenAI",
    category="frontier_model",
    content_types=["youtube_video"],
)
def scrape_openai() -> List[Dict[str, Any]]:
    return _scrape_youtube_channel(
        channel_id="UCXZCJLdBC09xxGZ6gcdrc6A",
        source_name="OpenAI",
        source_key="yt_openai",
        category="frontier_model",
    )


@register(
    key="yt_anthropic",
    name="Anthropic",
    category="frontier_model",
    content_types=["youtube_video"],
)
def scrape_anthropic() -> List[Dict[str, Any]]:
    return _scrape_youtube_channel(
        channel_id="UCrDwWp7EBBv4NwvScIpBDOA",
        source_name="Anthropic",
        source_key="yt_anthropic",
        category="frontier_model",
    )


@register(
    key="yt_ai_engineer",
    name="AI Engineer",
    category="learning",
    content_types=["youtube_video"],
)
def scrape_ai_engineer() -> List[Dict[str, Any]]:
    return _scrape_youtube_channel(
        channel_id="UCLKPca3kwwd-B59HNr-_lvA",
        source_name="AI Engineer",
        source_key="yt_ai_engineer",
        category="learning",
    )


@register(
    key="yt_google_deepmind",
    name="Google DeepMind",
    category="frontier_model",
    content_types=["youtube_video"],
)
def scrape_google_deepmind() -> List[Dict[str, Any]]:
    return _scrape_youtube_channel(
        channel_id="UCP7jMXSY2xbc3KCAE0MHQ-A",
        source_name="Google DeepMind",
        source_key="yt_google_deepmind",
        category="frontier_model",
    )


@register(
    key="yt_andrej_karpathy",
    name="Andrej Karpathy",
    category="learning",
    content_types=["youtube_video"],
)
def scrape_andrej_karpathy() -> List[Dict[str, Any]]:
    return _scrape_youtube_channel(
        channel_id="UCXUPKJO5MZQN11PqgIvyuvQ",
        source_name="Andrej Karpathy",
        source_key="yt_andrej_karpathy",
        category="learning",
    )


@register(
    key="yt_y_combinator",
    name="Y Combinator",
    category="venture",
    content_types=["youtube_video"],
)
def scrape_y_combinator() -> List[Dict[str, Any]]:
    return _scrape_youtube_channel(
        channel_id="UCcefcZRL2oaA_uBNeo5UOWg",
        source_name="Y Combinator",
        source_key="yt_y_combinator",
        category="venture",
    )


@register(
    key="yt_sequoia_capital",
    name="Sequoia Capital",
    category="venture",
    content_types=["youtube_video"],
)
def scrape_sequoia_capital() -> List[Dict[str, Any]]:
    return _scrape_youtube_channel(
        channel_id="UCWrF0oN6unbXrWsTN7RctTw",
        source_name="Sequoia Capital",
        source_key="yt_sequoia_capital",
        category="venture",
    )


@register(
    key="yt_a16z",
    name="A16Z",
    category="venture",
    content_types=["youtube_video"],
)
def scrape_a16z() -> List[Dict[str, Any]]:
    return _scrape_youtube_channel(
        channel_id="UC9cn0TuPq4dnbTY-CBsm8XA",
        source_name="A16Z",
        source_key="yt_a16z",
        category="venture",
    )
