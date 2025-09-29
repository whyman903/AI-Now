#!/usr/bin/env python3
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from xml.etree import ElementTree as ET

BASE_URL = "https://www.deepseek.com"
PAGE_URL = "https://www.deepseek.com/en"
THUMBNAIL_URL = "/images/deepseek-logo.png"
GITHUB_PREFIX = "https://github.com/deepseek-ai/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.deepseek.com/",
    "Sec-Ch-Ua": '"Not/A)Brand";v="99", "Google Chrome";v="126", "Chromium";v="126"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
}

GITHUB_PAGE_HEADERS: Dict[str, str] = {
    "User-Agent": HEADERS["User-Agent"],
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Referer": "https://www.deepseek.com/",
}

ATOM_NS = "{http://www.w3.org/2005/Atom}"

logger = logging.getLogger(__name__)


def _fetch_page(url: str = PAGE_URL) -> str:
    with httpx.Client(headers=HEADERS, timeout=15.0, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text


def _normalize(text: str | None) -> str | None:
    if not text:
        return None
    return " ".join(text.split())


def _absolutize(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return urljoin(BASE_URL, url)
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return urljoin(PAGE_URL, url)


def _extract_research_links(html: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")

    results: List[Dict[str, str]] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not href:
            continue
        url = _absolutize(href)
        if not url.lower().startswith(GITHUB_PREFIX.lower()):
            continue
        if url in seen:
            continue

        title = _normalize(anchor.get_text(strip=True))
        if not title:
            continue

        results.append({"title": title, "url": url})
        seen.add(url)

    return results


def _to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _format_relative(dt: datetime) -> str:
    now = datetime.now(timezone.utc)
    delta = now - dt.replace(tzinfo=timezone.utc)
    seconds = int(delta.total_seconds())
    if seconds < 0:
        seconds = 0

    intervals = (
        ("year", 60 * 60 * 24 * 365),
        ("month", 60 * 60 * 24 * 30),
        ("week", 60 * 60 * 24 * 7),
        ("day", 60 * 60 * 24),
        ("hour", 60 * 60),
        ("minute", 60),
    )

    for label, length in intervals:
        value = seconds // length
        if value >= 1:
            suffix = "s" if value > 1 else ""
            return f"{value} {label}{suffix} ago"

    return "just now"


def _extract_repo_identifiers(url: str) -> tuple[str | None, str | None]:
    if not url.startswith("https://github.com/"):
        return None, None
    path = url[len("https://github.com/") :]
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2:
        return None, None
    owner, repo = parts[0], parts[1]
    repo = repo.removesuffix(".git")
    return owner, repo


def _fetch_readme_metadata(repo_url: str, client: httpx.Client | None = None) -> tuple[datetime | None, Dict[str, Any]]:
    owner_repo = _extract_repo_identifiers(repo_url)
    if owner_repo == (None, None):
        return None, {}
    owner, repo = owner_repo

    close_client = False
    http_client = client
    if http_client is None:
        http_client = httpx.Client(headers=GITHUB_PAGE_HEADERS, timeout=10.0, follow_redirects=True)
        close_client = True

    try:
        feed_url = f"https://github.com/{owner}/{repo}/commits.atom?path=README.md"
        response = http_client.get(feed_url, timeout=15.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:  # pragma: no cover - network dependent
        logger.debug("DeepSeek scraper: failed fetching README feed for %s: %s", repo_url, exc)
        if close_client:
            http_client.close()
        return None, {}

    published_at: datetime | None = None
    meta: Dict[str, Any] = {}

    try:
        root = ET.fromstring(response.text)
        entry = root.find(f"{ATOM_NS}entry")
        if entry is not None:
            updated_text = entry.findtext(f"{ATOM_NS}updated")
            if updated_text:
                parsed = dateparser.parse(updated_text)
                if parsed:
                    published_at = _to_utc_naive(parsed)
                    meta["date_iso"] = published_at.isoformat()
                    meta["date_display"] = _format_relative(published_at)
            link = entry.find(f"{ATOM_NS}link[@rel='alternate']")
            if link is not None and link.get("href"):
                meta["readme_commit_url"] = link.get("href")
    except ET.ParseError as exc:  # pragma: no cover - defensive parsing guard
        logger.debug("DeepSeek scraper: failed parsing README feed for %s: %s", repo_url, exc)

    # Fallback to general repo commit feed if README-specific feed is empty
    if not published_at:
        try:
            feed_url = f"https://github.com/{owner}/{repo}/commits.atom"
            response = http_client.get(feed_url, timeout=15.0)
            response.raise_for_status()
            root = ET.fromstring(response.text)
            entry = root.find(f"{ATOM_NS}entry")
            if entry is not None:
                updated_text = entry.findtext(f"{ATOM_NS}updated")
                if updated_text:
                    parsed = dateparser.parse(updated_text)
                    if parsed:
                        published_at = _to_utc_naive(parsed)
                        meta.setdefault("date_iso", published_at.isoformat())
                        meta.setdefault("date_display", _format_relative(published_at))
                link = entry.find(f"{ATOM_NS}link[@rel='alternate']")
                if link is not None and link.get("href"):
                    meta.setdefault("readme_commit_url", link.get("href"))
        except (httpx.HTTPError, ET.ParseError) as exc:  # pragma: no cover - defensive parsing guard
            logger.debug("DeepSeek scraper: failed fallback commit feed for %s: %s", repo_url, exc)

    if close_client:
        http_client.close()

    return published_at, meta


def scrape() -> List[Dict[str, Any]]:
    html = _fetch_page()
    items = _extract_research_links(html)

    normalized: List[Dict[str, Any]] = []
    with httpx.Client(headers=GITHUB_PAGE_HEADERS, timeout=10.0, follow_redirects=True) as gh_client:
        for item in items:
            published_at, extra_meta = _fetch_readme_metadata(item["url"], client=gh_client)

            meta: Dict[str, Any] = {
                "source_name": "DeepSeek",
                "category": "ai_ml",
                "extraction_method": "httpx",
                "section": "Research",
            }
            meta.update(extra_meta)

            normalized.append(
                {
                    "title": item["title"],
                    "url": item["url"],
                    "author": "DeepSeek",
                    "published_at": published_at,
                    "thumbnail_url": THUMBNAIL_URL,
                    "type": "research_lab",
                    "meta_data": meta,
                }
            )

    return normalized
