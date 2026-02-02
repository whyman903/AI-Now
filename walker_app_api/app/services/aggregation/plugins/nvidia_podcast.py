"""NVIDIA AI Podcast scraper plugin (Apple Podcasts)."""
from typing import Any, Dict, List

from app.services.aggregation.registry import register
from app.services.aggregation.utils.podcast import scrape_apple_podcast

PODCAST_URL = "https://podcasts.apple.com/us/podcast/nvidia-ai-podcast/id1186480811"


@register(
    key="scrape_nvidia_podcast",
    name="NVIDIA AI Podcast",
    category="learning",
    content_types=["podcast"],
    requires_selenium=True,
)
def scrape(headless: bool = True) -> List[Dict[str, Any]]:
    return scrape_apple_podcast(
        podcast_url=PODCAST_URL,
        podcast_name="NVIDIA AI Podcast",
        author_name="NVIDIA",
        headless=headless,
        category="learning",
    )
