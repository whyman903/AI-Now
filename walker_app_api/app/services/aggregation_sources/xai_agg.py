#!/usr/bin/env python3
"""
Scrape x.ai/news (Selenium):
  https://x.ai/news

Extracts per post: title, date_iso, date_display, thumbnail, url
Prints JSON to stdout and (optionally) writes CSV via --csv.

Usage:
  python xai_news_scrape_selenium.py [--csv out.csv] [--no-headless]
"""

import re
import json
import csv
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

BASE = "https://x.ai"
START_URL = "https://x.ai/news"

BG_URL_RE = re.compile(r'url\((["\']?)(.*?)\1\)')

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

    # Hide webdriver flag
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"}
    )
    return driver

def wait_for_news(driver, timeout=20):
    # Wait until at least one news anchor is present
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

def parse_date(d: str) -> tuple[str | None, str | None]:
    if not d:
        return None, None
    d_disp = normalize(d)
    try:
        dt = dateparser.parse(d_disp, fuzzy=True)
        return dt.isoformat(), d_disp
    except Exception:
        # Fallback: try common format (e.g., "August 28, 2025")
        try:
            dt = datetime.strptime(d_disp, "%B %d, %Y")
            return dt.isoformat(), d_disp
        except Exception:
            return None, d_disp

def extract_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen_urls = set()

    # Strategy:
    # - Iterate all anchors leading to /news/... (there can be duplicate anchors per card)
    # - For each anchor, climb to the top card wrapper that also contains the date and the image block.
    # - Extract title from the <h3> under the <a>.
    # - Extract date from a nearby <p class="mono-tag"> within the same card wrapper.
    # - Extract thumbnail from a sibling block having inline style with background-image.
    for a in soup.select("a[href^='/news/']"):
        href = a.get("href")
        if not href:
            continue
        url = urljoin(BASE, href)

        # Skip duplicates early
        if url in seen_urls:
            continue

        # Title: prefer h3 within this anchor
        h3 = a.find("h3")
        title = normalize(h3.get_text(strip=True)) if h3 else None
        if not title:
            # fallback: anchor text itself
            title = normalize(a.get_text(strip=True)) or None

        # Find a reasonable "card wrapper": climb parents until we see a block that contains date + possibly image
        wrapper = None
        cur = a
        for _ in range(8):  # climb up a few levels max
            cur = cur.parent
            if not cur or getattr(cur, "name", None) is None:
                break
            # Heuristics: a wrapper that has date node and/or the background-image block and flex layout
            has_date = bool(cur.select_one("p.mono-tag"))
            has_bg = bool(cur.select_one("div[style*='background-image']"))
            if has_date or has_bg:
                wrapper = cur
                # keep climbing a bit to find the topmost such wrapper (but bounded)
        if wrapper is None:
            wrapper = a.parent

        # Date
        date_node = wrapper.select_one("p.mono-tag") if wrapper else None
        date_iso, date_display = parse_date(date_node.get_text(strip=True) if date_node else None)

        # Thumbnail (background-image in sibling/child div)
        bg_div = wrapper.select_one("div[style*='background-image']") if wrapper else None
        thumb_rel = extract_bg_url(bg_div.get("style")) if bg_div else None
        thumbnail = urljoin(BASE, thumb_rel) if thumb_rel else None

        # Finalize item
        items.append({
            "title": title,
            "date_iso": date_iso,
            "date_display": date_display,
            "thumbnail": thumbnail,
            "url": url,
            "author": 'XAI', 
            "type": "research_lab"
        })
        seen_urls.add(url)

    return items

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="Write results to CSV as well")
    ap.add_argument("--no-headless", action="store_true", help="Run with a visible browser")
    args = ap.parse_args()

    driver = build_driver(headless=not args.no_headless)
    try:
        driver.get(START_URL)
        # Slight delay lets client-side layout settle
        time.sleep(1.0)
        wait_for_news(driver, timeout=25)
        autoscroll_to_bottom(driver, pause=0.9, max_tries=20)
        html = driver.page_source
    except TimeoutException:
        html = driver.page_source
    finally:
        driver.quit()

    data = extract_from_html(html)

    # Emit JSON
    print(json.dumps(data, indent=2, ensure_ascii=False))

    # Optional CSV
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["title", "date_iso", "date_display", "thumbnail", "url"])
            w.writeheader()
            for row in data:
                w.writerow(row)

if __name__ == "__main__":
    main()