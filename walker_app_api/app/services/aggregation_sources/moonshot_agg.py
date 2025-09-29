#!/usr/bin/env python3
import re
import time
from typing import Any, Dict, List
from urllib.parse import urljoin, urlparse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from ._lab_scraper_utils import (
    autoscroll_page,
    create_chrome_driver,
    make_lab_item,
    normalize_whitespace,
    parse_datetime,
)

BASE = "https://www.moonshot.ai/"
BG_URL_RE = re.compile(r'background-image\s*:\s*url\((["\']?)(.*?)\1\)', re.I)

def absolutize(u: str | None) -> str | None:
    if not u:
        return None
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return urljoin(BASE, u)
    if not urlparse(u).scheme:
        return urljoin(BASE, u)
    return u

def build_driver(headless: bool = True) -> webdriver.Chrome:
    return create_chrome_driver(headless=headless, window_size="1400,1200")

def wait_for_cards(driver, timeout=25):
    sel = "a[class*='k2Item'], a[class*='researchItem']"
    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))

def autoscroll(driver, pause=0.8, max_tries=15):
    autoscroll_page(driver, pause=pause, max_attempts=max_tries)

def get_text_safe(root, css):
    try:
        return normalize_whitespace(root.find_element(By.CSS_SELECTOR, css).text)
    except NoSuchElementException:
        return None

def pick_bg_url_from_style(style_val: str | None) -> str | None:
    if not style_val:
        return None
    m = BG_URL_RE.search(style_val)
    return m.group(2) if m else None

def extract_items(driver):
    items, seen = [], set()

    for a in driver.find_elements(By.CSS_SELECTOR, "a[class*='k2Item']"):
        href = a.get_attribute("href")
        if not href:
            continue
        url = absolutize(href)
        if url in seen:
            continue

        title = get_text_safe(a, "h2[class*='title___'], h2")
        date_display = get_text_safe(a, "p[class*='time___'], time")
        date_iso = date_display

        thumb = None
        try:
            vid = a.find_element(By.CSS_SELECTOR, "video")
            src = vid.get_attribute("src")
            if src:
                thumb = absolutize(src)
        except NoSuchElementException:
            pass
        if not thumb:
            try:
                img = a.find_element(By.CSS_SELECTOR, "img")
                thumb = absolutize(img.get_attribute("src"))
            except NoSuchElementException:
                pass

        items.append({
            "title": title,
            "date_iso": date_iso,
            "date_display": date_display,
            "thumbnail": thumb,
            "url": url,
        })
        seen.add(url)

    for a in driver.find_elements(By.CSS_SELECTOR, "a[class*='researchItem']"):
        href = a.get_attribute("href")
        if not href:
            continue
        url = absolutize(href)
        if url in seen:
            continue

        title = get_text_safe(a, "h2[class*='title___'], h2")
        date_display = get_text_safe(a, "p[class*='time___'], time")
        date_iso = date_display

        style_val = a.get_attribute("style")
        thumb_rel = pick_bg_url_from_style(style_val)
        thumb = absolutize(thumb_rel)

        items.append({
            "title": title,
            "date_iso": date_iso,
            "date_display": date_display,
            "thumbnail": thumb,
            "url": url,
            "author": 'Moonshot',
            "type": "research_lab"
        })
        seen.add(url)

    return items


def scrape(headless: bool = True) -> List[Dict[str, Any]]:
    """Scrape Moonshot cards and return normalized content items."""
    driver = build_driver(headless=headless)
    try:
        driver.get(BASE)
        time.sleep(1.0)
        try:
            wait_for_cards(driver, timeout=30)
        except TimeoutException:
            pass
        autoscroll(driver, pause=0.9, max_tries=20)
        raw = extract_items(driver)
    finally:
        driver.quit()

    normalized: List[Dict[str, Any]] = []
    for item in raw:
        title = item.get("title")
        url = item.get("url")
        if not title or not url:
            continue
        published_at = parse_datetime(item.get("date_iso") or item.get("date_display"))
        normalized.append(
            make_lab_item(
                title=title,
                url=url,
                author=item.get("author") or "Moonshot",
                published_at=published_at,
                thumbnail_url=item.get("thumbnail"),
                item_type=item.get("type"),
                source_name="Moonshot",
                extraction_method="selenium",
                date_iso=item.get("date_iso"),
                date_display=item.get("date_display"),
            )
        )
    return normalized
