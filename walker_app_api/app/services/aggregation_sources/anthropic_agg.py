#!/usr/bin/env python3
"""
Scrape Anthropic News accurately:
  https://www.anthropic.com/news

Extracts: title, date_iso, date_display, thumbnail, url
Prints JSON to stdout; optional CSV with --csv.

Usage:
  python anthropic_news_scrape_selenium_v2.py [--csv out.csv] [--no-headless]
"""

import re
import csv
import json
import time
import argparse
from urllib.parse import urljoin
from datetime import datetime

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

BASE = "https://www.anthropic.com"
START_URL = "https://www.anthropic.com/news"

MONTH_RE = re.compile(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", re.I)
YEAR_RE = re.compile(r"\b20\d{2}\b")

def build_driver(headless: bool = True) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1400,1400")
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

def wait_for_cards(driver, timeout=25):
    sel = ("a.PostCard_post-card__z_Sqq,"
           "a[class*='PostCard_post-card__'],"
           "a.Card_linkRoot__alQfM,"
           "a[class*='Card_linkRoot__']")
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, sel))
    )

def autoscroll_to_bottom(driver, pause=0.8, max_tries=20):
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

def parse_date_text(text: str):
    """Return (iso, display) for 'Sep 15, 2025' etc."""
    if not text:
        return None, None
    disp = normalize(text)
    # Try robust parse first
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
    # last is usually highest width
    last = parts[-1].split()[0]
    return last

def extract_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    items, seen = [], set()

    # Only iterate <a> cards and read everything FROM INSIDE that <a>
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

        # --- Title ---
        # PostCard variant
        title_node = a.select_one("h3.PostCard_post-heading__Ob1pu, h3[class*='PostCard_post-heading__']")
        # Card variant
        if not title_node:
            title_node = a.select_one("h3.Card_headline__reaoT, h3[class*='Card_headline__']")
        # Generic fallback
        if not title_node:
            title_node = a.select_one("h3")
        title = normalize(title_node.get_text(strip=True)) if title_node else None

        # --- Date (only from inside the anchor) ---
        # 1) Post list date div
        date_node = a.select_one("div.PostList_post-date__djrOA, div[class*='PostList_post-date__']")
        # 2) Card date paragraph (detail-m agate)
        if not date_node:
            date_node = a.select_one("p.detail-m.agate")
        # 3) Any <time> inside anchor
        if not date_node:
            date_node = a.select_one("time[datetime], time")
        date_text = date_node.get("datetime") if (date_node and date_node.name == "time" and date_node.has_attr("datetime")) else (normalize(date_node.get_text(strip=True)) if date_node else None)
        date_iso, date_display = parse_date_text(date_text)

        # --- Thumbnail (only from inside the anchor) ---
        # Prefer explicit <img> within card; choose highest-res from srcset
        img = a.select_one("img")
        thumbnail = None
        if img:
            if img.has_attr("srcset"):
                best = pick_best_src_from_srcset(img["srcset"])
                thumbnail = best or img.get("src")
            else:
                thumbnail = img.get("src")
        # absolutize if needed (handles /_next/image?url=...)
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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="Write results to CSV as well")
    ap.add_argument("--no-headless", action="store_true")
    args = ap.parse_args()

    driver = build_driver(headless=not args.no_headless)
    try:
        driver.get(START_URL)
        time.sleep(1.0)  # let client-side layout settle
        wait_for_cards(driver, timeout=25)
        autoscroll_to_bottom(driver, pause=0.9, max_tries=20)
        html = driver.page_source
    except TimeoutException:
        html = driver.page_source
    finally:
        driver.quit()

    data = extract_from_html(html)
    print(json.dumps(data, indent=2, ensure_ascii=False))

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["title", "date_iso", "date_display", "thumbnail", "url"])
            w.writeheader()
            for row in data:
                w.writerow(row)

if __name__ == "__main__":
    main()