"""Scrape a user-defined source using stored CSS selectors, RSS, or Selenium."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from app.db.models import AggregationSource
from .utils.html import make_item

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 20.0
_MAX_RSS_ENTRIES = 30
_USER_AGENT = (
    "Mozilla/5.0 (compatible; WalkerApp/1.0; +https://walkerapp.com)"
)


def _fetch_html(url: str) -> str:
    """Fetch *url* and return the response body as text."""
    with httpx.Client(
        timeout=_REQUEST_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text


def _resolve_url(href: Optional[str], base_url: str, url_prefix: Optional[str] = None) -> Optional[str]:
    """Turn a potentially relative *href* into an absolute URL."""
    if not href:
        return None
    href = href.strip()
    if href.startswith(("http://", "https://")):
        return href
    prefix = url_prefix or base_url
    return urljoin(prefix, href)


def _first_srcset_url(srcset: Optional[str]) -> Optional[str]:
    """Extract the first URL from a srcset attribute value."""
    if not srcset:
        return None
    first = srcset.split(",")[0].strip()
    return first.split()[0] if first else None


def _parse_date(text: Optional[str]) -> Optional[datetime]:
    """Best-effort date parsing, returning a naive UTC datetime."""
    if not text:
        return None
    try:
        dt = dateparser.parse(text, fuzzy=True)
    except Exception:
        return None
    if dt is None:
        return None
    if dt.tzinfo:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _get_content_type(source: AggregationSource) -> str:
    """Resolve the primary content type for a source."""
    if source.content_types:
        types = source.content_types if isinstance(source.content_types, list) else [source.content_types]
        if types:
            return types[0]
    return "article"


# ---------------------------------------------------------------------------
# Shared CSS extraction helper
# ---------------------------------------------------------------------------

def _extract_items_from_soup(
    soup: BeautifulSoup,
    source: AggregationSource,
    extraction_method: str,
) -> List[Dict[str, Any]]:
    """Extract items from *soup* using the CSS selectors stored on *source*.

    This shared helper is used by both the CSS and Selenium paths to avoid
    duplicating the title/url/date/thumbnail/author extraction logic.
    """
    selectors: Dict[str, Any] = source.selectors or {}
    container_sel = selectors.get("item_container")
    title_sel = selectors.get("title")
    url_sel = selectors.get("url")

    if not container_sel or not title_sel or not url_sel:
        logger.warning(
            "User source %s missing required selectors (item_container/title/url)",
            source.key,
        )
        return []

    containers = soup.select(container_sel)
    if not containers:
        logger.info("User source %s: no containers matched '%s'", source.key, container_sel)
        return []

    content_type = _get_content_type(source)
    base_url = source.url or ""
    items: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()

    for container in containers:
        title_el = container.select_one(title_sel)
        url_el = container.select_one(url_sel)

        title = title_el.get_text(strip=True) if title_el else None
        raw_href = url_el.get("href") if url_el else None

        if not title:
            continue

        resolved = _resolve_url(raw_href, base_url, source.url_prefix)
        if not resolved:
            continue

        if resolved in seen_urls:
            continue
        seen_urls.add(resolved)

        published_at: Optional[datetime] = None
        if selectors.get("date"):
            date_el = container.select_one(selectors["date"])
            if date_el:
                date_text = date_el.get("datetime") or date_el.get_text(strip=True)
                published_at = _parse_date(date_text)

        thumbnail_url: Optional[str] = None
        if selectors.get("thumbnail"):
            thumb_el = container.select_one(selectors["thumbnail"])
            if thumb_el:
                raw_thumb = thumb_el.get("src") or _first_srcset_url(thumb_el.get("srcset"))
                thumbnail_url = _resolve_url(raw_thumb, base_url, source.url_prefix)

        author: Optional[str] = None
        if selectors.get("author"):
            author_el = container.select_one(selectors["author"])
            if author_el:
                author = author_el.get_text(strip=True) or None

        items.append(
            make_item(
                title=title,
                url=resolved,
                author=author or source.name,
                published_at=published_at,
                thumbnail_url=thumbnail_url,
                item_type=content_type,
                source_name=source.name,
                extraction_method=extraction_method,
                extra_meta={"category": source.category},
            )
        )

    return items


# ---------------------------------------------------------------------------
# Method-specific scrapers
# ---------------------------------------------------------------------------

def _scrape_with_css_selectors(source: AggregationSource) -> List[Dict[str, Any]]:
    """Fetch HTML and apply CSS selectors (the original approach)."""
    selectors = source.selectors or {}
    if not selectors.get("item_container") or not selectors.get("title") or not selectors.get("url"):
        logger.warning(
            "User source %s missing required selectors (item_container/title/url)",
            source.key,
        )
        return []

    html = _fetch_html(source.url)
    soup = BeautifulSoup(html, "html.parser")
    return _extract_items_from_soup(soup, source, "user_css_selectors")


def _scrape_rss(source: AggregationSource) -> List[Dict[str, Any]]:
    """Fetch and parse the source's RSS/Atom feed."""
    feed_url = getattr(source, "feed_url", None)
    if not feed_url:
        logger.warning("User source %s has extraction_method=rss but no feed_url", source.key)
        return []

    try:
        import feedparser
    except ImportError:
        logger.error("feedparser not installed — cannot scrape RSS source %s", source.key)
        return []

    with httpx.Client(
        timeout=_REQUEST_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        resp = client.get(feed_url)
        resp.raise_for_status()

    feed = feedparser.parse(resp.text)
    content_type = _get_content_type(source)
    items: List[Dict[str, Any]] = []

    for entry in feed.entries[:_MAX_RSS_ENTRIES]:
        title = entry.get("title")
        link = entry.get("link")
        if not title or not link:
            continue

        published_at: Optional[datetime] = None
        for date_field in ("published_parsed", "updated_parsed"):
            time_struct = entry.get(date_field)
            if time_struct:
                try:
                    published_at = datetime(*time_struct[:6])
                except Exception:
                    pass
                break
        if not published_at:
            for date_str_field in ("published", "updated"):
                raw_date = entry.get(date_str_field)
                if raw_date:
                    published_at = _parse_date(raw_date)
                    if published_at:
                        break

        author = entry.get("author")

        thumbnail_url: Optional[str] = None
        media = entry.get("media_thumbnail")
        if media and isinstance(media, list) and media[0].get("url"):
            thumbnail_url = media[0]["url"]
        elif entry.get("media_content"):
            for mc in entry.get("media_content", []):
                if mc.get("url") and mc.get("medium") == "image":
                    thumbnail_url = mc["url"]
                    break

        items.append(
            make_item(
                title=title,
                url=link,
                author=author or source.name,
                published_at=published_at,
                thumbnail_url=thumbnail_url,
                item_type=content_type,
                source_name=source.name,
                extraction_method="user_rss",
                extra_meta={"category": source.category},
            )
        )

    return items


def _scrape_with_selenium(source: AggregationSource) -> List[Dict[str, Any]]:
    """Render the page with Chrome and then apply CSS selectors."""
    try:
        from .utils.webdriver import create_chrome_driver, autoscroll_page
    except ImportError:
        logger.error("Selenium/webdriver dependencies not available for source %s", source.key)
        return []

    driver = None
    try:
        driver = create_chrome_driver()
        driver.get(source.url)
        autoscroll_page(driver, max_attempts=10)
        page_source = driver.page_source
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    soup = BeautifulSoup(page_source, "html.parser")
    return _extract_items_from_soup(soup, source, "user_selenium")


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------

def scrape_user_source(source: AggregationSource) -> List[Dict[str, Any]]:
    """Scrape a user source using the appropriate extraction method.

    Dispatches to RSS, Selenium, or CSS selector scraping based on
    ``source.extraction_method``.
    """
    if not source.url and not getattr(source, "feed_url", None):
        logger.warning("User source %s has no URL configured", source.key)
        return []

    method = getattr(source, "extraction_method", "css_selectors")

    if method == "rss":
        items = _scrape_rss(source)
    elif method == "selenium":
        items = _scrape_with_selenium(source)
    else:
        items = _scrape_with_css_selectors(source)

    logger.info("User source %s (%s): extracted %s items", source.key, method, len(items))
    return items
