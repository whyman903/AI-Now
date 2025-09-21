#!/usr/bin/env python3
import re
import time
from typing import List, Dict, Any
from urllib.parse import urljoin
from datetime import datetime, timezone

from bs4 import BeautifulSoup, Tag
from dateutil import parser as dateparser

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

BASE = "https://x.ai"
START_URL = "https://x.ai/news"

BG_URL_RE = re.compile(r'url\((["\']?)(.*?)\1\)')
MONTH_NAME_RE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"\b\d{4}\b")

def build_driver(headless: bool = True) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1400,1000")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("accept-language=en-US,en;q=0.9")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)

    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"}
    )
    return driver

def wait_for_news(driver, timeout=20):
    sel = "a[href^='/news/'] h3"
    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))

def autoscroll_to_bottom(driver, pause=0.8, max_tries=16):
    last_h = driver.execute_script("return document.body.scrollHeight")
    tries = 0
    while tries < max_tries:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause)
        new_h = driver.execute_script("return document.body.scrollHeight")
        if new_h == last_h:
            time.sleep(pause)
            new_h = driver.execute_script("return document.body.scrollHeight")
            if new_h == last_h:
                break
        last_h = new_h
        tries += 1

def normalize(s: str) -> str:
    return " ".join(s.split()) if s else s

def extract_bg_url(style_value: str) -> str | None:
    if not style_value:
        return None
    m = BG_URL_RE.search(style_value)
    return m.group(2) if m else None


def _looks_like_date_text(text: str | None) -> bool:
    if not text:
        return False
    if YEAR_RE.search(text):
        return True
    if MONTH_NAME_RE.search(text):
        return True
    if re.search(r"\b\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4}\b", text):
        return True
    return False

def parse_date(d: str) -> tuple[str | None, str | None]:
    if not d:
        return None, None
    d_disp = normalize(d)
    try:
        dt = dateparser.parse(d_disp, fuzzy=True)
        return dt.isoformat(), d_disp
    except Exception:
        try:
            dt = datetime.strptime(d_disp, "%B %d, %Y")
            return dt.isoformat(), d_disp
        except Exception:
            return None, d_disp

def extract_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen_urls = set()

    for a in soup.select("a[href^='/news/']"):
        href = a.get("href")
        if not href:
            continue
        url = urljoin(BASE, href)

        if url in seen_urls:
            continue

        h3 = a.find("h3")
        title = normalize(h3.get_text(strip=True)) if h3 else None
        if not title:
            title = normalize(a.get_text(strip=True)) or None

        wrapper = None
        background_parent: Tag | None = None
        cur: Tag | None = a
        for _ in range(12):
            cur = cur.parent if isinstance(cur, Tag) else None
            if not isinstance(cur, Tag):
                break

            if background_parent is None and cur.select_one("div[style*='background-image']"):
                background_parent = cur

            candidate_nodes = cur.select(
                "time[datetime], .mono-tag, p[class*='mono'], span[class*='mono']"
            )
            for node in candidate_nodes:
                raw_text = node.get("datetime") if node.name == "time" else node.get_text(" ", strip=True)
                if _looks_like_date_text(normalize(raw_text)):
                    wrapper = cur
                    break
            if wrapper:
                break

        if wrapper is None:
            wrapper = background_parent or a.parent

        if background_parent is None and isinstance(wrapper, Tag):
            bg_cursor: Tag | None = wrapper
            for _ in range(6):
                bg_cursor = bg_cursor.parent if isinstance(bg_cursor, Tag) else None
                if not isinstance(bg_cursor, Tag):
                    break
                if bg_cursor.select_one("div[style*='background-image']"):
                    background_parent = bg_cursor
                    break

        date_iso = None
        date_display = None
        fallback_display = None
        candidates = []
        if wrapper:
            candidates = wrapper.select(
                "time[datetime], .mono-tag, p[class*='mono'], span[class*='mono']"
            )

        for node in candidates:
            raw = node.get("datetime") if node.name == "time" else node.get_text(" ", strip=True)
            raw = normalize(raw)
            if not raw:
                continue
            iso, disp = parse_date(raw)
            if iso:
                date_iso, date_display = iso, disp
                break
            if not fallback_display and _looks_like_date_text(raw):
                fallback_display = disp

        if not date_display and fallback_display:
            date_display = fallback_display

        bg_div = None
        if wrapper:
            bg_div = wrapper.select_one("div[style*='background-image']")
        if not bg_div and background_parent:
            bg_div = background_parent.select_one("div[style*='background-image']")
        thumb_rel = extract_bg_url(bg_div.get("style")) if bg_div else None
        thumbnail = urljoin(BASE, thumb_rel) if thumb_rel else None

        items.append({
            "title": title,
            "date_iso": date_iso,
            "date_display": date_display,
            "thumbnail": thumbnail,
            "url": url,
            "author": 'xAI',
            "type": "research_lab"
        })
        seen_urls.add(url)

    return items


def _parse_iso(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        dt = dateparser.parse(dt_str, fuzzy=True)
    except Exception:
        return None
    if not dt:
        return None
    if dt.tzinfo:
        try:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            pass
    return dt


def scrape(headless: bool = True) -> List[Dict[str, Any]]:
    """Scrape xAI news posts and return normalized content items."""
    driver = build_driver(headless=headless)
    try:
        driver.get(START_URL)
        time.sleep(1.0)
        try:
            wait_for_news(driver, timeout=25)
        except TimeoutException:
            pass
        autoscroll_to_bottom(driver, pause=0.9, max_tries=20)
        html = driver.page_source
    finally:
        driver.quit()

    raw = extract_from_html(html)
    normalized: List[Dict[str, Any]] = []
    for item in raw:
        published_at = _parse_iso(item.get("date_iso") or item.get("date_display"))
        normalized.append({
            "title": item.get("title"),
            "url": item.get("url"),
            "author": item.get("author", "xAI"),
            "published_at": published_at,
            "thumbnail_url": item.get("thumbnail"),
            "type": item.get("type", "research_lab"),
            "meta_data": {
                "source_name": "xAI",
                "category": "ai_ml",
                "date_iso": item.get("date_iso"),
                "date_display": item.get("date_display"),
                "extraction_method": "selenium",
            },
        })
    return normalized
