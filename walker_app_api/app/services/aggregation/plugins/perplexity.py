"""Perplexity AI blog scraper plugin."""
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

from app.services.aggregation.registry import register
from app.services.aggregation.utils.date_parser import parse_date
from app.services.aggregation.utils.html import make_item, normalize_whitespace
from app.services.aggregation.utils.webdriver import autoscroll_page, create_chrome_driver

BASE = "https://research.perplexity.ai"
START_URL = "https://research.perplexity.ai"


def build_driver(headless: bool = True) -> webdriver.Chrome:
    return create_chrome_driver(headless=headless, window_size="1400,1400")


def wait_for_articles(driver, timeout=25):
    sel = "a[href^='./articles/'], a[href*='/articles/']"
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, sel))
    )


def autoscroll_to_bottom(driver, pause=0.8, max_tries=20):
    autoscroll_page(driver, pause=pause, max_attempts=max_tries)


def parse_date_text(text: str):
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

    anchors = soup.select("a[href^='./articles/'], a[href*='/articles/']")

    for a in anchors:
        href = a.get("href")
        if not href:
            continue

        if href.startswith("./"):
            href = href[2:]
        url = urljoin(BASE, href)

        if url in seen:
            continue

        title_node = a.select_one("h3") or a.select_one("h5")
        title = (
            normalize_whitespace(title_node.get_text(strip=True))
            if title_node
            else None
        )

        category = None
        date_text = None

        meta_paragraphs = a.select("p.framer-text.framer-styles-preset-q2pox2")
        for p in meta_paragraphs:
            text = normalize_whitespace(p.get_text(strip=True))
            if not text:
                continue
            if any(month in text for month in ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]):
                date_text = text
            else:
                category = text

        date_iso, date_display = parse_date_text(date_text)

        description = None
        desc_node = a.select_one("p.framer-text.framer-styles-preset-tre3a4")
        if not desc_node:
            desc_node = a.select_one("p.framer-text.framer-styles-preset-isgb9l")
        if desc_node:
            description = normalize_whitespace(desc_node.get_text(strip=True))

        img = a.select_one("img")
        thumbnail = None
        if img:
            if img.has_attr("srcset"):
                best = pick_best_src_from_srcset(img["srcset"])
                thumbnail = best or img.get("src")
            else:
                thumbnail = img.get("src")

        if thumbnail and not thumbnail.startswith(("http://", "https://")):
            thumbnail = urljoin(BASE, thumbnail)

        items.append({
            "title": title,
            "date_iso": date_iso,
            "date_display": date_display,
            "thumbnail": thumbnail,
            "url": url,
            "author": "Perplexity",
            "type": "research_lab",
            "category": category,
            "description": description,
        })
        seen.add(url)

    return items


@register(
    key="scrape_perplexity",
    name="Perplexity",
    category="frontier_model",
    content_types=["research_lab", "article"],
    requires_selenium=True,
)
def scrape(headless: bool = True) -> List[Dict[str, Any]]:
    driver = build_driver(headless=headless)
    try:
        driver.get(START_URL)
        time.sleep(1.5)
        try:
            wait_for_articles(driver, timeout=30)
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
        published_at = parse_date(item.get("date_iso") or item.get("date_display"))

        extra_meta = {}
        if item.get("description"):
            extra_meta["summary"] = item["description"]
        if item.get("category"):
            extra_meta["research_category"] = item["category"]

        normalized.append(
            make_item(
                title=title,
                url=url,
                author=item.get("author") or "Perplexity",
                published_at=published_at,
                thumbnail_url=item.get("thumbnail"),
                item_type=item.get("type"),
                source_name="Perplexity",
                extraction_method="selenium",
                date_iso=item.get("date_iso"),
                date_display=item.get("date_display"),
                extra_meta=extra_meta or None,
            )
        )
    return normalized
