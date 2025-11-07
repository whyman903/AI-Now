"""Central registry describing all ingestable content sources."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List


@dataclass(frozen=True)
class SourceDefinition:
    key: str
    name: str
    channel: str  # rss | youtube | scraper
    category: str
    content_types: List[str]
    description: str | None = None
    default_enabled: bool = True


_SOURCES: List[SourceDefinition] = [
    # RSS sources
    SourceDefinition(
        key="rss_sequoia_capital",
        name="Sequoia Capital",
        channel="rss",
        category="venture",
        content_types=["blog"],
    ),
    # YouTube channels
    SourceDefinition(
        key="yt_openai",
        name="OpenAI",
        channel="youtube",
        category="frontier_model",
        content_types=["youtube_video"],
    ),
    SourceDefinition(
        key="yt_anthropic",
        name="Anthropic",
        channel="youtube",
        category="frontier_model",
        content_types=["youtube_video"],
    ),
    SourceDefinition(
        key="yt_ai_engineer",
        name="AI Engineer",
        channel="youtube",
        category="learning",
        content_types=["youtube_video"],
    ),
    SourceDefinition(
        key="yt_google_deepmind",
        name="Google DeepMind",
        channel="youtube",
        category="frontier_model",
        content_types=["youtube_video"],
    ),
    SourceDefinition(
        key="yt_andrej_karpathy",
        name="Andrej Karpathy",
        channel="youtube",
        category="learning",
        content_types=["youtube_video"],
    ),
    SourceDefinition(
        key="yt_y_combinator",
        name="Y Combinator",
        channel="youtube",
        category="venture",
        content_types=["youtube_video"],
    ),
    SourceDefinition(
        key="yt_sequoia_capital",
        name="Sequoia Capital",
        channel="youtube",
        category="venture",
        content_types=["youtube_video"],
    ),
    SourceDefinition(
        key="yt_a16z",
        name="A16Z",
        channel="youtube",
        category="venture",
        content_types=["youtube_video"],
    ),
    # Scraper-based sources
    SourceDefinition(
        key="scrape_anthropic",
        name="Anthropic",
        channel="scraper",
        category="frontier_model",
        content_types=["article", "news"],
    ),
    SourceDefinition(
        key="scrape_deepseek",
        name="DeepSeek",
        channel="scraper",
        category="frontier_model",
        content_types=["article"],
    ),
    SourceDefinition(
        key="scrape_xai",
        name="xAI",
        channel="scraper",
        category="frontier_model",
        content_types=["article"],
    ),
    SourceDefinition(
        key="scrape_qwen",
        name="Qwen",
        channel="scraper",
        category="frontier_model",
        content_types=["article"],
    ),
    SourceDefinition(
        key="scrape_moonshot",
        name="Moonshot",
        channel="scraper",
        category="frontier_model",
        content_types=["article"],
    ),
    SourceDefinition(
        key="scrape_openai",
        name="OpenAI",
        channel="scraper",
        category="frontier_model",
        content_types=["article", "research_lab"],
    ),
    SourceDefinition(
        key="scrape_google_deepmind",
        name="Google DeepMind",
        channel="scraper",
        category="frontier_model",
        content_types=["research_lab", "article"],
    ),
    SourceDefinition(
        key="scrape_perplexity",
        name="Perplexity",
        channel="scraper",
        category="applied_ai",
        content_types=["article"],
    ),
    SourceDefinition(
        key="scrape_thinking_machines",
        name="Thinking Machines",
        channel="scraper",
        category="frontier_model",
        content_types=["article"],
    ),
    SourceDefinition(
        key="scrape_hugging_face_papers",
        name="Hugging Face Papers",
        channel="scraper",
        category="options",
        content_types=["research_paper"],
    ),
    SourceDefinition(
        key="scrape_tavily_trends",
        name="Tavily AI Trends",
        channel="scraper",
        category="options",
        content_types=["article"],
    ),
    SourceDefinition(
        key="scrape_nvidia_podcast",
        name="NVIDIA AI Podcast",
        channel="scraper",
        category="learning",
        content_types=["podcast"],
        description="The NVIDIA AI Podcast explores how the latest technologies are shaping our world",
    ),
    SourceDefinition(
        key="scrape_dwarkesh_podcast",
        name="Dwarkesh Podcast",
        channel="scraper",
        category="learning",
        content_types=["podcast"],
        description="Deeply researched interviews with leading thinkers",
    ),
]

SOURCES: List[SourceDefinition] = list[SourceDefinition](_SOURCES)
SOURCES_BY_KEY: Dict[str, SourceDefinition] = {source.key: source for source in SOURCES}


def list_sources() -> List[SourceDefinition]:
    return SOURCES


def get_source(key: str) -> SourceDefinition:
    return SOURCES_BY_KEY[key]


def valid_source_keys() -> Iterable[str]:
    return SOURCES_BY_KEY.keys()
