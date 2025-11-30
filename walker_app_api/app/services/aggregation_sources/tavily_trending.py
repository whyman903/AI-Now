import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from openai import AsyncOpenAI
from tavily import AsyncTavilyClient

from app.core.config import settings

logger = logging.getLogger(__name__)


class TrendingSummary(BaseModel):
    """AI-generated summary of current AI trends."""
    markdown_news_digest: str = Field(
        description="A numbered list of 5 AI news items in markdown format."
    )


# Major US/UK tech publications only
TRUSTED_DOMAINS = [
    "techcrunch.com", "theverge.com", "wired.com", "arstechnica.com",
    "bloomberg.com", "reuters.com", "wsj.com", "nytimes.com", "ft.com",
    "cnbc.com", "venturebeat.com", "theinformation.com", "semafor.com",
    "technologyreview.com", "engadget.com", "zdnet.com", "cnet.com",
]


async def _get_tavily_search_results() -> str:
    """Fetches raw search results using Tavily's news topic with domain filtering."""
    tavily_client = AsyncTavilyClient(api_key=settings.TAVILY_API_KEY)
    
    query = "AI model release OR foundation model launch OR LLM update OR AI benchmark OR AGI research OR major AI funding OR AI acquisition -opinion"
    
    try:
        response = await tavily_client.search(
            query=query,
            topic="news",
            search_depth="advanced",
            days=7,
            max_results=12,
            include_domains=TRUSTED_DOMAINS,
        )
        
        results = response.get("results", [])
        if not results:
            return "No recent news found."
            
        formatted_results = []
        for r in results:
            published_date = r.get('published_date') or r.get('publishedDate') or ''
            date_str = f"\nPublished: {published_date}" if published_date else ""
            formatted_results.append(
                f"Source: {r['title']}\nURL: {r['url']}{date_str}\nContent: {r['content']}\n---"
            )
            
        return "\n".join(formatted_results)
        
    except Exception as e:
        logger.error(f"Tavily search failed: {e}")
        return ""

async def _generate_ai_trends_summary() -> TrendingSummary:
    """Pipeline: Search Tavily -> Summarize with LLM (Grok)"""
    
    search_context = await _get_tavily_search_results()
    
    if not search_context or search_context == "No recent news found.":
        return TrendingSummary(markdown_news_digest="No significant AI news found in the last 3 days.")

    client = AsyncOpenAI(
        api_key=settings.XAI_API_KEY, 
        base_url="https://api.x.ai/v1"
    )

    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    
    prompt = f"""
    Today is {today}. Based on the SEARCH RESULTS below, write a "Trending AI" digest.
    
    SEARCH RESULTS:
    {search_context}
    
    INSTRUCTIONS:
    - Select the top 5 most significant stories (model releases, major announcements, $500M+ funding, field-changing moves).
    - SKIP: listicles, opinion pieces, minor enterprise deals, routine security patches, rate limits,"AI is changing X" fluff.
    - **No duplicates.** One story per event.
    - Start with "1." (numbered list). 1-2 sentences each.
    - **Bold key names/terms**. End with [Source](URL) YYYY/MM/DD.
    
    Example:
    1. Anthropic released **Claude Opus 4.5**, claiming 50% improvement on SWE-bench. [TechCrunch](https://techcrunch.com/...) 11/28/2025.
    """

    try:
        response = await client.chat.completions.create(
            model="grok-4-1-fast", 
            messages=[
                {"role": "system", "content": "You are a concise tech news editor."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
        )
        
        content = response.choices[0].message.content
        return TrendingSummary(markdown_news_digest=content)

    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        return TrendingSummary(markdown_news_digest="Error generating summary digest.")


async def scrape_async() -> List[Dict[str, Any]]:
    """Async entry point for the content aggregator."""
    try:
        trends = await _generate_ai_trends_summary()
    except Exception as exc:
        logger.error("AI trends summary generation failed: %s", exc, exc_info=True)
        return []

    digest = trends.markdown_news_digest.strip()
    timestamp = datetime.now(timezone.utc).replace(tzinfo=None)
    print(digest)
    return [
        {
            "title": "AI Trends Digest",
            "url": "#",
            "published_at": timestamp,
            "meta_data": {
                "source_name": "Tavily AI Trends",
                "summary": digest,
                "generated_by": "direct_pipeline",
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
            "scrape() cannot run inside an active event loop; "
            "await scrape_async() instead."
        ) from exc
