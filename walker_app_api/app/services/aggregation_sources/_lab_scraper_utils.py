"""Shared helpers to keep lab scraper implementations consistent."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, MutableMapping, Optional
from urllib.parse import urljoin

from dateutil import parser as dateparser
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from ._webdriver import get_chromedriver_path
from ...core.config import settings


_LEGACY_THUMBNAIL_REMAP = {
    "deepseek-logo.png": "/static/images/deepseek-brand.png",
    "thinking-machines.png": "/static/images/thinking-machines-brand.png",
}

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


__all__ = [
    "DEFAULT_USER_AGENT",
    "autoscroll_page",
    "build_lab_meta",
    "create_chrome_driver",
    "ensure_naive_utc",
    "make_lab_item",
    "normalize_whitespace",
    "parse_datetime",
]


def _resolve_public_url(value: Optional[str]) -> Optional[str]:
    """Convert relative asset paths into absolute URLs using configured base."""
    if not value:
        return value

    cleaned = value.strip()
    if not cleaned:
        return cleaned

    lower_cleaned = cleaned.lower()
    for legacy_suffix, replacement in _LEGACY_THUMBNAIL_REMAP.items():
        if lower_cleaned.endswith(legacy_suffix):
            cleaned = replacement
            break

    if cleaned.startswith(("http://", "https://", "data:")):
        return cleaned

    base = (settings.PUBLIC_BASE_URL or "").strip()
    if not base:
        return cleaned

    if not base.endswith("/"):
        base = base + "/"

    return urljoin(base, cleaned.lstrip("/"))


def create_chrome_driver(
    *,
    headless: bool = True,
    window_size: str = "1400,1000",
    extra_args: Optional[list[str]] = None,
) -> webdriver.Chrome:
    """Provision a Chrome driver with hardened defaults for lab scrapers."""
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument(f"--window-size={window_size}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("accept-language=en-US,en;q=0.9")
    opts.add_argument(f"user-agent={DEFAULT_USER_AGENT}")
    for arg in extra_args or []:
        opts.add_argument(arg)

    service = Service(get_chromedriver_path())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def autoscroll_page(
    driver: webdriver.Chrome,
    *,
    pause: float = 0.9,
    max_attempts: int = 20,
    ensure_stable: bool = True,
    scroll_script: str = "window.scrollTo(0, document.body.scrollHeight);",
    height_script: str = "return document.body.scrollHeight",
) -> None:
    """Scroll down until the page height stabilizes or attempts are exhausted."""
    last_height = driver.execute_script(height_script)
    attempts = 0
    while attempts < max_attempts:
        driver.execute_script(scroll_script)
        time.sleep(pause)
        new_height = driver.execute_script(height_script)
        if new_height == last_height:
            if ensure_stable:
                time.sleep(pause)
                new_height = driver.execute_script(height_script)
                if new_height == last_height:
                    break
            else:
                break
        last_height = new_height
        attempts += 1


def normalize_whitespace(value: Optional[str]) -> Optional[str]:
    """Collapse whitespace and return None when the input is falsy."""
    if not value:
        return None
    return " ".join(value.split())


def ensure_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert datetimes to naive UTC to align with persistence layer expectations."""
    if dt is None:
        return None
    if dt.tzinfo:
        try:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            return dt
    return dt


def parse_datetime(value: Optional[str | datetime]) -> Optional[datetime]:
    """Best-effort parsing of incoming date strings to naive UTC datetimes."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return ensure_naive_utc(value)
    try:
        parsed = dateparser.parse(value, fuzzy=True)
    except Exception:
        return None
    if not parsed:
        return None
    return ensure_naive_utc(parsed)


def build_lab_meta(
    *,
    source_name: str,
    extraction_method: str,
    category: str = "ai_ml",
    date_iso: Optional[str] = None,
    date_display: Optional[str] = None,
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble a consistent `meta_data` payload for lab scrapers."""
    meta: Dict[str, Any] = {
        "source_name": source_name,
        "category": category,
        "extraction_method": extraction_method,
    }
    if date_iso:
        meta["date_iso"] = date_iso
    if date_display:
        meta["date_display"] = date_display
    if extra:
        meta.update(extra)
    return meta


def make_lab_item(
    *,
    title: str,
    url: str,
    source_name: str,
    extraction_method: str,
    author: Optional[str] = None,
    published_at: Optional[datetime] = None,
    thumbnail_url: Optional[str] = None,
    item_type: Optional[str] = None,
    date_iso: Optional[str] = None,
    date_display: Optional[str] = None,
    extra_meta: Optional[Mapping[str, Any]] = None,
    extra_fields: Optional[MutableMapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Create the normalized item dictionary used by all lab scrapers."""
    resolved_thumbnail = _resolve_public_url(thumbnail_url)

    item: Dict[str, Any] = {
        "title": title,
        "url": url,
        "author": author,
        "published_at": ensure_naive_utc(published_at),
        "thumbnail_url": resolved_thumbnail,
        "type": item_type or "research_lab",
        "meta_data": build_lab_meta(
            source_name=source_name,
            extraction_method=extraction_method,
            date_iso=date_iso,
            date_display=date_display,
            extra=extra_meta,
        ),
    }
    if extra_fields:
        item.update(extra_fields)
    return item
