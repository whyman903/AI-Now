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


async def _get_tavily_search_results() -> str:
    """
    Fetches raw search results directly using Tavily's 'news' topic.
    This is faster and more focused than a general agentic search.
    """
    tavily_client = AsyncTavilyClient(api_key=settings.TAVILY_API_KEY)
    
    # We use a broad, high-level query because 'topic="news"' handles the recency logic for us.
    query = "groundbreaking artificial intelligence news model releases and major announcements"
    
    try:
        response = await tavily_client.search(
            query=query,
            topic="news",      # Optimized for news retrieval
            days=5,            # Look back 5 days
            max_results=10,     # Get enough to filter down to top 5
            
        )
        
        # Format results into a clean text block for the LLM
        results = response.get("results", [])
        if not results:
            return "No recent news found."
            
        formatted_results = []
        for r in results:
            # We explicitly grab title, content, url, and published_date if available
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
    """
    Pipeline: 
    1. Search Tavily (News)
    2. Summarize with LLM (Grok)
    """
    
    # 1. Get Context
    search_context = await _get_tavily_search_results()
    
    if not search_context or search_context == "No recent news found.":
        return TrendingSummary(markdown_news_digest="No significant AI news found in the last 5 days.")

    # 2. Call LLM (Grok via OpenAI-compatible client)
    # Note: Using AsyncOpenAI is standard for Grok/xAI now
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
    - Select the top 5 most groundbreaking stories.
    - **CRITICAL: Do NOT include duplicate stories about the same event.** If multiple sources cover the same announcement (e.g., Claude Opus 4.5 release), pick ONE story and cite only ONE source.
    - Start directly with "1." (numbered list).
    - **Be CONCISE and PUNCHY: Aim for 1-2 sentences per item**
    - Write in PAST TENSE with active voice.
    - **Use FORMAL, DIRECT language. Avoid casual phrases like "tie-up", "alongside", or informal business jargon.**
    - **ONLY STATE FACTS: NO editorial commentary, analysis, or implications.**
    - **Bold key terms and names** inline (do not use separate headlines).
    - End each item with a markdown citation: [Source Name](URL) YYYY/MM/DD.
    - **IMPORTANT: For the citation, use ONLY the source name (e.g., "Bloomberg", "Reuters", "TechCrunch"), NOT the article title. Extract the source name from the URL domain.**
    - Exclude: Rumors, opinions, "top 10" lists, or minor funding rounds.
    - Strict Format: Markdown only.
    
    Example format:
    1. Anthropic unveiled **Claude Opus 4.5**, enhancing coding, agentic abilities, and enterprise workflows. [Bloomberg](https://bloomberg.com/...) 1/15/2025.
    """

    try:
        response = await client.chat.completions.create(
            model="grok-4-1-fast", 
            messages=[
                {"role": "system", "content": "You are a concise tech news editor."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2, # Keep it factual
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