#!/usr/bin/env python3
import re
import csv
import json
import time
import argparse
from typing import List, Dict, Any
from urllib.parse import urljoin
from datetime import datetime, timezone

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
        title = normalize(title_node.get_text(strip=True)) if title_node else None

        date_node = a.select_one("div.PostList_post-date__djrOA, div[class*='PostList_post-date__']")
        if not date_node:
            date_node = a.select_one("p.detail-m.agate")
        if not date_node:
            date_node = a.select_one("time[datetime], time")
        date_text = date_node.get("datetime") if (date_node and date_node.name == "time" and date_node.has_attr("datetime")) else (normalize(date_node.get_text(strip=True)) if date_node else None)
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
        published_at = _parse_iso(item.get("date_iso"))
        normalized.append({
            "title": item.get("title"),
            "url": item.get("url"),
            "author": item.get("author", "Anthropic"),
            "published_at": published_at,
            "thumbnail_url": item.get("thumbnail"),
            "type": item.get("type", "article"),
            "meta_data": {
                "source_name": "Anthropic",
                "category": "ai_ml",
                "date_iso": item.get("date_iso"),
                "date_display": item.get("date_display"),
                "extraction_method": "selenium",
            },
        })
    return normalized

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="Write results to CSV as well")
    ap.add_argument("--no-headless", action="store_true")
    args = ap.parse_args()

    data = scrape(headless=not args.no_headless)
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["title", "date_iso", "date_display", "thumbnail", "url"])
            w.writeheader()
            for row in data:
                meta = row.get("meta_data", {})
                w.writerow({
                    "title": row.get("title"),
                    "date_iso": meta.get("date_iso"),
                    "date_display": meta.get("date_display"),
                    "thumbnail": row.get("thumbnail_url"),
                    "url": row.get("url"),
                })

if __name__ == "__main__":
    main()
