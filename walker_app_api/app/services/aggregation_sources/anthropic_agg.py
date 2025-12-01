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
from selenium.webdriver.common.action_chains import ActionChains
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
START_URLS = [
    "https://www.anthropic.com/news",
    "https://www.anthropic.com/research",
]

def build_driver(headless: bool = True) -> webdriver.Chrome:
    return create_chrome_driver(headless=headless, window_size="1400,1400")

def wait_for_cards(driver, timeout=25):
    sel = ("a[class*='PublicationList_listItem__'],"
           "a.PostCard_post-card__z_Sqq,"
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
        "a[class*='PublicationList_listItem__'], "
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

        title_node = a.select_one("span[class*='PublicationList_title__']")
        if not title_node:
            title_node = a.select_one("h3.PostCard_post-heading__Ob1pu, h3[class*='PostCard_post-heading__']")
        if not title_node:
            title_node = a.select_one("h3.Card_headline__reaoT, h3[class*='Card_headline__']")
        if not title_node:
            title_node = a.select_one("h3, span[role='heading']")
        title = (
            normalize_whitespace(title_node.get_text(strip=True))
            if title_node
            else None
        )

        date_node = a.select_one("time[class*='PublicationList_date__']")
        if not date_node:
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


def extract_items_with_driver(driver: webdriver.Chrome) -> List[Dict[str, Any]]:
    """
    Extract items using live DOM so we can hover each list item and capture the
    corresponding aside illustration image that only appears/updates on hover.
    """
    items: List[Dict[str, Any]] = []
    seen: set[str] = set()
    anchor_selector = (
        "a[class*='PublicationList_listItem__'],"
        "a.PostCard_post-card__z_Sqq,"
        "a[class*='PostCard_post-card__'],"
        "a.Card_linkRoot__alQfM,"
        "a[class*='Card_linkRoot__']"
    )
    aside_img_selector = (
        "aside[class*='PublicationList_aside__'] img,"
        "div[class*='PublicationList_illustrationContainer__'] img"
    )
    anchors = driver.find_elements(By.CSS_SELECTOR, anchor_selector)
    actions = ActionChains(driver)
    last_img_src: str | None = None

    for a in anchors:
        try:
            href = a.get_attribute("href")
            if not href:
                # Handle relative anchors rendered without absolute hrefs
                href = a.get_attribute("data-href") or a.get_attribute("to")
            if not href:
                continue
            url = urljoin(BASE, href)
            if url in seen:
                continue

            # Title
            title_text = None
            try:
                title_el = a.find_element(By.CSS_SELECTOR, "span[class*='PublicationList_title__']")
            except Exception:
                try:
                    title_el = a.find_element(By.CSS_SELECTOR, "h3, span[role='heading']")
                except Exception:
                    title_el = None
            if title_el:
                title_text = normalize_whitespace(title_el.text)

            # Date (prefer visible time text)
            date_iso, date_display = None, None
            date_text = None
            try:
                time_el = a.find_element(By.CSS_SELECTOR, "time")
                date_text = time_el.get_attribute("datetime") or normalize_whitespace(time_el.text)
            except Exception:
                pass
            date_iso, date_display = parse_date_text(date_text)

            # Hover to update aside illustration and capture thumbnail
            thumbnail = None
            try:
                actions.move_to_element(a).perform()
                # Wait briefly for aside image to reflect the hovered item
                end_time = time.time() + 3.0
                while time.time() < end_time:
                    imgs = driver.find_elements(By.CSS_SELECTOR, aside_img_selector)
                    if imgs:
                        img = imgs[0]
                        alt = normalize_whitespace(img.get_attribute("alt") or "")
                        src = img.get_attribute("src") or ""
                        if title_text and alt and alt == title_text and src:
                            thumbnail = src
                            break
                        # Fallback: accept a changed src even if alt doesn't match exactly
                        if src and src != last_img_src:
                            thumbnail = src
                            break
                    time.sleep(0.1)
                if thumbnail:
                    last_img_src = thumbnail
                    if thumbnail.startswith("/"):
                        thumbnail = urljoin(BASE, thumbnail)
            except Exception:
                pass

            items.append({
                "title": title_text,
                "date_iso": date_iso,
                "date_display": date_display,
                "thumbnail": thumbnail,
                "url": url,
                "author": "Anthropic",
                "type": "research_lab",
            })
            seen.add(url)
        except Exception:
            # skip individual failures to keep batch robust
            continue

    return items


def scrape(headless: bool = True) -> List[Dict[str, Any]]:
    """Scrape Anthropic news and research pages and return normalized content items."""
    driver = build_driver(headless=headless)
    all_raw_items = []

    try:
        for url in START_URLS:
            try:
                driver.get(url)
                time.sleep(1.0)
                try:
                    wait_for_cards(driver, timeout=30)
                except TimeoutException:
                    pass
                autoscroll_to_bottom(driver, pause=0.9, max_tries=24)
                # Prefer live DOM extraction so we can fetch hover thumbnails
                live_items = extract_items_with_driver(driver)
                # Fallback to static HTML parse for resilience
                if not live_items:
                    html = driver.page_source
                    all_raw_items.extend(extract_from_html(html))
                else:
                    all_raw_items.extend(live_items)
            except Exception:
                # If a specific page fails, log it (if logger were available) and continue
                continue
    finally:
        driver.quit()

    # Dedup by URL
    seen_urls = set()
    unique_items = []
    for item in all_raw_items:
        u = item.get("url")
        if u and u not in seen_urls:
            seen_urls.add(u)
            unique_items.append(item)

    normalized: List[Dict[str, Any]] = []
    for item in unique_items:
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
