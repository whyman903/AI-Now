#!/usr/bin/env python3
"""Dwarkesh Podcast scraper."""
from typing import Any, Dict, List

from ._apple_podcast_scraper import scrape_apple_podcast

PODCAST_URL = "https://podcasts.apple.com/us/podcast/dwarkesh-podcast/id1516093381"
PODCAST_NAME = "Dwarkesh Podcast"
AUTHOR_NAME = "Dwarkesh Patel"


def scrape(headless: bool = True) -> List[Dict[str, Any]]:
    """Scrape Dwarkesh Podcast from Apple Podcasts."""
    return scrape_apple_podcast(
        podcast_url=PODCAST_URL,
        podcast_name=PODCAST_NAME,
        author_name=AUTHOR_NAME,
        headless=headless,
        category="learning",
    )

