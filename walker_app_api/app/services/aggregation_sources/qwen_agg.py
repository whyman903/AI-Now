#!/usr/bin/env python3
from typing import Any, Dict, List
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from ._lab_scraper_utils import make_lab_item, normalize_whitespace, parse_datetime

BASE = "https://qwenlm.github.io"
INDEX_URL = "https://qwenlm.github.io/blog/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text

def parse_date(text: str):
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
    if not url:
        return url
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return urljoin(BASE, url)
    return url if bool(urlparse(url).scheme) else urljoin(INDEX_URL, url)

def extract_thumbnail_from_post(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    
    # First try meta tags, but validate they contain actual URLs not placeholders
    for sel, attr in [
        ('meta[property="og:image"]', "content"),
        ('meta[name="twitter:image"]', "content"),
    ]:
        m = soup.select_one(sel)
        if m and m.get(attr):
            content = m.get(attr)
            # Skip placeholder content
            if content and not ("<" in content or ">" in content or "path" in content.lower() or "link" in content.lower()):
                thumbnail = absolutize(content)
                if thumbnail and thumbnail.startswith(("http://", "https://")):
                    return thumbnail
    
    # Look for the first image in the main content area
    container = soup.select_one(".post-content, .entry-content, article, main")
    if container:
        # Look for images in the content, preferring those with meaningful src attributes
        for img in container.select("img"):
            src = img.get("src")
            if src and not src.startswith("data:"):
                # Skip very small images (likely icons or decorative elements)
                width = img.get("width")
                height = img.get("height")
                if width and height:
                    try:
                        if int(width) < 100 or int(height) < 100:
                            continue
                    except (ValueError, TypeError):
                        pass
                return absolutize(src)
    
    # Fallback: look for any image on the page
    img = soup.select_one("img")
    if img and img.get("src"):
        src = img.get("src")
        if src and not src.startswith("data:"):
            return absolutize(src)
    
    return None

def extract_index(html: str):
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    seen = set()
    for art in soup.select("article.post-entry"):
        a = art.select_one("a.entry-link[href]")
        if not a:
            continue
        url = absolutize(a["href"])
        if url in seen:
            continue

        h2 = art.select_one("header.entry-header h2")
        title = (
            normalize_whitespace(h2.get_text(strip=True))
            if h2
            else None
        )

        date_span = art.select_one("footer.entry-footer span[title]") or art.select_one("footer.entry-footer span")
        date_text = None
        if date_span:
            title_attr = date_span.get("title")
            visible = date_span.get_text(strip=True)
            iso = None
            if title_attr:
                try:
                    iso = dateparser.parse(title_attr, fuzzy=True).isoformat()
                except Exception:
                    pass
            if not iso:
                iso, _ = parse_date(visible)
            date_iso = iso
            date_display = visible
        else:
            date_iso = date_display = None

        posts.append({
            "title": title,
            "date_iso": date_iso,
            "date_display": date_display,
            "url": url,
            "thumbnail": None,
        })
        seen.add(url)

    for a in soup.select("a.entry-link[href]"):
        url = absolutize(a["href"])
        if url in seen:
            continue
        parent = a.parent
        title_node = None
        date_iso = date_display = None

        ctx = parent
        for _ in range(4):
            if not ctx:
                break
            title_node = title_node or ctx.select_one("header.entry-header h2")
            if not date_iso and not date_display:
                span = ctx.select_one("footer.entry-footer span[title]") or ctx.select_one("footer.entry-footer span")
                if span:
                    vis = span.get_text(strip=True)
                    iso = None
                    if span.has_attr("title"):
                        try:
                            iso = dateparser.parse(span["title"], fuzzy=True).isoformat()
                        except Exception:
                            pass
                    if not iso:
                        iso, _ = parse_date(vis)
                    date_iso, date_display = iso, vis
            ctx = ctx.parent

        title = (
            normalize_whitespace(title_node.get_text(strip=True))
            if title_node
            else None
        )
        posts.append({
            "title": title,
            "date_iso": date_iso,
            "date_display": date_display,
            "url": url,
            "thumbnail": None,
            "author": 'Qwen',
            "type": "research_lab"
        })
        seen.add(url)

    return posts


def scrape() -> List[Dict[str, Any]]:
    """Scrape the Qwen blog index and return normalized content items."""
    index_html = fetch(INDEX_URL)
    raw_items = extract_index(index_html)
    normalized: List[Dict[str, Any]] = []
    
    for item in raw_items:
        url = item.get("url")
        title = item.get("title")
        if not url or not title:
            continue

        thumbnail_url = None
        try:
            post_html = fetch(url)
            thumbnail_url = extract_thumbnail_from_post(post_html)
        except Exception as exc:
            print(f"Failed to fetch thumbnail for {url}: {exc}")

        published_at = parse_datetime(item.get("date_iso") or item.get("date_display"))
        normalized.append(
            make_lab_item(
                title=title,
                url=url,
                author=item.get("author") or "Qwen",
                published_at=published_at,
                thumbnail_url=thumbnail_url,
                item_type=item.get("type"),
                source_name="Qwen",
                extraction_method="requests",
                date_iso=item.get("date_iso"),
                date_display=item.get("date_display"),
            )
        )
    return normalized
