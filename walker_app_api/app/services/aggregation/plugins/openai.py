"""OpenAI blog scraper plugin."""
from typing import Any, Dict, List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from app.services.aggregation.registry import register
from app.services.aggregation.utils.date_parser import parse_date
from app.services.aggregation.utils.html import make_item, normalize_whitespace
from app.services.aggregation.utils.webdriver import autoscroll_page, create_chrome_driver

BASE = "https://openai.com"
START_URL = "https://openai.com/research/index/?display=grid"


def build_driver(headless: bool = True) -> webdriver.Chrome:
    return create_chrome_driver(headless=headless, window_size="1400,1000")


def wait_for_grid(driver, timeout=20):
    sel = "a[aria-label][href^='/index/']"
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, sel))
    )


def autoscroll_to_bottom(driver, pause=0.8, max_tries=20):
    autoscroll_page(driver, pause=pause, max_attempts=max_tries)


def extract_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    items = []

    for a in soup.select("a[aria-label][href^='/index/']"):
        try:
            title_node = a.select_one(".mb-2xs, .text-h5, h2, h3")
            title = None
            if title_node:
                title = normalize_whitespace(title_node.get_text(strip=True))
            if not title:
                aria = a.get("aria-label")
                if aria:
                    primary = aria.split(" - ")[0] if " - " in aria else aria
                    title = normalize_whitespace(primary)

            time_node = a.select_one("time[datetime]") or a.select_one("time")
            date_iso = (
                time_node.get("datetime")
                if time_node and time_node.has_attr("datetime")
                else None
            )
            date_display = (
                normalize_whitespace(time_node.get_text(strip=True))
                if time_node
                else None
            )

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
                "author": "OpenAI",
                "type": "research_lab",
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


@register(
    key="scrape_openai",
    name="OpenAI",
    category="frontier_model",
    content_types=["research_lab", "article"],
    requires_selenium=True,
)
def scrape(headless: bool = True) -> List[Dict[str, Any]]:
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
        title = item.get("title")
        url = item.get("url")
        if not title or not url:
            continue
        published_at = parse_date(item.get("date_iso") or item.get("date_display"))
        normalized.append(
            make_item(
                title=title,
                url=url,
                author=item.get("author") or "OpenAI",
                published_at=published_at,
                thumbnail_url=item.get("thumbnail"),
                item_type=item.get("type"),
                source_name="OpenAI",
                extraction_method="selenium",
                date_iso=item.get("date_iso"),
                date_display=item.get("date_display"),
            )
        )
    return normalized
