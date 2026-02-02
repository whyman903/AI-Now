"""Programmatic RSS/Atom feed discovery for user-submitted URLs."""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 15.0
_USER_AGENT = "Mozilla/5.0 (compatible; WalkerApp/1.0; +https://walkerapp.com)"

# Common paths where blogs/sites expose RSS or Atom feeds.
_COMMON_FEED_PATHS = [
    "/feed",
    "/rss",
    "/rss.xml",
    "/atom.xml",
    "/feed.xml",
    "/blog/feed",
    "/blog/rss",
    "/blog/atom.xml",
    "/index.xml",
    "/feeds/posts/default",
]

_FEED_CONTENT_TYPES = frozenset({
    "application/rss+xml",
    "application/atom+xml",
    "application/xml",
    "text/xml",
})

_XML_FEED_MARKERS = (b"<rss", b"<feed", b"<channel", b"<atom:feed")


def _get_client() -> httpx.Client:
    return httpx.Client(
        timeout=_REQUEST_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
    )


def _looks_like_feed(content_type: str, body: bytes) -> bool:
    """Check if an HTTP response looks like an RSS/Atom feed."""
    ct = content_type.lower().split(";")[0].strip()
    if ct in _FEED_CONTENT_TYPES:
        return True
    # Some servers serve feeds as text/html — check body for XML feed markers.
    body_start = body[:2000].lower()
    return any(marker in body_start for marker in _XML_FEED_MARKERS)


def _discover_from_html(html: str, page_url: str) -> List[str]:
    """Extract RSS/Atom feed URLs from <link rel="alternate"> tags."""
    soup = BeautifulSoup(html, "html.parser")
    candidates: List[str] = []
    for link in soup.find_all("link", rel="alternate"):
        link_type = (link.get("type") or "").lower()
        if link_type in ("application/rss+xml", "application/atom+xml"):
            href = link.get("href")
            if href:
                candidates.append(urljoin(page_url, href.strip()))
    return candidates


def _probe_common_paths(page_url: str) -> List[str]:
    """Probe well-known feed paths and return those that respond with feed content."""
    candidates: List[str] = []
    with _get_client() as client:
        for path in _COMMON_FEED_PATHS:
            probe_url = urljoin(page_url, path)
            try:
                resp = client.head(probe_url)
                if resp.status_code < 400:
                    # Confirm with a partial GET
                    resp = client.get(probe_url, headers={"Range": "bytes=0-2000"})
                    if resp.status_code < 400 and _looks_like_feed(
                        resp.headers.get("content-type", ""), resp.content
                    ):
                        candidates.append(probe_url)
            except httpx.HTTPError:
                continue
    return candidates


def discover_feed_url(html: str, page_url: str) -> Optional[str]:
    """Discover the best RSS/Atom feed URL for *page_url*.

    1. Parse ``<link rel="alternate">`` tags from the provided HTML.
    2. Probe common feed paths (``/feed``, ``/rss.xml``, etc.).
    3. Validate each candidate with a real HTTP request.

    Returns the first valid feed URL, or ``None`` if no feed is found.
    """
    # Step 1: HTML link tags (most authoritative)
    candidates = _discover_from_html(html, page_url)

    # Step 2: Common path probing
    seen = set(candidates)
    for url in _probe_common_paths(page_url):
        if url not in seen:
            candidates.append(url)
            seen.add(url)

    # Step 3: Validate each candidate
    for url in candidates:
        is_valid, count, title = validate_feed(url)
        if is_valid and count > 0:
            logger.info("Discovered valid feed: %s (%d items, title=%r)", url, count, title)
            return url

    return None


def validate_feed(feed_url: str) -> Tuple[bool, int, Optional[str]]:
    """Fetch and parse *feed_url* with feedparser.

    Returns ``(is_valid, item_count, feed_title)``.
    """
    try:
        import feedparser
    except ImportError:
        logger.warning("feedparser not installed — cannot validate RSS feed")
        return False, 0, None

    try:
        with _get_client() as client:
            resp = client.get(feed_url)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.debug("Failed to fetch feed %s: %s", feed_url, exc)
        return False, 0, None

    feed = feedparser.parse(resp.text)

    if feed.bozo and not feed.entries:
        logger.debug("Feed %s is malformed and has no entries", feed_url)
        return False, 0, None

    title = feed.feed.get("title") if hasattr(feed, "feed") else None
    item_count = len(feed.entries)

    if item_count == 0:
        return False, 0, title

    return True, item_count, title
