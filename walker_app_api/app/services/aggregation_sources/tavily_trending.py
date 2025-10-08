"""AI trends summary agent powered by Tavily search and xAI's Grok."""

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
        f"""Today is {today}. Find the MOST GROUNDBREAKING AI news from the past 3-5 days and return a numbered list.

            IMPORTANT: When using the Tavily search tool, use SHORT search queries under 400 characters. 
            Examples: "major AI model releases October 2025", "OpenAI GPT Claude Gemini announcements", "AI breakthrough research this week"
            
            Start directly with "1." - do NOT include any title, heading, introduction, or preamble.

            WHAT COUNTS AS GROUNDBREAKING:
            - Major AI model launches from top labs (GPT-5, Claude 4, Gemini 2, Grok 3, Llama 4) - NOT beta tests
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
    )
    print(result.output)
    return result.output


def scrape() -> List[Dict[str, Any]]:
    """Entry point for the content aggregator."""

    try:
        trends = asyncio.run(_generate_ai_trends_summary())
    except Exception as exc:
        logger.error("AI trends summary generation failed: %s", exc, exc_info=True)
        return []

    timestamp = datetime.now(timezone.utc).replace(tzinfo=None)
    date_str = timestamp.strftime("%B %d, %Y")

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


