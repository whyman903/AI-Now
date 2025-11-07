#!/usr/bin/env python3
"""Generic Apple Podcasts scraper."""
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup, Tag
from dateutil import parser as dateparser
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from ._lab_scraper_utils import (
    create_chrome_driver,
    make_lab_item,
    normalize_whitespace,
)

BASE_URL = "https://podcasts.apple.com"

LOAD_WAIT_TIME = 3.0
SCROLL_ITERATIONS = 5
SCROLL_WAIT = 1.5
SCROLL_INCREMENTAL_WAIT = 0.5
FINAL_WAIT = 2.0

EPISODE_SELECTORS = [
    "li[data-testid^='episode-lockup']",
    "li.episode",
    "div[class*='episode-details']",
]

TITLE_SELECTORS = [
    "[data-testid='episode-lockup-title']",
    "h3[class*='episode-details__title']",
    "span[class*='episode-details__title']",
    "h3",
]

DATE_SELECTORS = [
    "[data-testid='episode-details__published-date']",
    "p[class*='episode-details__published-date']",
    "time",
]

DESCRIPTION_SELECTORS = [
    "[data-testid='episode-content__summary']",
    "div[class*='episode-details__summary']",
    "p[class*='episode-details__summary']",
]

DURATION_SELECTORS = [
    "div[class*='episode-details__meta']",
    "span[class*='duration']",
]

ARTWORK_SELECTORS = [
    "div[class*='episode-wrapper__play-button-wrapper--artwork']",
    "div[class*='artwork-overlay']",
    "div[data-testid='track-play-button']",
]


def _wait_for_episodes(driver, timeout: int = 25) -> None:
    """Wait for episode elements to load on the page."""
    for selector in EPISODE_SELECTORS:
        try:
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            return
        except TimeoutException:
            continue


def _parse_relative_date(text: str) -> Optional[datetime]:
    """Parse relative dates ('8H AGO') or absolute dates ('OCT 21') into datetime objects."""
    if not text:
        return None
    
    text = text.strip().upper()
    now = datetime.utcnow()
    
    relative_pattern = r'(\d+)\s*([HDWMY])\s*AGO'
    match = re.match(relative_pattern, text)
    
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        
        unit_map = {
            'H': timedelta(hours=value),
            'D': timedelta(days=value),
            'W': timedelta(weeks=value),
            'M': timedelta(days=value * 30),
            'Y': timedelta(days=value * 365),
        }
        
        return now - unit_map.get(unit, timedelta())
    
    if not re.search(r'\d{4}', text):
        text = f"{text} {now.year}"
    
    try:
        return dateparser.parse(text, fuzzy=True)
    except Exception:
        return None


def _parse_duration(text: str) -> Optional[int]:
    """Parse duration text ('38 min', '1 hr 5 min', '2h 25m') into seconds."""
    if not text:
        return None
    
    text = text.strip().lower()
    total_seconds = 0
    
    hours_match = re.search(r'(\d+)\s*h(?:r|rs?)?', text)
    if hours_match:
        total_seconds += int(hours_match.group(1)) * 3600
    
    minutes_match = re.search(r'(\d+)\s*m(?:in)?', text)
    if minutes_match:
        total_seconds += int(minutes_match.group(1)) * 60
    
    return total_seconds if total_seconds > 0 else None


def _find_element_text(episode: Tag, selectors: List[str]) -> Optional[str]:
    """Find and extract text from the first matching selector."""
    for selector in selectors:
        element = episode.select_one(selector)
        if element:
            text = element.get_text(strip=True)
            if text:
                return normalize_whitespace(text)
    return None


def _extract_title(episode: Tag) -> Optional[str]:
    """Extract episode title from episode element."""
    for selector in TITLE_SELECTORS:
        elem = episode.select_one(selector)
        if elem:
            text = elem.get_text(strip=True)
            if text:
                return normalize_whitespace(text)
    
    link = episode.find("a", title=True)
    if link and link.get("title"):
        return normalize_whitespace(link["title"])
    
    return None


def _extract_url(episode: Tag) -> Optional[str]:
    """Extract episode URL from episode element."""
    link = episode.find("a", href=True)
    if not link or not link.get("href"):
        return None
    
    href = link["href"]
    
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return f"{BASE_URL}{href}"
    
    return None


def _extract_episode_id(url: Optional[str]) -> Optional[str]:
    """Extract episode ID from URL for uniqueness tracking."""
    if url and "/episode/" in url:
        return url.split("/episode/")[-1].split("?")[0]
    return None


def _extract_published_date(episode: Tag) -> Optional[datetime]:
    """Extract and parse episode published date."""
    for selector in DATE_SELECTORS:
        elem = episode.select_one(selector)
        if elem:
            date_text = elem.get("datetime") if elem.name == "time" else elem.get_text(strip=True)
            if date_text:
                return _parse_relative_date(date_text)
    return None


def _extract_duration(episode: Tag) -> Optional[int]:
    """Extract episode duration in seconds."""
    for selector in DURATION_SELECTORS:
        elem = episode.select_one(selector)
        if elem:
            text = elem.get_text(strip=True)
            if text:
                duration = _parse_duration(text)
                if duration:
                    return duration
    return None


def _extract_thumbnail_from_style(element: Tag) -> Optional[str]:
    """Extract thumbnail URL from CSS background-image property."""
    style = element.get("style", "")
    if "background-image" in style:
        match = re.search(r'background-image:\s*url\(["\']?([^"\'()]+)["\']?\)', style)
        if match:
            return match.group(1)
    return None


def _extract_thumbnail_from_data_attrs(element: Tag) -> Optional[str]:
    """Extract thumbnail URL from data attributes."""
    data_attrs = ['data-src', 'data-image', 'data-artwork', 'data-poster']
    for attr in data_attrs:
        value = element.get(attr)
        if value:
            return value
    return None


def _extract_thumbnail_from_img(element: Tag) -> Optional[str]:
    """Extract thumbnail URL from img element or srcset."""
    if not element:
        return None
    
    img = element.find("img")
    if not img:
        return None
    
    src = img.get("src")
    if src:
        return src
    
    srcset = img.get("srcset", "")
    if srcset:
        urls = [s.strip().split()[0] for s in srcset.split(",") if s.strip()]
        if urls:
            return urls[0]
    
    return img.get("data-src")


def _normalize_thumbnail_url(url: Optional[str]) -> Optional[str]:
    """Normalize and convert relative thumbnail URLs to absolute."""
    if not url:
        return None
    
    url = url.strip()
    
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"{BASE_URL}{url}"
    
    return url


def _extract_thumbnail(episode: Tag) -> Optional[str]:
    """Extract episode thumbnail/artwork using multiple strategies."""
    for selector in ARTWORK_SELECTORS:
        artwork = episode.select_one(selector)
        if artwork:
            thumbnail = _extract_thumbnail_from_style(artwork)
            if thumbnail:
                return _normalize_thumbnail_url(thumbnail)
            
            thumbnail = _extract_thumbnail_from_data_attrs(artwork)
            if thumbnail:
                return _normalize_thumbnail_url(thumbnail)
            
            thumbnail = _extract_thumbnail_from_img(artwork.parent)
            if thumbnail:
                return _normalize_thumbnail_url(thumbnail)
    
    picture = episode.find("picture")
    if picture:
        source = picture.find("source")
        if source and source.get("srcset"):
            urls = [s.strip().split()[0] for s in source["srcset"].split(",") if s.strip()]
            if urls:
                return _normalize_thumbnail_url(urls[0])
    
    thumbnail = _extract_thumbnail_from_img(episode)
    return _normalize_thumbnail_url(thumbnail)


def _create_unique_key(title: str, episode_id: Optional[str]) -> str:
    """Create unique identifier for deduplication."""
    return f"{title}||{episode_id}" if episode_id else title


def _create_fallback_url(title: str, podcast_url: str) -> str:
    """Create fallback URL when no episode-specific URL is found."""
    url_title = title.lower().replace(" ", "-").replace(":", "")[:50]
    return f"{podcast_url}?episode={url_title}"


def _find_episodes(soup: BeautifulSoup) -> List[Tag]:
    """Find all episode elements in the parsed HTML."""
    for selector in EPISODE_SELECTORS:
        episodes = soup.select(selector)
        if episodes:
            return episodes
    return []


def extract_from_html(html: str, podcast_url: str) -> List[Dict[str, Any]]:
    """Extract podcast episodes from Apple Podcasts HTML."""
    soup = BeautifulSoup(html, "html.parser")
    items: List[Dict[str, Any]] = []
    seen: set[str] = set()
    
    episodes = _find_episodes(soup)
    
    for episode in episodes:
        title = _extract_title(episode)
        if not title:
            continue
        
        url = _extract_url(episode)
        episode_id = _extract_episode_id(url)
        unique_key = _create_unique_key(title, episode_id)
        
        if unique_key in seen:
            continue
        seen.add(unique_key)
        
        if not url:
            url = _create_fallback_url(title, podcast_url)
        
        items.append({
            "title": title,
            "url": url,
            "published_at": _extract_published_date(episode),
            "description": _find_element_text(episode, DESCRIPTION_SELECTORS),
            "thumbnail": _extract_thumbnail(episode),
            "duration_seconds": _extract_duration(episode),
        })
    
    return items


def _load_page_content(driver, podcast_url: str) -> str:
    """Load the podcast page and return HTML after ensuring all content is loaded."""
    driver.get(podcast_url)
    time.sleep(LOAD_WAIT_TIME)
    
    try:
        _wait_for_episodes(driver, timeout=30)
    except TimeoutException:
        pass
    
    time.sleep(FINAL_WAIT)
    
    for i in range(SCROLL_ITERATIONS):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(SCROLL_WAIT)
        driver.execute_script(f"window.scrollBy(0, {500 * (i + 1)});")
        time.sleep(SCROLL_INCREMENTAL_WAIT)
    
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(FINAL_WAIT)
    
    return driver.page_source


def scrape_apple_podcast(
    podcast_url: str,
    podcast_name: str,
    author_name: str,
    headless: bool = True,
    category: str = "learning"
) -> List[Dict[str, Any]]:
    """
    Generic scraper for any Apple Podcasts show.
    
    Args:
        podcast_url: Full Apple Podcasts URL
        podcast_name: Display name of the podcast
        author_name: Podcast author/host name
        headless: Whether to run browser in headless mode
        category: Content category for the podcast
    
    Returns:
        List of normalized podcast episode dictionaries
    """
    driver = create_chrome_driver(headless=headless, window_size="1400,1400")
    
    try:
        html = _load_page_content(driver, podcast_url)
    finally:
        driver.quit()
    
    raw_items = extract_from_html(html, podcast_url)
    
    normalized = []
    for raw_item in raw_items:
        title = raw_item.get("title")
        url = raw_item.get("url")
        
        if not title or not url:
            continue
        
        extra_meta = {}
        if raw_item.get("description"):
            extra_meta["description"] = raw_item["description"]
        if raw_item.get("duration_seconds"):
            extra_meta["duration_seconds"] = raw_item["duration_seconds"]
        
        normalized.append(
            make_lab_item(
                title=title,
                url=url,
                author=author_name,
                published_at=raw_item.get("published_at"),
                thumbnail_url=raw_item.get("thumbnail"),
                item_type="podcast",
                source_name=podcast_name,
                extraction_method="selenium",
                extra_meta={**extra_meta, "category": category},
            )
        )
    
    return normalized

