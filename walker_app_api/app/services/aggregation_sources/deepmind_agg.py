#!/usr/bin/env python3
"""Google DeepMind blog scraper."""
from typing import Any, Dict, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from ._lab_scraper_utils import make_lab_item, normalize_whitespace, parse_datetime

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


def fetch(url: str) -> str:
    """Fetch a URL with appropriate headers."""
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def parse_date(text: str):
    """Parse date text into ISO and display format."""
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


def absolutize(url: str) -> str:
    """Convert relative URLs to absolute URLs."""
    if not url:
        return url
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return urljoin(BASE, url)
    return url if url.startswith(("http://", "https://")) else urljoin(INDEX_URL, url)


def extract_articles(html: str):
    """Extract articles from the DeepMind blog page."""
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    seen = set()

    # Find all article cards
    for article in soup.select("article.card.card-blog"):
        # Extract title
        title_node = article.select_one("h3.card__title")
        title = normalize_whitespace(title_node.get_text(strip=True)) if title_node else None
        
        if not title:
            continue

        # Extract link
        link_node = article.select_one("a[href]")
        if not link_node:
            continue
        
        url = absolutize(link_node.get("href"))
        if url in seen:
            continue
        seen.add(url)

        # Extract date
        time_node = article.select_one("time[datetime]")
        date_text = None
        date_iso = None
        date_display = None
        
        if time_node:
            date_text = time_node.get("datetime")
            if not date_text:
                date_text = time_node.get_text(strip=True)
            if date_text:
                date_iso, date_display = parse_date(date_text)

        # Extract category
        category_node = article.select_one("span.meta__category")
        category = normalize_whitespace(category_node.get_text(strip=True)) if category_node else None

        # Extract thumbnail
        thumbnail = None
        img = article.select_one("img")
        if img:
            # Try to get the src attribute
            src = img.get("src")
            if src:
                thumbnail = absolutize(src)
            # If no src, try srcset
            elif img.get("srcset"):
                srcset = img.get("srcset")
                # Parse srcset to get the best quality image
                if srcset:
                    # srcset format: "url width, url width, ..."
                    sources = [s.strip().split()[0] for s in srcset.split(",") if s.strip()]
                    if sources:
                        thumbnail = absolutize(sources[-1])  # Get the largest image

        articles.append({
            "title": title,
            "url": url,
            "date_iso": date_iso,
            "date_display": date_display,
            "thumbnail": thumbnail,
            "category": category,
            "author": "Google DeepMind",
            "type": "research_lab",
        })

    return articles


def scrape() -> List[Dict[str, Any]]:
    """Scrape the Google DeepMind blog and return normalized content items."""
    index_html = fetch(INDEX_URL)
    raw_items = extract_articles(index_html)
    normalized: List[Dict[str, Any]] = []
    
    for item in raw_items:
        url = item.get("url")
        title = item.get("title")
        if not url or not title:
            continue

        published_at = parse_datetime(item.get("date_iso") or item.get("date_display"))
        
        # Build metadata
        meta_data = {
            "extraction_method": "requests",
        }
        if item.get("category"):
            meta_data["category"] = item["category"]
        if item.get("date_iso"):
            meta_data["date_iso"] = item["date_iso"]
        if item.get("date_display"):
            meta_data["date_display"] = item["date_display"]

        normalized.append(
            make_lab_item(
                title=title,
                url=url,
                author=item.get("author") or "Google DeepMind",
                published_at=published_at,
                thumbnail_url=item.get("thumbnail"),
                item_type=item.get("type"),
                source_name="Google DeepMind",
                extraction_method="requests",
                date_iso=item.get("date_iso"),
                date_display=item.get("date_display"),
            )
        )
    
    return normalized

