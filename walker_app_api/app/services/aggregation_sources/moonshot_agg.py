#!/usr/bin/env python3
"""
Scrape Moonshot.ai homepage cards with Selenium:
  https://www.moonshot.ai/

Extract per card (anchors only):
- title
- date_iso, date_display
- thumbnail (video src or background-image from style)
- url

Usage:
  python moonshot_news_scrape_selenium.py [--csv out.csv] [--no-headless]
"""

import re
import csv
import json
import time
import argparse
from urllib.parse import urljoin, urlparse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

BASE = "https://www.moonshot.ai/"
BG_URL_RE = re.compile(r'background-image\s*:\s*url\((["\']?)(.*?)\1\)', re.I)

def absolutize(u: str | None) -> str | None:
    if not u:
        return None
    if u.startswith("//"):  # protocol-relative
        return "https:" + u
    if u.startswith("/"):
        return urljoin(BASE, u)
    if not urlparse(u).scheme:
        return urljoin(BASE, u)
    return u

def build_driver(headless: bool = True) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1400,1200")
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
    # Hide webdriver flag to reduce bot checks
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"}
    )
    return driver

def wait_for_cards(driver, timeout=25):
    # Wait until at least one K2 or Research anchor appears
    sel = "a[class*='k2Item'], a[class*='researchItem']"
    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))

def autoscroll(driver, pause=0.8, max_tries=15):
    last = driver.execute_script("return document.body.scrollHeight")
    tries = 0
    while tries < max_tries:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause)
        new = driver.execute_script("return document.body.scrollHeight")
        if new == last:
            break
        last = new
        tries += 1

def get_text_safe(root, css):
    try:
        return root.find_element(By.CSS_SELECTOR, css).text.strip()
    except NoSuchElementException:
        return None

def pick_bg_url_from_style(style_val: str | None) -> str | None:
    if not style_val:
        return None
    m = BG_URL_RE.search(style_val)
    return m.group(2) if m else None

def extract_items(driver):
    items, seen = [], set()

    # 1) K2 hero cards (video + title/date inside the same <a>)
    for a in driver.find_elements(By.CSS_SELECTOR, "a[class*='k2Item']"):
        href = a.get_attribute("href")
        if not href:
            continue
        url = absolutize(href)
        if url in seen:
            continue

        title = get_text_safe(a, "h2[class*='title___'], h2")
        date_display = get_text_safe(a, "p[class*='time___'], time")
        date_iso = date_display  # already YYYY-MM-DD on site

        # Thumbnail: <video src> (protocol-relative) or first <img> inside the anchor
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

    # 2) Research cards (background-image on anchor style + title/date inside)
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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="Also write CSV to this path")
    ap.add_argument("--no-headless", action="store_true", help="Run with visible Chrome")
    args = ap.parse_args()

    driver = build_driver(headless=not args.no_headless)
    try:
        driver.get(BASE)
        # Give React/Vue hydration a moment
        time.sleep(1.0)
        wait_for_cards(driver, timeout=30)
        autoscroll(driver, pause=0.9, max_tries=20)
        data = extract_items(driver)
    except TimeoutException:
        # Extract whatever is visible
        data = extract_items(driver)
    finally:
        driver.quit()

    print(json.dumps(data, indent=2, ensure_ascii=False))

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["title", "date_iso", "date_display", "thumbnail", "url"])
            w.writeheader()
            for row in data:
                w.writerow(row)

if __name__ == "__main__":
    main()