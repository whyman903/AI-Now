"""Hugging Face daily papers scraper plugin."""
import re
import zlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from app.services.aggregation.registry import register

BASE = "https://huggingface.co"
TRENDING = f"{BASE}/papers/trending"

ARXIV_PDF_RE = re.compile(r"https?://arxiv\.org/(?:pdf|abs)/(\d{4}\.\d{4,}(?:v\d+)?)")
GITHUB_URL_RE = re.compile(
    rb"https?://(?:www\.)?github\.com/[\w\-./%?#=]+",
    re.IGNORECASE,
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
}


def _normalize_arxiv_to_pdf(url: str) -> str:
    m = ARXIV_PDF_RE.search(url)
    if not m:
        return url
    paper_id = m.group(1)
    return f"https://arxiv.org/pdf/{paper_id}.pdf"


def _find_pdf_link_from_html(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")

    for a in soup.find_all("a", href=True):
        text = (a.get_text() or "").strip().lower()
        href = a["href"]
        if "pdf" in text:
            return _normalize_arxiv_to_pdf(href)

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".pdf"):
            return href

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "arxiv.org" in href:
            return _normalize_arxiv_to_pdf(href)

    m = re.search(r'href="(https?://[^"]+\.pdf)"', html)
    if m:
        return m.group(1)

    m2 = ARXIV_PDF_RE.search(html)
    if m2:
        pid = m2.group(1)
        return f"https://arxiv.org/pdf/{pid}.pdf"

    return None


def _fetch_text_sync(url: str) -> Optional[str]:
    try:
        r = httpx.get(url, headers=HEADERS, timeout=20.0, follow_redirects=True)
        if r.status_code == 200:
            return r.text
    except httpx.HTTPError:
        pass
    return None


def _resolve_pdf_for_paper_sync(paper_url: str) -> Optional[str]:
    html = _fetch_text_sync(paper_url)
    if not html:
        return None
    return _find_pdf_link_from_html(html)


def _clean_extracted_url(url: str) -> str:
    return url.rstrip(")]>.,;'\"")


def _extract_github_from_bytes(blob: bytes) -> Optional[str]:
    match = GITHUB_URL_RE.search(blob)
    if not match:
        return None
    url_bytes = match.group(0)
    try:
        url = url_bytes.decode("utf-8", errors="ignore")
    except UnicodeDecodeError:
        return None
    return _clean_extracted_url(url)


def _iter_pdf_streams(pdf_bytes: bytes, max_stream_bytes: int = 1_500_000):
    stream_marker = b"stream"
    end_marker = b"endstream"
    start_idx = 0
    while True:
        stream_pos = pdf_bytes.find(stream_marker, start_idx)
        if stream_pos == -1:
            break
        data_start = stream_pos + len(stream_marker)
        while data_start < len(pdf_bytes) and pdf_bytes[data_start:data_start + 1] in (b"\r", b"\n"):
            data_start += 1
        end_pos = pdf_bytes.find(end_marker, data_start)
        if end_pos == -1:
            break
        stream = pdf_bytes[data_start:end_pos]
        if not stream:
            start_idx = end_pos + len(end_marker)
            continue
        if max_stream_bytes and len(stream) > max_stream_bytes:
            start_idx = end_pos + len(end_marker)
            continue
        yield stream
        start_idx = end_pos + len(end_marker)


def _safe_decompress(stream: bytes, max_output: int = 2_000_000) -> Optional[bytes]:
    if not stream or len(stream) > max_output * 4:
        return None

    for wbits in (zlib.MAX_WBITS, -15):
        try:
            decompressor = zlib.decompressobj(wbits)
            remaining = max_output
            chunks = []

            data = decompressor.decompress(stream, remaining)
            if data:
                chunks.append(data)
                remaining -= len(data)

            while remaining > 0 and decompressor.unconsumed_tail:
                data = decompressor.decompress(decompressor.unconsumed_tail, remaining)
                if not data:
                    break
                chunks.append(data)
                remaining -= len(data)

            if chunks:
                return b"".join(chunks)
        except zlib.error:
            continue
    return None


def _extract_github_url_from_pdf(pdf_url: str) -> Optional[str]:
    try:
        response = httpx.get(pdf_url, headers=HEADERS, timeout=30.0, follow_redirects=True)
    except httpx.HTTPError:
        return None

    if response.status_code != 200 or not response.content:
        return None

    raw_bytes = response.content

    direct_match = _extract_github_from_bytes(raw_bytes)
    if direct_match:
        return direct_match

    for stream in _iter_pdf_streams(raw_bytes):
        inflated = _safe_decompress(stream)
        if not inflated:
            continue
        match = _extract_github_from_bytes(inflated)
        if match:
            return match

    return None


@register(
    key="scrape_hugging_face_papers",
    name="Hugging Face Papers",
    category="options",
    content_types=["research_paper"],
)
def scrape(limit: Optional[int] = 15) -> List[Dict[str, Any]]:
    html = httpx.get(TRENDING, headers=HEADERS, timeout=30.0).text
    soup = BeautifulSoup(html, "html.parser")

    articles = soup.select("article")
    results: List[Dict[str, Any]] = []
    scraped_at = datetime.now(timezone.utc).isoformat()

    for idx, article in enumerate(articles, start=1):
        if limit and idx > limit:
            break

        title_el = article.select_one("h3")
        title = title_el.get_text(strip=True) if title_el else None
        if not title:
            continue

        link_el = article.select_one("a[href^='/papers/']")
        if not link_el:
            continue
        href = link_el.get("href", "")
        if not href:
            continue
        paper_page_url = urljoin(BASE, href)

        pdf_url = _resolve_pdf_for_paper_sync(paper_page_url)
        github_url = _extract_github_url_from_pdf(pdf_url) if pdf_url else None
        final_url = pdf_url or paper_page_url

        thumb_el = article.select_one("img")
        thumbnail = thumb_el.get("src") if thumb_el and thumb_el.get("src") else None
        if thumbnail and thumbnail.startswith("/"):
            thumbnail = urljoin(BASE, thumbnail)

        summary_el = article.select_one("p.line-clamp-2")
        description = summary_el.get_text(" ", strip=True) if summary_el else ""

        authors_text = None
        published_text = None
        info_div = article.select_one("div.flex.items-center.text-sm.text-gray-400")
        if not info_div:
            info_div = article.select_one("div.flex.items-center.text-sm.text-gray-500")
        if not info_div:
            for div in article.find_all("div", class_=True):
                classes = div.get("class", [])
                if "items-center" in classes and "text-sm" in classes:
                    text = div.get_text(" ", strip=True)
                    if text and "author" in text.lower():
                        info_div = div
                        break

        if info_div:
            span_texts = [span.get_text(" ", strip=True) for span in info_div.find_all("span") if span.get_text(strip=True)]
            if span_texts:
                authors_text = span_texts[0]
            for candidate in span_texts[1:]:
                stripped = candidate.strip()
                if not stripped or stripped == "\u00b7":
                    continue
                if "published" in stripped.lower() or stripped:
                    published_text = candidate
                    break
            if published_text and published_text.lower().startswith("published on"):
                published_text = published_text[len("Published on"):].strip()

        published_at = None
        if published_text:
            try:
                dt = dateparser.parse(published_text)
                if dt:
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    else:
                        dt = dt.astimezone(timezone.utc)
                    published_at = dt
            except Exception:
                published_at = None

        meta: Dict[str, Any] = {
            "source_name": "Hugging Face Papers",
            "category": "ai_ml",
            "rank": idx,
            "scraped_date": scraped_at,
            "extraction_method": "huggingface_trending",
            "original_url": paper_page_url,
        }
        if pdf_url:
            meta["pdf_url"] = pdf_url
        if github_url:
            meta["github_url"] = github_url
        if description:
            meta["description"] = description
        if authors_text:
            meta["authors"] = authors_text
        if published_text:
            meta["date_display"] = published_text

        results.append({
            "type": "research_paper",
            "title": title,
            "url": final_url,
            "author": authors_text or None,
            "published_at": published_at,
            "thumbnail_url": thumbnail,
            "meta_data": meta,
        })

    return results
