"""Qwen blog scraper plugin."""
from typing import Any, Dict, List
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from app.services.aggregation.registry import register
from app.services.aggregation.utils.date_parser import parse_date
from app.services.aggregation.utils.html import make_item, normalize_whitespace

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
    return url if bool(urlparse(url).scheme) else urljoin(INDEX_URL, url)


def _extract_thumbnail_from_post(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")

    for sel, attr in [
        ('meta[property="og:image"]', "content"),
        ('meta[name="twitter:image"]', "content"),
    ]:
        m = soup.select_one(sel)
        if m and m.get(attr):
            content = m.get(attr)
            # Reject SVG fragments and HTML markup that some meta tags contain instead of image URLs
            if content and not ("<" in content or ">" in content or "path" in content.lower() or "link" in content.lower()):
                thumbnail = _absolutize(content)
                if thumbnail and thumbnail.startswith(("http://", "https://")):
                    return thumbnail

    container = soup.select_one(".post-content, .entry-content, article, main")
    if container:
        for img in container.select("img"):
            src = img.get("src")
            if src and not src.startswith("data:"):
                width = img.get("width")
                height = img.get("height")
                if width and height:
                    try:
                        if int(width) < 100 or int(height) < 100:
                            continue
                    except (ValueError, TypeError):
                        pass
                return _absolutize(src)

    img = soup.select_one("img")
    if img and img.get("src"):
        src = img.get("src")
        if src and not src.startswith("data:"):
            return _absolutize(src)

    return None


def _extract_index(html: str):
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    seen = set()

    for art in soup.select("article.post-entry"):
        a = art.select_one("a.entry-link[href]")
        if not a:
            continue
        url = _absolutize(a["href"])
        if url in seen:
            continue

        h2 = art.select_one("header.entry-header h2")
        title = normalize_whitespace(h2.get_text(strip=True)) if h2 else None

        date_span = art.select_one("footer.entry-footer span[title]") or art.select_one("footer.entry-footer span")
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
                iso, _ = _parse_date_text(visible)
            date_iso = iso
            date_display = visible
        else:
            date_iso = date_display = None

        posts.append({
            "title": title,
            "date_iso": date_iso,
            "date_display": date_display,
            "url": url,
        })
        seen.add(url)

    for a in soup.select("a.entry-link[href]"):
        url = _absolutize(a["href"])
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
                        iso, _ = _parse_date_text(vis)
                    date_iso, date_display = iso, vis
            ctx = ctx.parent

        title = normalize_whitespace(title_node.get_text(strip=True)) if title_node else None
        posts.append({
            "title": title,
            "date_iso": date_iso,
            "date_display": date_display,
            "url": url,
        })
        seen.add(url)

    return posts


@register(
    key="scrape_qwen",
    name="Qwen",
    category="frontier_model",
    content_types=["article"],
)
def scrape() -> List[Dict[str, Any]]:
    index_html = _fetch(INDEX_URL)
    raw_items = _extract_index(index_html)
    normalized: List[Dict[str, Any]] = []

    for item in raw_items:
        url = item.get("url")
        title = item.get("title")
        if not url or not title:
            continue

        thumbnail_url = None
        try:
            post_html = _fetch(url)
            thumbnail_url = _extract_thumbnail_from_post(post_html)
        except Exception:
            pass

        published_at = parse_date(item.get("date_iso") or item.get("date_display"))
        normalized.append(
            make_item(
                title=title,
                url=url,
                author="Qwen",
                published_at=published_at,
                thumbnail_url=thumbnail_url,
                source_name="Qwen",
                extraction_method="requests",
                date_iso=item.get("date_iso"),
                date_display=item.get("date_display"),
            )
        )
    return normalized
