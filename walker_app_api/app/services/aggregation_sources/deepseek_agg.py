#!/usr/bin/env python3
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from xml.etree import ElementTree as ET
from selenium import webdriver

from ._lab_scraper_utils import (
    create_chrome_driver,
    ensure_naive_utc,
    make_lab_item,
    normalize_whitespace,
)
from app.core.config import settings

BASE_URL = "https://www.deepseek.com"
PAGE_URL = "https://www.deepseek.com/en"
THUMBNAIL_URL = f"{settings.PUBLIC_BASE_URL or 'http://localhost:8000'}/static/images/deepseek-brand.png"
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
    """Fetch the DeepSeek page using Selenium to bypass 403 blocking."""
    driver = create_chrome_driver(headless=True, window_size="1400,1000")
    try:
        driver.get(url)
        # Give the page a moment to render any JavaScript content
        time.sleep(2)
        return driver.page_source
    finally:
        driver.quit()

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

        title = normalize_whitespace(anchor.get_text(strip=True))
        if not title:
            continue

        results.append({"title": title, "url": url})
        seen.add(url)

    return results


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
                    published_at = ensure_naive_utc(parsed)
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
                        published_at = ensure_naive_utc(parsed)
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


def _fetch_repos_from_github_api() -> List[Dict[str, str]]:
    """Fetch DeepSeek repos directly from GitHub API instead of scraping their website."""
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            # Get repositories sorted by most recently updated
            response = client.get(
                "https://api.github.com/users/deepseek-ai/repos",
                params={"sort": "updated", "per_page": 15},
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            response.raise_for_status()
            repos = response.json()
            
            results = []
            for repo in repos:
                # Filter for main model repos (not forks, archives, or utility repos)
                if repo.get("fork") or repo.get("archived"):
                    continue
                    
                name = repo.get("name", "")
                # Focus on main DeepSeek model repos
                if not any(keyword in name.lower() for keyword in ["deepseek", "model", "coder", "3fs"]):
                    continue
                
                results.append({
                    "title": name.replace("-", " "),
                    "url": repo["html_url"],
                    "description": repo.get("description", ""),
                })
            
            return results
    except Exception as exc:
        logger.error(f"Failed to fetch DeepSeek repos from GitHub API: {exc}")
        return []


def scrape() -> List[Dict[str, Any]]:
    """Scrape DeepSeek content using GitHub API (website blocks Selenium)."""
    items = _fetch_repos_from_github_api()
    
    if not items:
        logger.warning("DeepSeek scraper: No items found from GitHub API")
        return []

    normalized: List[Dict[str, Any]] = []
    with httpx.Client(headers=GITHUB_PAGE_HEADERS, timeout=10.0, follow_redirects=True) as gh_client:
        for item in items:
            published_at, repo_meta = _fetch_readme_metadata(item["url"], client=gh_client)

            meta_extra: Dict[str, Any] = {
                "section": "Research",
                "description": item.get("description", ""),
            }
            repo_meta = repo_meta or {}
            date_iso = repo_meta.get("date_iso")
            date_display = repo_meta.get("date_display")
            meta_extra.update(
                {k: v for k, v in repo_meta.items() if k not in {"date_iso", "date_display"}}
            )

            normalized.append(
                make_lab_item(
                    title=item["title"],
                    url=item["url"],
                    author="DeepSeek",
                    published_at=published_at,
                    thumbnail_url=THUMBNAIL_URL,
                    item_type="research_lab",
                    source_name="DeepSeek",
                    extraction_method="github_api",
                    date_iso=date_iso,
                    date_display=date_display,
                    extra_meta=meta_extra,
                )
            )

    return normalized
