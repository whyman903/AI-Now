#!/usr/bin/env python3
import time
from typing import List, Dict, Any
from urllib.parse import urljoin
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from ._webdriver import get_chromedriver_path

BASE = "https://openai.com"
START_URL = "https://openai.com/research/index/?display=grid"
from selenium.webdriver.chrome.service import Service

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
    service = Service(get_chromedriver_path())
    driver = webdriver.Chrome(service=service, options=opts)

    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"}
    )
    return driver

def wait_for_grid(driver, timeout=20):
    sel = "a[aria-label][href^='/index/']"
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, sel))
    )

def autoscroll_to_bottom(driver, pause=0.8, max_tries=20):
    """
    Scrolls to bottom, waiting for lazy-loaded content.
    Stops when page height no longer increases or max_tries reached.
    """
    last_height = driver.execute_script("return document.body.scrollHeight")
    tries = 0
    while tries < max_tries:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            time.sleep(pause)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
        last_height = new_height
        tries += 1

def normalize_text(s: str) -> str:
    return " ".join(s.split()) if s else s

def extract_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    items = []

    for a in soup.select("a[aria-label][href^='/index/']"):
        try:
            title_node = a.select_one(".mb-2xs, .text-h5, h2, h3")
            if title_node:
                title = normalize_text(title_node.get_text(strip=True))
            else:
                aria = a.get("aria-label", "")
                title = normalize_text(aria.split(" - ")[0]) if (" - " in aria) else (aria or None)

            time_node = a.select_one("time[datetime]") or a.select_one("time")
            date_iso = time_node.get("datetime") if time_node and time_node.has_attr("datetime") else None
            date_display = normalize_text(time_node.get_text(strip=True)) if time_node else None

            url = urljoin(BASE, a.get("href"))

            thumb = None
            parent = a.parent
            if parent:
                img = parent.select_one("img")
                if not img and parent.previous_sibling:
                    prev_el = parent.previous_sibling
                    while prev_el and getattr(prev_el, "name", None) is None:
                        prev_el = prev_el.previous_sibling
                    if prev_el:
                        img = prev_el.select_one("img") if hasattr(prev_el, "select_one") else None

                if img:
                    if img.get("src"):
                        thumb = img["src"]
                    elif img.get("srcset"):
                        cands = [p.strip().split(" ")[0] for p in img["srcset"].split(",") if p.strip()]
                        if cands:
                            thumb = cands[-1]

            items.append({
                "title": title,
                "date_iso": date_iso,
                "date_display": date_display,
                "thumbnail": thumb,
                "url": url,
                "author": 'OpenAI',
                "type": "research_lab"
            })
        except Exception:
            continue

    seen, deduped = set(), []
    for it in items:
        u = it.get("url")
        if u and u not in seen:
            deduped.append(it)
            seen.add(u)
    return deduped


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = dateparser.parse(value, fuzzy=True)
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
    """Scrape OpenAI Research grid and return normalized items."""
    driver = build_driver(headless=headless)
    try:
        driver.get(START_URL)
        try:
            wait_for_grid(driver, timeout=25)
        except TimeoutException:
            pass
        autoscroll_to_bottom(driver, pause=0.9, max_tries=24)
        html = driver.page_source
    finally:
        driver.quit()

    raw = extract_from_html(html)
    normalized: List[Dict[str, Any]] = []
    for item in raw:
        published_at = _parse_date(item.get("date_iso") or item.get("date_display"))
        normalized.append({
            "title": item.get("title"),
            "url": item.get("url"),
            "author": item.get("author", "OpenAI"),
            "published_at": published_at,
            "thumbnail_url": item.get("thumbnail"),
            "type": item.get("type", "research_lab"),
            "meta_data": {
                "source_name": "OpenAI",
                "category": "ai_ml",
                "date_iso": item.get("date_iso"),
                "date_display": item.get("date_display"),
                "extraction_method": "selenium",
            },
        })
    return normalized
