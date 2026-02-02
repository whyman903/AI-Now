"""Dwarkesh Podcast scraper plugin (Apple Podcasts)."""
from typing import Any, Dict, List

from app.services.aggregation.registry import register
from app.services.aggregation.utils.podcast import scrape_apple_podcast

PODCAST_URL = "https://podcasts.apple.com/us/podcast/dwarkesh-podcast/id1516093381"


@register(
    key="scrape_dwarkesh_podcast",
    name="Dwarkesh Podcast",
    category="learning",
    content_types=["podcast"],
    requires_selenium=True,
)
def scrape(headless: bool = True) -> List[Dict[str, Any]]:
    return scrape_apple_podcast(
        podcast_url=PODCAST_URL,
        podcast_name="Dwarkesh Podcast",
        author_name="Dwarkesh Patel",
        headless=headless,
        category="learning",
    )
