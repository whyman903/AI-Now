"""Thinking Machines blog scraper plugin."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.services.aggregation.registry import register
from app.services.aggregation.utils.date_parser import parse_date
from app.services.aggregation.utils.html import make_item, normalize_whitespace

BASE_URL = "https://thinkingmachines.ai"
LISTING_URL = f"{BASE_URL}/blog/"
THUMBNAIL_URL = "/static/images/thinking-machines-brand.png"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Referer": BASE_URL,
}
TIMEOUT = httpx.Timeout(15.0)

logger = logging.getLogger(__name__)


def _absolute_url(url: str) -> str:
    if not url:
        return url
    return urljoin(BASE_URL, url)


def _fetch_html(client: httpx.Client, url: str) -> str:
    response = client.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return response.text


def _extract_article_details(
    client: httpx.Client, article_url: str
) -> tuple[Optional[datetime], Optional[str], Optional[str]]:
    try:
        html = _fetch_html(client, article_url)
    except httpx.HTTPError as exc:
        logger.warning("Thinking Machines: failed fetching %s: %s", article_url, exc)
        return None, None, None

    soup = BeautifulSoup(html, "html.parser")

    published_iso = None
    date_meta = soup.select_one('meta[itemprop="datePublished"]')
    if date_meta and date_meta.get("content"):
        published_iso = date_meta["content"].strip()

    summary = None
    description_meta = soup.select_one('meta[name="description"]') or soup.select_one(
        'meta[property="og:description"]'
    )
    if description_meta and description_meta.get("content"):
        summary = normalize_whitespace(description_meta["content"])

    article_image = None
    thumb_meta = soup.select_one('meta[property="og:image"]')
    if thumb_meta and thumb_meta.get("content"):
        article_image = _absolute_url(thumb_meta["content"].strip())

    published_at = parse_date(published_iso)

    return published_at, summary, article_image


@register(
    key="scrape_thinking_machines",
    name="Thinking Machines",
    category="frontier_model",
    content_types=["article"],
)
def scrape() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        listing_html = _fetch_html(client, LISTING_URL)
        soup = BeautifulSoup(listing_html, "html.parser")

        for anchor in soup.select("a.post-item-link"):
            href = anchor.get("href")
            url = _absolute_url(href) if href else None
            if not url:
                continue

            title_el = anchor.select_one(".post-title")
            title = normalize_whitespace(title_el.get_text()) if title_el else None
            if not title:
                continue

            date_text_el = anchor.select_one("time.desktop-time") or anchor.select_one("time")
            date_text = normalize_whitespace(date_text_el.get_text()) if date_text_el else None

            published_at, summary, article_image = _extract_article_details(client, url)

            date_display = None
            if published_at:
                try:
                    date_display = published_at.strftime("%b %d, %Y")
                except Exception:
                    date_display = None

            extra_meta: Dict[str, Any] = {}
            if summary:
                extra_meta["summary"] = summary
            if article_image:
                extra_meta["article_image"] = article_image
            if date_text and not date_display:
                extra_meta["listing_date_text"] = date_text

            items.append(
                make_item(
                    title=title,
                    url=url,
                    author="Thinking Machines",
                    source_name="Thinking Machines",
                    extraction_method="httpx",
                    published_at=published_at,
                    thumbnail_url=THUMBNAIL_URL,
                    date_iso=published_at.isoformat() if isinstance(published_at, datetime) else None,
                    date_display=date_display,
                    extra_meta=extra_meta or None,
                )
            )

    return items
