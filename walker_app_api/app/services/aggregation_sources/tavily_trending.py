import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Set

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.grok import GrokProvider
from pydantic_ai.tools import Tool
from tavily import AsyncTavilyClient
from tavily.errors import BadRequestError

from app.core.config import settings

logger = logging.getLogger(__name__)


MAX_TAVILY_RETRIES = 2
RETRY_DELAY_SECONDS = 1.0
MAX_TAVILY_QUERY_LENGTH = 380
TAVILY_SUMMARY_TIMEOUT_SECONDS = 75

_tavily_client: Optional[AsyncTavilyClient] = None


def _get_tavily_client() -> AsyncTavilyClient:
    global _tavily_client
    if _tavily_client is None:
        _tavily_client = AsyncTavilyClient(settings.TAVILY_API_KEY)
    return _tavily_client


async def _safe_tavily_search(
    query: str,
    search_deep: Literal["basic", "advanced"] = "basic",
    topic: Literal["general", "news"] = "general",
    time_range: Literal["day", "week", "month", "year", "d", "w", "m", "y"] | None = None,
):
    normalized_query = (query or "").strip()
    if len(normalized_query) > MAX_TAVILY_QUERY_LENGTH:
        logger.warning(
            "Trimming Tavily query from %s to %s characters",
            len(normalized_query),
            MAX_TAVILY_QUERY_LENGTH,
        )
        normalized_query = normalized_query[:MAX_TAVILY_QUERY_LENGTH]

    client = _get_tavily_client()
    results = await client.search(
        normalized_query,
        search_depth=search_deep,
        topic=topic,
        time_range=time_range,
    )
    return results.get("results", [])


SAFE_TAVILY_SEARCH_TOOL = Tool[Any](
    _safe_tavily_search,
    name="tavily_search",
    description="Searches Tavily with auto-trimming to stay under query limits.",
)


def _format_digest(raw_digest: str) -> str:
    """Normalize the LLM response so we always return a clean numbered list."""

    if not raw_digest:
        return raw_digest

    cleaned_lines: List[str] = []
    seen: Set[str] = set()
    for line in raw_digest.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower().startswith("final answer"):
            continue
        if stripped.startswith("<") and stripped.endswith(">"):
            continue
        normalized = re.sub(r"^\d+\.\s*", "", stripped)
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned_lines.append(normalized)

    if not cleaned_lines:
        return raw_digest.strip()

    max_items = 5
    cleaned_lines = cleaned_lines[:max_items]
    return "\n".join(f"{idx}. {text}" for idx, text in enumerate(cleaned_lines, 1))


class TrendingSummary(BaseModel):
    """AI-generated summary of current AI trends."""

    markdown_news_digest: str = Field(
        description="""
        A numbered list of 5 AI news items in markdown format. 
        Start directly with '1.' - do NOT include any title, heading, or introduction.
        Each item should 1-2 sentence snippet with **key terms and important names bolded inline**.
        Do NOT use a separate bolded headline - weave the bolded terms naturally into the flowing text.
        End each item with an inline citation: [Source Name](URL).
        """
    )


async def _generate_ai_trends_summary() -> TrendingSummary:
    """Generate a concise summary of what's trending in AI using Tavily."""

    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    prompt = f"""Today is {today}. Find the MOST GROUNDBREAKING AI news from the past 3-5 days and return a numbered list.

            IMPORTANT: When using the Tavily search tool, use SHORT search queries under 400 characters. 
            Examples: "major AI model releases October 2025", "OpenAI GPT Claude Gemini announcements", "AI breakthrough research this week"
            
            Start directly with "1." - do NOT include any title, heading, introduction, or preamble.

            WHAT COUNTS AS GROUNDBREAKING:
            - Major AI model launches from top labs - NOT beta tests
            - Revolutionary new capabilities or benchmarks (AGI milestones, new reasoning abilities)
            - Game-changing product launches (ChatGPT Canvas, Google Astra, AI agents)
            - Massive funding ($1B+) or valuations ($10B+) for major AI companies
            - Breakthrough research papers that shift the field
            - Major acquisitions or IPOs in AI space
            
            STRICT EXCLUSIONS:
            - Hardware partnerships (GPU deals, chip agreements)
            - Routine funding rounds under $1B
            - Partnerships between companies unless they're industry-defining
            - Pre-release testing, A/B tests, rumors
            - Consumer hardware products
            - Startups with <$5B valuation
            - Crime, misuse, or controversy stories

            CRITICAL SOURCE REQUIREMENTS:
            - You MUST use authoritative sources: TechCrunch, The Verge, Bloomberg, Reuters, Wired, MIT Technology Review, Financial Times, WSJ, official company blogs
            - If a story is ONLY available on low-quality sites (ts2.tech, TestingCatalog, SEO blogs), SKIP IT and find a different story
            - Each citation must be from a tier-1 source or official company announcement

            TENSE: Use PAST TENSE for completed events. If DevDay was October 6 and today is October 8, write "OpenAI announced" NOT "OpenAI is set to announce".

            FORMAT:
            - ONE punchy sentence per item
            - Bold **key terms** inline
            - End with: [Source Name](URL)
            
            Example: "**OpenAI** launched **ChatGPT Canvas**, a new collaborative interface enabling direct document editing within conversations. [The Verge](https://example.com)"

            Provide 5 TRULY GROUNDBREAKING items. Quality over quantity - if you can't find 5 with tier-1 sources, provide fewer.
        """
    agent = Agent(
        OpenAIChatModel("grok-4-1-fast", provider=GrokProvider(api_key=settings.XAI_API_KEY)),
        output_type=TrendingSummary,
        system_prompt=(
            """You are an AI news aggregator agent with access to the Tavily search tool. 

                YOUR CAPABILITIES:
                - Search for recent news and developments in AI
                - Analyze and summarize information from multiple sources
                - Present findings in clear, organized formats with proper citations

                CITATION REQUIREMENTS:
                - Always provide inline citations for every piece of information
                - Format citations as: [Source Name](URL)
                - Ensure URLs are complete and accessible
                - Each news item must include its source

                OUTPUT STANDARDS:
                - Write clear, concise summaries
                - Focus on factual reporting, not speculation
                - Prioritize authoritative sources

            TOPIC FILTER:
                - Avoid AI safety, ethics, misuse, regulation, or content-moderation stories.
                - Focus only on technical, commercial, or research breakthroughs in AI.
            """
        ),
        tools=[SAFE_TAVILY_SEARCH_TOOL],
    )

    for attempt in range(1, MAX_TAVILY_RETRIES + 1):
        try:
            result = await asyncio.wait_for(
                agent.run(prompt),
                timeout=TAVILY_SUMMARY_TIMEOUT_SECONDS,
            )
            return result.output
        except asyncio.TimeoutError:
            logger.warning(
                "AI trends summary timed out (attempt %s/%s)",
                attempt,
                MAX_TAVILY_RETRIES,
            )
            if attempt == MAX_TAVILY_RETRIES:
                raise
        except BadRequestError as exc:
            logger.warning(
                "Tavily search failed (attempt %s/%s): %s",
                attempt,
                MAX_TAVILY_RETRIES,
                exc,
            )
            if attempt == MAX_TAVILY_RETRIES:
                raise
        except Exception as exc:
            logger.warning(
                "AI trends summary attempt %s/%s failed: %s",
                attempt,
                MAX_TAVILY_RETRIES,
                exc,
                exc_info=True,
            )
            if attempt == MAX_TAVILY_RETRIES:
                raise

        await asyncio.sleep(RETRY_DELAY_SECONDS)


async def scrape_async() -> List[Dict[str, Any]]:
    """Async entry point for the content aggregator."""
    try:
        trends = await _generate_ai_trends_summary()
    except Exception as exc:
        logger.error("AI trends summary generation failed: %s", exc, exc_info=True)
        return []

    digest = _format_digest(trends.markdown_news_digest)
    timestamp = datetime.now(timezone.utc).replace(tzinfo=None)
    return [
        {
            "title": "AI Trends Digest",
            "url": "#",
            "published_at": timestamp,
            "meta_data": {
                "source_name": "Tavily AI Trends",
                "summary": digest,
                "generated_by": "pydantic_ai",
                "model": "grok-4-1-fast",
                "search_engine": "tavily",
                "generated_at": timestamp.isoformat(),
            },
        }
    ]


def scrape() -> List[Dict[str, Any]]:
    """Backward-compatible synchronous entry point."""
    try:
        return asyncio.run(scrape_async())
    except RuntimeError as exc:
        raise RuntimeError(
            "tavily_trending.scrape() cannot run inside an active event loop; "
            "await scrape_async() instead."
        ) from exc
