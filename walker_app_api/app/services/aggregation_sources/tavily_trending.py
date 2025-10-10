import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.grok import GrokProvider
from pydantic_ai.common_tools.tavily import tavily_search_tool

from app.core.config import settings

logger = logging.getLogger(__name__)


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
    
    today = datetime.now().strftime("%B %d, %Y")

    agent = Agent(
        OpenAIChatModel("grok-4-fast", provider=GrokProvider(api_key=settings.XAI_API_KEY)),
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
            """)
        ,
        tools=[tavily_search_tool(api_key=settings.TAVILY_API_KEY)],
    )

    result = await agent.run(
        f"""Today is {today}. 
        Find the most important AI news today

        IMPORTANT: When using the Tavily search tool, use SHORT search queries.  
        Examples:"AI breakthrough research this week"
        
        WHAT COUNTS AS IMPORTANT:
        - Major AI model launches from top labs (OpenAI, Anthropic, Google, XAI, etc.) - NOT beta tests
        - Game-changing product launches (ChatGPT Sora, Google Astra, AI agents)
        - Breakthrough research papers that shift the field
        - Major acquisitions or IPOs in AI space
        
        CRITICAL SOURCE REQUIREMENTS:
        - You MUST use authoritative, tier-1 sources — prioritize the company’s own official releases, or trusted outlets like TechCrunch, The Verge, Bloomberg, Reuters, Wired, MIT Technology Review, Financial Times, Axios, or WSJ; if a story appears only on low-quality or SEO-driven sites (e.g., ts2.tech, TestingCatalog), skip it and find a reputable alternative.

        FORMAT:
        - ONE punchy sentence per item
        - Bold **key terms** inline
        - End with: [Source Name](URL)
        
        Example: "**OpenAI** launched **ChatGPT Sora**, a new collaborative interface enabling direct document editing within conversations. The feature supports **real-time collaboration** on code and documents, with users able to highlight sections and request targeted revisions without rewriting entire prompts. [The Verge](https://example.com)"   
        Provide 5 TRULY GROUNDBREAKING items. Quality over quantity - if you can't find 5 with tier-1 sources, provide fewer.
        """
    )
    return result.output


def scrape() -> List[Dict[str, Any]]:
    """Entry point for the content aggregator."""
    try:
        trends = asyncio.run(_generate_ai_trends_summary())
    except Exception as exc:
        logger.error("AI trends summary generation failed: %s", exc, exc_info=True)
        return []

    timestamp = datetime.now(timezone.utc).replace(tzinfo=None)
    return [
        {
            "title": f"AI Trends",
            "url": "#",
            "published_at": timestamp,
            "meta_data": {
                "source_name": "Tavily AI Trends",
                "summary": trends.markdown_news_digest,
                "generated_by": "pydantic_ai",
                "model": "grok-4-fast",
                "search_engine": "tavily",
            },
        }
    ]


