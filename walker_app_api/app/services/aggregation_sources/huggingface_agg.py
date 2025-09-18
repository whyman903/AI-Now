#!/usr/bin/env python3
import re
import sys
import asyncio
import random
import time
import json
from typing import List, Set, Optional, Dict, Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
import argparse
from datetime import datetime, timezone
from dateutil import parser as dateparser


BASE = "https://huggingface.co"
TRENDING = f"{BASE}/papers/trending"

PAPER_HREF_RE = re.compile(r'href="(/papers/\d{4}\.\d{4,}(?:v\d+)?)"')
ARXIV_PDF_RE = re.compile(r"https?://arxiv\.org/(?:pdf|abs)/(\d{4}\.\d{4,}(?:v\d+)?)")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
}

def uniq(seq):
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out


async def fetch_text(client: httpx.AsyncClient, url: str, retries: int = 3, timeout: float = 20.0) -> Optional[str]:
    delay = 0.8
    for attempt in range(retries):
        try:
            r = await client.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r.text
            # Some Next.js pages 307/308 to canonical; httpx follows redirects by default.
        except (httpx.HTTPError, httpx.ReadTimeout):
            pass
        await asyncio.sleep(delay + random.random() * 0.4)
        delay *= 1.8
    return None


def extract_paper_hrefs(html: str) -> List[str]:
    """
    Robustly find /papers/{id} links. Try:
      1) Regex across raw HTML
      2) Parsing DOM
      3) Falling back to __NEXT_DATA__ JSON if present
    """
    hrefs = set(PAPER_HREF_RE.findall(html))

    # DOM-based fallback
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        h = a["href"]
        if isinstance(h, str) and h.startswith("/papers/") and re.match(r"^/papers/\d{4}\.\d{4,}(?:v\d+)?$", h):
            hrefs.add(h)

    if not hrefs:
        for s in soup.find_all("script"):
            if not s.string:
                continue
            for match in PAPER_HREF_RE.findall(s.string):
                hrefs.add(match)

    return sorted(hrefs)


def normalize_arxiv_to_pdf(url: str) -> str:
    """
    Ensure arXiv links are in the canonical PDF form: https://arxiv.org/pdf/{id}.pdf
    Accepts /abs/{id} or /pdf/{id}[.pdf]
    """
    m = ARXIV_PDF_RE.search(url)
    if not m:
        return url
    paper_id = m.group(1)
    return f"https://arxiv.org/pdf/{paper_id}.pdf"


def find_pdf_link_from_html(html: str, base_url: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")

    # 1) Anchor with text mentioning PDF
    for a in soup.find_all("a", href=True):
        text = (a.get_text() or "").strip().lower()
        href = a["href"]
        if "pdf" in text:
            return normalize_arxiv_to_pdf(href)

    # 2) Any href that clearly points to a PDF
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".pdf"):
            return href

    # 3) Any arXiv link; normalize to /pdf/{id}.pdf
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "arxiv.org" in href:
            return normalize_arxiv_to_pdf(href)

    # 4) Last-resort: regex search in raw HTML
    m = re.search(r'href="(https?://[^"]+\.pdf)"', html)
    if m:
        return m.group(1)

    m2 = ARXIV_PDF_RE.search(html)
    if m2:
        pid = m2.group(1)
        return f"https://arxiv.org/pdf/{pid}.pdf"

    return None


async def resolve_pdf_for_paper(client: httpx.AsyncClient, href: str) -> Optional[str]:
    """
    Try both:
      https://huggingface.co/papers/trending{href}
      https://huggingface.co{href}
    and extract a PDF link from the page.
    """
    candidates = [
        urljoin(BASE, f"/papers/trending{href}"),
        urljoin(BASE, href),
    ]
    for url in candidates:
        html = await fetch_text(client, url)
        if not html:
            continue
        pdf = find_pdf_link_from_html(html, url)
        if pdf:
            return pdf
    return None


async def gather_pdfs(limit: Optional[int] = None, concurrency: int = 10) -> List[str]:
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        trending_html = await fetch_text(client, TRENDING)
        if not trending_html:
            raise RuntimeError("Failed to fetch trending page.")

        hrefs = extract_paper_hrefs(trending_html)
        if not hrefs:
            raise RuntimeError("No paper links found on trending page. The page layout may have changed.")

        if limit:
            hrefs = hrefs[:limit]

        sem = asyncio.Semaphore(concurrency)
        pdfs: Set[str] = set()

        async def worker(href: str):
            async with sem:
                pdf = await resolve_pdf_for_paper(client, href)
                if pdf:
                    # normalize arXiv links
                    pdfs.add(normalize_arxiv_to_pdf(pdf))

        await asyncio.gather(*(worker(h) for h in hrefs))
        return sorted(pdfs)


def scrape_trending_papers(limit: Optional[int] = 15) -> List[Dict[str, Any]]:
    """Scrape trending Hugging Face papers and return normalized content items."""
    html = httpx.get(TRENDING, headers=HEADERS, timeout=30.0).text
    soup = BeautifulSoup(html, "html.parser")

    articles = soup.select("article")
    results: List[Dict[str, Any]] = []
    scraped_at = datetime.now(timezone.utc).isoformat()

    for idx, article in enumerate(articles, start=1):
        if limit and idx > limit:
            break

        # Title
        title_el = article.select_one("h3")
        title = title_el.get_text(strip=True) if title_el else None
        if not title:
            continue

        # Link
        link_el = article.select_one("a[href^='/papers/']")
        if not link_el:
            continue
        href = link_el.get("href", "")
        if not href:
            continue
        url = urljoin(BASE, href)

        # Thumbnail
        thumb_el = article.select_one("img")
        thumbnail = thumb_el.get("src") if thumb_el and thumb_el.get("src") else None
        if thumbnail and thumbnail.startswith("/"):
            thumbnail = urljoin(BASE, thumbnail)

        # Summary/description
        summary_el = article.select_one("p.line-clamp-2")
        description = summary_el.get_text(" ", strip=True) if summary_el else ""

        # Authors & published date text
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
                if not stripped or stripped == "·":
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
        }
        if description:
            meta["description"] = description
        if authors_text:
            meta["authors"] = authors_text
        if published_text:
            meta["date_display"] = published_text

        results.append(
            {
                "type": "research_paper",
                "title": title,
                "url": url,
                "author": "Hugging Face Papers",
                "published_at": published_at,
                "thumbnail_url": thumbnail,
                "meta_data": meta,
            }
        )

    return results


def main():
    parser = argparse.ArgumentParser(description="Collect PDF URLs from Hugging Face trending papers.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of papers processed.")
    parser.add_argument("--out", type=str, default=None, help="Optional file to write PDF URLs.")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrent fetches.")
    args = parser.parse_args()

    pdfs = asyncio.run(gather_pdfs(limit=args.limit, concurrency=args.concurrency))
    for url in pdfs:
        print(url)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            for url in pdfs:
                f.write(url + "\n")
        print(f"\nWrote {len(pdfs)} URLs to {args.out}")

if __name__ == "__main__":
    main()
