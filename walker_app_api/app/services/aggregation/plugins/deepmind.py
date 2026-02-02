"""Google DeepMind blog scraper plugin."""
from typing import Any, Dict, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from app.services.aggregation.registry import register
from app.services.aggregation.utils.date_parser import parse_date
from app.services.aggregation.utils.html import make_item, normalize_whitespace

BASE = "https://deepmind.google"
INDEX_URL = "https://deepmind.google/blog/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def _parse_date_text(text: str):
    if not text:
        return None, None
    disp = normalize_whitespace(text)
    if not disp:
        return None, None
    try:
        dt = dateparser.parse(disp, fuzzy=True)
        return dt.isoformat(), disp
    except Exception:
        return None, disp


def _absolutize(url: str) -> str:
    if not url:
        return url
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return urljoin(BASE, url)
    return url if url.startswith(("http://", "https://")) else urljoin(INDEX_URL, url)


def _extract_articles(html: str):
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    seen = set()

    for article in soup.select("article.card.card-blog"):
        title_node = article.select_one("h3.card__title")
        title = normalize_whitespace(title_node.get_text(strip=True)) if title_node else None
        if not title:
            continue

        link_node = article.select_one("a[href]")
        if not link_node:
            continue

        url = _absolutize(link_node.get("href"))
        if url in seen:
            continue
        seen.add(url)

        time_node = article.select_one("time[datetime]")
        date_iso = None
        date_display = None

        if time_node:
            date_text = time_node.get("datetime")
            if not date_text:
                date_text = time_node.get_text(strip=True)
            if date_text:
                date_iso, date_display = _parse_date_text(date_text)

        thumbnail = None
        img = article.select_one("img")
        if img:
            src = img.get("src")
            if src:
                thumbnail = _absolutize(src)
            elif img.get("srcset"):
                sources = [s.strip().split()[0] for s in img["srcset"].split(",") if s.strip()]
                if sources:
                    thumbnail = _absolutize(sources[-1])

        articles.append({
            "title": title,
            "url": url,
            "date_iso": date_iso,
            "date_display": date_display,
            "thumbnail": thumbnail,
        })

    return articles


@register(
    key="scrape_google_deepmind",
    name="Google DeepMind",
    category="frontier_model",
    content_types=["research_lab", "article"],
)
def scrape() -> List[Dict[str, Any]]:
    index_html = _fetch(INDEX_URL)
    raw_items = _extract_articles(index_html)
    normalized: List[Dict[str, Any]] = []

    for item in raw_items:
        url = item.get("url")
        title = item.get("title")
        if not url or not title:
            continue

        published_at = parse_date(item.get("date_iso") or item.get("date_display"))

        normalized.append(
            make_item(
                title=title,
                url=url,
                author="Google DeepMind",
                published_at=published_at,
                thumbnail_url=item.get("thumbnail"),
                item_type="research_lab",
                source_name="Google DeepMind",
                extraction_method="requests",
                date_iso=item.get("date_iso"),
                date_display=item.get("date_display"),
            )
        )

    return normalized
