#!/usr/bin/env python3
"""NVIDIA AI Podcast scraper."""
from typing import Any, Dict, List

from ._apple_podcast_scraper import scrape_apple_podcast

PODCAST_URL = "https://podcasts.apple.com/us/podcast/nvidia-ai-podcast/id1186480811"
PODCAST_NAME = "NVIDIA AI Podcast"
AUTHOR_NAME = "NVIDIA"


def scrape(headless: bool = True) -> List[Dict[str, Any]]:
    """Scrape NVIDIA AI Podcast from Apple Podcasts."""
    return scrape_apple_podcast(
        podcast_url=PODCAST_URL,
        podcast_name=PODCAST_NAME,
        author_name=AUTHOR_NAME,
        headless=headless,
        category="learning",
    )
