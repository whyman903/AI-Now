"""Analyze a web page's HTML with an LLM to discover CSS selectors for scraping."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
from openai import AsyncOpenAI
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BACKOFF = [1.0, 2.0]  # seconds between retries (exponential)


# ---- Schemas ----

class SelectorSet(BaseModel):
    item_container: str
    title: str
    url: str
    date: Optional[str] = None
    thumbnail: Optional[str] = None
    author: Optional[str] = None


class AnalysisResult(BaseModel):
    selectors: SelectorSet
    preview_items: List[Dict[str, Any]]
    confidence: str
    notes: Optional[str] = None
    warnings: List[str] = []
    needs_javascript: bool = False
    js_indicators: List[str] = []


# ---- Prompt ----

_SYSTEM_PROMPT = """\
You are a web scraping expert. Given HTML from a content listing page (blog, \
news, research), identify CSS selectors that extract the repeating content \
items.

Return ONLY a JSON object (no markdown, no extra text) with these keys:

{
  "item_container": "CSS selector matching each content item wrapper",
  "title": "selector WITHIN the container for the item title",
  "url": "selector WITHIN the container for the link (a tag with href)",
  "date": "selector WITHIN the container for the publication date, or null",
  "thumbnail": "selector WITHIN the container for the thumbnail image, or null",
  "author": "selector WITHIN the container for the author name, or null",
  "confidence": "high | medium | low",
  "needs_javascript": false,
  "js_indicators": [],
  "notes": "brief explanation of what you found"
}

Rules:
- item_container must match 3+ repeating items on the page.
- title and url are REQUIRED. date/thumbnail/author are optional (null if unclear).
- Use standard CSS selector syntax (tag.class, tag[attr], etc.).
- Keep selectors as simple and robust as possible — avoid deeply nested chains.
- If you are unsure, set confidence to "low".

Date selector guidance:
- Prefer <time> tags with datetime attributes — use "time" or "time[datetime]".
- If dates appear as plain text inside a div/span, verify the selector targets the \
element whose text is a DATE (contains digits and month names), not a category label.
- If the same class is used for both category tags and dates, use positional \
selectors like :last-child or :nth-child(N) to distinguish them.
- If you cannot reliably distinguish the date element, set date to null.

JavaScript detection:
- Set "needs_javascript" to true if the HTML shows signs of being a \
single-page application (SPA) or client-rendered site:
  * Empty #root, #__next, #app, or #__nuxt divs with no content items inside
  * <noscript> tags containing fallback messages about enabling JavaScript
  * Very little visible text content despite the page being a content listing
  * Data attributes like data-reactroot, ng-app, v-app with empty containers
- "js_indicators" should list the specific signals found (e.g. "empty #__next div", \
"noscript fallback present", "minimal text content").
- If the HTML has normal server-rendered content, set needs_javascript to false.
"""


def _build_user_prompt(url: str, cleaned_html: str) -> str:
    return f"URL: {url}\n\nHTML:\n{cleaned_html}"


# ---- LLM Call ----

def _strip_code_fences(content: str) -> str:
    """Strip markdown code fences if present."""
    if content.startswith("```"):
        lines = content.split("\n")
        lines = lines[1:]  # remove opening fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines)
    return content


async def _call_llm_with_retry(url: str, cleaned_html: str) -> Dict[str, Any]:
    """Send cleaned HTML to Grok with retry logic for transient failures.

    Retries up to ``_MAX_RETRIES`` times on ``JSONDecodeError`` (malformed LLM
    output) and transient network errors, with exponential backoff.
    """
    client = AsyncOpenAI(
        api_key=settings.XAI_API_KEY,
        base_url="https://api.x.ai/v1",
    )

    last_error: Optional[Exception] = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = await client.chat.completions.create(
                model="grok-4-1-fast",
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": _build_user_prompt(url, cleaned_html)},
                ],
                temperature=0.1,
            )

            content = response.choices[0].message.content.strip()
            content = _strip_code_fences(content)
            return json.loads(content)

        except json.JSONDecodeError as exc:
            last_error = exc
            logger.warning(
                "LLM returned malformed JSON (attempt %d/%d): %s",
                attempt + 1, _MAX_RETRIES, exc,
            )
        except Exception as exc:
            last_error = exc
            logger.warning(
                "LLM call failed (attempt %d/%d): %s",
                attempt + 1, _MAX_RETRIES, exc,
            )

        if attempt < _MAX_RETRIES - 1:
            delay = _RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)]
            await asyncio.sleep(delay)

    raise last_error  # type: ignore[misc]


# ---- Preview Extraction ----

def _first_srcset_url(srcset: Optional[str]) -> Optional[str]:
    """Extract the first URL from a srcset attribute value."""
    if not srcset:
        return None
    first = srcset.split(",")[0].strip()
    return first.split()[0] if first else None


def _extract_preview(
    html: str,
    selectors: SelectorSet,
    max_items: int = 5,
) -> List[Dict[str, Any]]:
    """Apply *selectors* to *html* and return up to *max_items* extracted items."""
    soup = BeautifulSoup(html, "html.parser")
    containers = soup.select(selectors.item_container)
    items: List[Dict[str, Any]] = []

    for container in containers[:max_items]:
        title_el = container.select_one(selectors.title)
        url_el = container.select_one(selectors.url)

        title = title_el.get_text(strip=True) if title_el else None
        url = url_el.get("href") if url_el else None

        if not title and not url:
            continue

        item: Dict[str, Any] = {"title": title, "url": url}

        if selectors.date:
            date_el = container.select_one(selectors.date)
            if date_el:
                item["date"] = (
                    date_el.get("datetime")
                    or date_el.get_text(strip=True)
                )

        if selectors.thumbnail:
            thumb_el = container.select_one(selectors.thumbnail)
            if thumb_el:
                item["thumbnail"] = thumb_el.get("src") or _first_srcset_url(thumb_el.get("srcset"))

        if selectors.author:
            author_el = container.select_one(selectors.author)
            if author_el:
                item["author"] = author_el.get_text(strip=True)

        items.append(item)

    return items


# ---- Public API ----

def _validate_preview(
    preview_items: List[Dict[str, Any]],
    selectors: SelectorSet,
) -> List[str]:
    """Check preview quality and return warnings for suspect selectors."""
    warnings: List[str] = []

    if not preview_items:
        warnings.append("No items matched the container selector.")
        return warnings

    # Check titles
    titles_missing = sum(1 for it in preview_items if not it.get("title"))
    if titles_missing == len(preview_items):
        warnings.append("Title selector matched no text in any item.")

    # Check URLs
    urls_missing = sum(1 for it in preview_items if not it.get("url"))
    if urls_missing == len(preview_items):
        warnings.append("URL selector matched no href in any item.")

    # Check dates — if a date selector was provided, verify at least some
    # extracted values look like actual dates (contain digits).
    if selectors.date:
        date_values = [it.get("date") for it in preview_items if it.get("date")]
        if not date_values:
            warnings.append("Date selector matched nothing; dates will be empty.")
        else:
            _DATE_LIKE = re.compile(r"\d")
            non_date = [v for v in date_values if not _DATE_LIKE.search(v)]
            if len(non_date) == len(date_values):
                warnings.append(
                    f"Date selector returned category-like values "
                    f"({date_values[0]!r}); selector may be wrong."
                )

    return warnings


async def analyze_page(url: str, cleaned_html: str) -> AnalysisResult:
    """Send cleaned HTML to Grok, parse selectors, validate with preview.

    Includes empirical JS detection: if the LLM returns selectors but preview
    extraction finds 0 items on static HTML, ``needs_javascript`` is forced to
    ``True`` (more reliable than the LLM's guess alone).
    """
    raw = await _call_llm_with_retry(url, cleaned_html)

    selectors = SelectorSet(
        item_container=raw["item_container"],
        title=raw["title"],
        url=raw["url"],
        date=raw.get("date"),
        thumbnail=raw.get("thumbnail"),
        author=raw.get("author"),
    )

    preview_items = _extract_preview(cleaned_html, selectors)
    warnings = _validate_preview(preview_items, selectors)

    confidence = raw.get("confidence", "low")
    if warnings:
        if confidence == "high":
            confidence = "medium"

    needs_javascript = bool(raw.get("needs_javascript", False))
    js_indicators = list(raw.get("js_indicators") or [])

    # Empirical JS detection: LLM found selectors but static HTML yields 0 items
    if not preview_items and not needs_javascript:
        needs_javascript = True
        if "empirical: 0 items extracted from static HTML" not in js_indicators:
            js_indicators.append("empirical: 0 items extracted from static HTML")
        logger.info(
            "Forced needs_javascript=True for %s (selectors returned but 0 preview items)",
            url,
        )

    return AnalysisResult(
        selectors=selectors,
        preview_items=preview_items,
        confidence=confidence,
        notes=raw.get("notes"),
        warnings=warnings,
        needs_javascript=needs_javascript,
        js_indicators=js_indicators,
    )
