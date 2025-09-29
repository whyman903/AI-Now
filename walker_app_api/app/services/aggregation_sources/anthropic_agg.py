#!/usr/bin/env python3
import time
from datetime import datetime
from typing import Any, Dict, List
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from ._lab_scraper_utils import (
    autoscroll_page,
    create_chrome_driver,
    make_lab_item,
    normalize_whitespace,
    parse_datetime,
)

BASE = "https://www.anthropic.com"
START_URL = "https://www.anthropic.com/news"

def build_driver(headless: bool = True) -> webdriver.Chrome:
    return create_chrome_driver(headless=headless, window_size="1400,1400")

def wait_for_cards(driver, timeout=25):
    sel = ("a.PostCard_post-card__z_Sqq,"
           "a[class*='PostCard_post-card__'],"
           "a.Card_linkRoot__alQfM,"
           "a[class*='Card_linkRoot__']")
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, sel))
    )

def autoscroll_to_bottom(driver, pause=0.8, max_tries=20):
    autoscroll_page(driver, pause=pause, max_attempts=max_tries)

def parse_date_text(text: str):
    """Return (iso, display) for 'Sep 15, 2025' etc."""
    if not text:
        return None, None
    disp = normalize_whitespace(text)
    for fn in (
        lambda x: dateparser.parse(x, fuzzy=True),
        lambda x: datetime.strptime(x, "%b %d, %Y"),
        lambda x: datetime.strptime(x, "%B %d, %Y"),
    ):
        try:
            dt = fn(disp)
            return dt.isoformat(), disp
        except Exception:
            pass
    return None, disp

def pick_best_src_from_srcset(srcset: str) -> str | None:
    """
    From a srcset like 'url&w=256 256w, url&w=384 384w, ...',
    pick the last (largest) candidate.
    """
    if not srcset:
        return None
    parts = [p.strip() for p in srcset.split(",") if p.strip()]
    if not parts:
        return None
    last = parts[-1].split()[0]
    return last

def extract_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    items, seen = [], set()

    anchors = soup.select(
        "a.PostCard_post-card__z_Sqq, a[class*='PostCard_post-card__'], "
        "a.Card_linkRoot__alQfM, a[class*='Card_linkRoot__']"
    )

    for a in anchors:
        href = a.get("href")
        if not href:
            continue
        url = urljoin(BASE, href)
        if url in seen:
            continue

        title_node = a.select_one("h3.PostCard_post-heading__Ob1pu, h3[class*='PostCard_post-heading__']")
        if not title_node:
            title_node = a.select_one("h3.Card_headline__reaoT, h3[class*='Card_headline__']")
        if not title_node:
            title_node = a.select_one("h3")
        title = (
            normalize_whitespace(title_node.get_text(strip=True))
            if title_node
            else None
        )

        date_node = a.select_one("div.PostList_post-date__djrOA, div[class*='PostList_post-date__']")
        if not date_node:
            date_node = a.select_one("p.detail-m.agate")
        if not date_node:
            date_node = a.select_one("time[datetime], time")
        date_text = (
            date_node.get("datetime")
            if (date_node and date_node.name == "time" and date_node.has_attr("datetime"))
            else (
                normalize_whitespace(date_node.get_text(strip=True))
                if date_node
                else None
            )
        )
        date_iso, date_display = parse_date_text(date_text)

        img = a.select_one("img")
        thumbnail = None
        if img:
            if img.has_attr("srcset"):
                best = pick_best_src_from_srcset(img["srcset"])
                thumbnail = best or img.get("src")
            else:
                thumbnail = img.get("src")
        if thumbnail and thumbnail.startswith("/"):
            thumbnail = urljoin(BASE, thumbnail)

        items.append({
            "title": title,
            "date_iso": date_iso,
            "date_display": date_display,
            "thumbnail": thumbnail,
            "url": url,
            "author": 'Anthropic',
            "type": "research_lab"
        })
        seen.add(url)

    return items


def scrape(headless: bool = True) -> List[Dict[str, Any]]:
    """Scrape Anthropic news and return normalized content items."""
    driver = build_driver(headless=headless)
    try:
        driver.get(START_URL)
        time.sleep(1.0)
        try:
            wait_for_cards(driver, timeout=30)
        except TimeoutException:
            pass
        autoscroll_to_bottom(driver, pause=0.9, max_tries=24)
        html = driver.page_source
    finally:
        driver.quit()

    raw_items = extract_from_html(html)
    normalized: List[Dict[str, Any]] = []
    for item in raw_items:
        title = item.get("title")
        url = item.get("url")
        if not title or not url:
            continue
        published_at = parse_datetime(item.get("date_iso") or item.get("date_display"))
        normalized.append(
            make_lab_item(
                title=title,
                url=url,
                author=item.get("author") or "Anthropic",
                published_at=published_at,
                thumbnail_url=item.get("thumbnail"),
                item_type=item.get("type"),
                source_name="Anthropic",
                extraction_method="selenium",
                date_iso=item.get("date_iso"),
                date_display=item.get("date_display"),
            )
        )
    return normalized
