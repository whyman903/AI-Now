# Aggregation Refactor Plan

## Problem Statement

The current system has 16 individual scraper files with duplicated patterns, inconsistent error handling, and 8+ different date-parsing implementations. Adding a new source requires touching 4 files (new scraper, source registry, content aggregator imports, content aggregator initialization). Users cannot add their own sources.

## Architecture: Hybrid Two-Tier System

System sources (Anthropic, OpenAI, etc.) stay as Python files with a plugin pattern for auto-discovery. User-created sources use LLM-generated CSS selectors stored in the database, executed by a lightweight generic engine. This split exists because system scrapers have complex, source-specific logic (hover-aside thumbnails, PDF binary decompression, GitHub API traversal) that CSS selectors cannot express, while user sources target simple blog/news pages where selector-based scraping works well.

```
CURRENT:
  anthropic_agg.py  ─┐
  openai_agg.py     ─┤
  xai_agg.py        ─┤──> content_aggregator.py ──> DB
  perplexity_agg.py ─┤
  ...16 more files  ─┘

PROPOSED:
  System sources (Python plugins)
    ├─ plugins/anthropic.py     ─┐
    ├─ plugins/openai.py        ─┤
    ├─ plugins/huggingface.py   ─┤
    ├─ ...                      ─┤──> aggregator.py ──> _persist_items() ──> DB
    └─ (auto-discovered)        ─┤
                                 ─┤
  User sources (DB selectors)    ─┤
    └─ user_source_engine.py ────┘
         reads selectors from aggregation_sources table
         (LLM generates selectors once at setup time)
```

---

## 1. System Sources: Plugin Pattern

### 1a. Plugin Interface

Each system source is a single Python file in `app/services/aggregation/plugins/`. A `@register` decorator handles auto-discovery.

```python
# app/services/aggregation/plugins/anthropic.py

from app.services.aggregation.registry import register

@register(
    key="scrape_anthropic",
    name="Anthropic",
    category="frontier_model",
    content_types=["article", "research_lab"],
    requires_selenium=True,
)
async def scrape() -> list[dict]:
    # Existing scrape logic, unchanged
    ...
```

The decorator adds the function and its metadata to a global registry. At import time, the `plugins/` package's `__init__.py` auto-imports all modules in the directory:

```python
# app/services/aggregation/plugins/__init__.py

import importlib
import pkgutil

for _, module_name, _ in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{module_name}")
```

### 1b. Registry

```python
# app/services/aggregation/registry.py

from dataclasses import dataclass
from typing import Callable, List, Dict

@dataclass(frozen=True)
class PluginSource:
    key: str
    name: str
    category: str
    content_types: list[str]
    scrape_func: Callable
    requires_selenium: bool = False

_REGISTRY: Dict[str, PluginSource] = {}

def register(*, key: str, name: str, category: str, content_types: list[str],
             requires_selenium: bool = False):
    def decorator(func):
        _REGISTRY[key] = PluginSource(
            key=key, name=name, category=category,
            content_types=content_types, scrape_func=func,
            requires_selenium=requires_selenium,
        )
        return func
    return decorator

def get_all_plugins() -> list[PluginSource]:
    return list(_REGISTRY.values())

def get_plugin(key: str) -> PluginSource:
    return _REGISTRY[key]
```

### 1c. Adding a New System Source

Drop a file in `plugins/`:

```python
# app/services/aggregation/plugins/new_lab.py

from app.services.aggregation.registry import register

@register(
    key="scrape_new_lab",
    name="New Lab",
    category="frontier_model",
    content_types=["article"],
)
async def scrape() -> list[dict]:
    ...
```

No other files need to change. The plugin auto-discovers at import.

### 1d. Shared Utilities

Consolidate duplicated logic from `_lab_scraper_utils.py` and individual scrapers into focused modules:

```
app/services/aggregation/
    utils/
        date_parser.py      # Single pipeline: ISO 8601 → datetime attr → relative → month-name → dateutil fuzzy
        thumbnail.py         # Strategy-based extraction (inline, background_image, hover_aside, parent_walk, meta_tags)
        webdriver.py         # Chrome driver creation + autoscroll (moved from _webdriver.py + _lab_scraper_utils.py)
        html.py              # normalize_whitespace, URL absolutization, common extraction helpers
```

**`date_parser.py`** replaces 8+ inconsistent implementations:

```python
def parse_date(value: str | datetime | None) -> tuple[datetime | None, str | None, str | None]:
    """Returns (datetime_obj, date_iso, date_display).
    Tries strategies in order: ISO 8601, datetime attribute, relative ("2 days ago"),
    month-name patterns ("Sep 15, 2025"), dateutil fuzzy fallback."""
```

**`thumbnail.py`** consolidates 6 thumbnail extraction patterns into strategy functions:

| Strategy | Description | Used by |
|----------|-------------|---------|
| `inline` | `img` src/srcset within the item element | Most sources |
| `background_image` | Parse `background-image` CSS from parent divs | xAI |
| `hover_aside` | Hover item, capture async aside img update | Anthropic |
| `parent_walk` | Walk up parent/sibling tree to find img | OpenAI |
| `meta_tags` | Fetch item URL, extract og:image | Qwen, Thinking Machines |

### 1e. Migration Path for Existing Scrapers

Each existing `*_agg.py` file becomes a plugin file with minimal changes:
1. Add the `@register` decorator
2. Replace duplicated utility calls with shared utility imports
3. Keep all source-specific logic intact (selectors, scrolling behavior, custom extraction)
4. Delete `source_registry.py` entries and `content_aggregator.py` import/init code

The 3 sources with highly specialized logic stay as custom plugins with full Python control:
- **huggingface.py** — PDF binary stream decompression + GitHub URL regex extraction
- **tavily.py** — Tavily API search + LLM summarization pipeline
- **deepseek.py** — GitHub API repo listing + Atom feed commit date mining

---

## 2. User-Created Sources: LLM-Assisted Setup

### 2a. How It Works

Users provide a URL. The system:

1. **Fetches the page** — httpx (or Selenium if JS-rendered) retrieves the full HTML
2. **Cleans the HTML** — strips scripts, styles, nav, footer, ads; keeps structural tags and classes; truncates to fit LLM context
3. **Sends to LLM** — a structured prompt asks the LLM to identify the repeating article/post pattern and return CSS selectors
4. **LLM returns selectors** — JSON with selectors for item container, title, URL, date, thumbnail, author
5. **Test scrape** — the system runs the selectors against the live page, returns a preview to the user
6. **User confirms** — selectors are saved to the `aggregation_sources` table
7. **Daily runs** — the generic engine uses stored selectors mechanically, zero LLM cost

### 2b. LLM Prompt Design

The LLM receives cleaned HTML and returns structured JSON:

```
You are analyzing a webpage to extract a repeating list of articles/posts.

Given the HTML below, identify:
1. The CSS selector for each repeating content item (article/post container)
2. Within each item, the CSS selector for: title, URL (href), date, thumbnail image, author
3. Whether URLs are relative (need a base prefix) or absolute
4. The date format pattern (e.g., "MMM DD, YYYY", ISO 8601, relative)

Return ONLY valid JSON:
{
  "item": "CSS selector for the repeating container",
  "title": "CSS selector for title text within item",
  "url": "CSS selector for the link element (must have href)",
  "date": "CSS selector for date element (or null)",
  "thumbnail": "CSS selector for image element (or null)",
  "author": "CSS selector for author element (or null)",
  "url_prefix": "base URL for relative links (or null)",
  "date_format": "description of date format found",
  "notes": "any edge cases or warnings"
}

HTML:
{cleaned_html}
```

### 2c. HTML Cleaning Strategy

Before sending to the LLM, clean the HTML to reduce token usage:

1. Remove `<script>`, `<style>`, `<noscript>`, `<svg>`, `<iframe>` tags entirely
2. Remove `<header>`, `<nav>`, `<footer>` elements (site chrome, not content)
3. Remove all inline event handlers and data attributes
4. Remove empty elements and comments
5. Collapse whitespace
6. Keep class names and IDs (the LLM needs these for selectors)
7. Truncate to ~4000 tokens if still too large (keep the first content-rich section)

### 2d. Generic User Source Engine

A single engine handles all user-created sources using stored selectors:

```python
# app/services/aggregation/user_source_engine.py

class UserSourceEngine:
    def __init__(self, source: AggregationSource):
        self.source = source
        self.selectors = source.selectors  # LLM-generated CSS selectors

    async def scrape(self) -> list[dict]:
        html = await self._fetch(self.source.url)
        soup = BeautifulSoup(html, "html.parser")
        items = []
        for element in soup.select(self.selectors["item"]):
            title = self._extract_text(element, self.selectors.get("title"))
            url = self._extract_href(element, self.selectors.get("url"))
            if not title or not url:
                continue
            items.append({
                "title": title,
                "url": self._absolutize(url),
                "published_at": self._extract_date(element),
                "thumbnail_url": self._extract_thumbnail(element),
                "author": self._extract_text(element, self.selectors.get("author")),
                "type": "article",
                "source_key": self.source.key,
            })
        return items
```

This engine is intentionally simple. It handles the 80% case of blog/news pages with a repeating list of articles. If a site has unusual structure, the LLM-generated selectors either handle it or the user adjusts.

### 2e. Selector Refresh

Sites change their HTML over time. When stored selectors stop returning results:

1. The system detects zero items scraped for a user source
2. It flags the source as `needs_refresh` and notifies the user
3. The user can trigger a re-analysis (re-run LLM on current HTML)
4. Or manually edit selectors if the change is minor

---

## 3. Database Table: `aggregation_sources`

This table stores metadata for ALL sources (system + user) and selectors/config for user-created sources only. System sources use this table for state tracking (last run, errors, enabled/disabled) but their scrape logic lives in Python.

```sql
CREATE TABLE aggregation_sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key             VARCHAR(100) NOT NULL UNIQUE,
    name            VARCHAR(255) NOT NULL,
    source_type     VARCHAR(20)  NOT NULL,  -- 'system' or 'user'
    category        VARCHAR(50)  NOT NULL,  -- frontier_model, venture, learning, applied_ai, options
    content_types   JSON         NOT NULL,  -- ["article", "research_lab"]

    -- User source fields (NULL for system sources)
    url             TEXT,                    -- the page to scrape
    selectors       JSON,                   -- LLM-generated CSS selectors (see schema below)
    url_prefix      VARCHAR(500),           -- base URL for resolving relative links
    requires_js     BOOLEAN      NOT NULL DEFAULT false,  -- needs Selenium vs httpx
    llm_analysis    JSON,                   -- raw LLM response from setup (for debugging/re-analysis)

    -- Ownership
    created_by      UUID         REFERENCES users(id) ON DELETE CASCADE,  -- NULL = system
    enabled         BOOLEAN      NOT NULL DEFAULT true,
    default_enabled BOOLEAN      NOT NULL DEFAULT true,

    -- Execution state
    last_run_at     TIMESTAMPTZ,
    last_error      TEXT,
    last_item_count INTEGER,     -- items found on last run
    run_count       INTEGER      NOT NULL DEFAULT 0,
    needs_refresh   BOOLEAN      NOT NULL DEFAULT false,

    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX ix_agg_sources_type     ON aggregation_sources(source_type);
CREATE INDEX ix_agg_sources_enabled  ON aggregation_sources(enabled);
CREATE INDEX ix_agg_sources_user     ON aggregation_sources(created_by);
```

### Selector Schema (user sources only)

```json
{
  "item":       "div.post-card",
  "title":      "h2.post-title",
  "url":        "a.post-link",
  "date":       "time.post-date",
  "thumbnail":  "img.post-thumbnail",
  "author":     "span.post-author"
}
```

### System Source Rows

System sources get rows with `source_type = 'system'`, `selectors = NULL`, `url = NULL`. These rows are seeded by migration and exist purely for state tracking and the unified source list API.

```json
{
  "key": "scrape_anthropic",
  "name": "Anthropic",
  "source_type": "system",
  "category": "frontier_model",
  "content_types": ["article", "research_lab"],
  "url": null,
  "selectors": null,
  "created_by": null,
  "enabled": true
}
```

### User Source Rows

```json
{
  "key": "user_techcrunch_ai_84f2",
  "name": "TechCrunch AI",
  "source_type": "user",
  "category": "options",
  "content_types": ["article"],
  "url": "https://techcrunch.com/category/artificial-intelligence/",
  "selectors": {
    "item": "div.post-block",
    "title": "a.post-block__title__link",
    "url": "a.post-block__title__link",
    "date": "time.river-byline__time",
    "thumbnail": "img.post-block__media",
    "author": "span.river-byline__authors"
  },
  "url_prefix": null,
  "requires_js": false,
  "created_by": "a1b2c3d4-...",
  "enabled": true
}
```

---

## 4. API Endpoints

### Source Setup (User-Created)

```
POST /api/v1/sources/analyze
  Body: { "url": "https://example.com/blog" }
  Auth: Required (user)
  Flow: Fetch page → clean HTML → LLM → return selectors + preview items
  Response: {
    "selectors": { ... },
    "preview_items": [ { "title": "...", "url": "...", ... }, ... ],
    "suggested_name": "Example Blog",
    "requires_js": false
  }

POST /api/v1/sources
  Body: {
    "url": "https://example.com/blog",
    "name": "Example Blog",
    "selectors": { ... },  // from /analyze response (user can edit)
    "category": "options"
  }
  Auth: Required (user)
  Response: { "key": "user_example_blog_a3f1", ... }

POST /api/v1/sources/{key}/refresh
  Auth: Required (owner)
  Flow: Re-fetch page → re-run LLM → return new selectors + preview
  Response: Same as /analyze
```

### Source Management

```
GET    /api/v1/sources                  # List all sources (system + user's own)
GET    /api/v1/sources/{key}            # Get source details
PATCH  /api/v1/sources/{key}            # Update source (owner only, user sources only)
DELETE /api/v1/sources/{key}            # Delete source (owner only, user sources only)
POST   /api/v1/sources/{key}/test       # Dry-run scrape, return preview items without persisting
```

### Existing Endpoint Changes

- `GET /api/v1/items/filters/labs` — query `aggregation_sources` table instead of hardcoded `source_registry.py`
- `POST /api/v1/aggregation/trigger` — aggregator reads system plugins from registry + user sources from DB
- `POST /api/v1/aggregation/ingest` — unchanged
- `GET /api/v1/aggregation/status` — pull per-source stats from `aggregation_sources` table

---

## 5. Refactored Aggregator

`aggregator.py` replaces `content_aggregator.py`. It orchestrates both tiers:

```python
class ContentAggregator:
    async def aggregate_all_content(self, low_memory: bool = False):
        # Tier 1: System sources from plugin registry
        plugins = get_all_plugins()
        selenium_plugins = [p for p in plugins if p.requires_selenium]
        api_plugins = [p for p in plugins if not p.requires_selenium]

        if self._selenium_enabled:
            await self._run_plugins(selenium_plugins, low_memory)
        await self._run_plugins(api_plugins, low_memory)

        # Tier 2: User sources from database
        db = SessionLocal()
        user_sources = db.query(AggregationSource).filter(
            AggregationSource.source_type == "user",
            AggregationSource.enabled == True,
        ).all()
        await self._run_user_sources(user_sources, low_memory)

    async def _run_plugins(self, plugins, low_memory):
        batch_size = 1 if low_memory else 3
        for batch in chunked(plugins, batch_size):
            tasks = [self._run_plugin(p) for p in batch]
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_plugin(self, plugin: PluginSource):
        result = await plugin.scrape_func()
        stats = await self._persist_items(result)
        self._update_source_state(plugin.key, stats)

    async def _run_user_sources(self, sources, low_memory):
        batch_size = 1 if low_memory else 3
        for batch in chunked(sources, batch_size):
            tasks = [self._run_user_source(s) for s in batch]
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_user_source(self, source: AggregationSource):
        engine = UserSourceEngine(source)
        result = await engine.scrape()
        stats = await self._persist_items(result)
        self._update_source_state(source.key, stats, source=source)
```

The `_persist_items()` method stays largely unchanged — it already handles URL canonicalization, deduplication, and upsert.

---

## 6. New Directory Structure

```
app/services/aggregation/
    __init__.py
    registry.py              # @register decorator, PluginSource dataclass, get_all_plugins()
    aggregator.py            # Refactored ContentAggregator (replaces content_aggregator.py)
    user_source_engine.py    # Generic selector-based scraper for user sources
    html_cleaner.py          # Clean HTML for LLM analysis
    llm_analyzer.py          # Send cleaned HTML to LLM, parse selector response
    plugins/
        __init__.py          # Auto-imports all plugin modules
        anthropic.py
        openai.py
        xai.py
        deepmind.py
        deepseek.py
        qwen.py
        moonshot.py
        perplexity.py
        thinking_machines.py
        huggingface.py
        tavily.py
        nvidia_podcast.py
        dwarkesh_podcast.py
        rss_sequoia.py
        youtube_channels.py  # All 8 YouTube channels in one plugin
    utils/
        __init__.py
        date_parser.py       # Unified date parsing pipeline
        thumbnail.py         # Strategy-based thumbnail extraction
        webdriver.py         # Chrome driver creation + autoscroll
        html.py              # normalize_whitespace, URL absolutization

alembic/versions/xxxx_add_aggregation_sources.py
```

---

## 7. Migration Strategy

### Phase 1: Infrastructure

1. Create `aggregation_sources` table via Alembic migration
2. Build `registry.py` with `@register` decorator
3. Build shared utilities (`date_parser.py`, `thumbnail.py`, `webdriver.py`, `html.py`)
4. Build `plugins/__init__.py` auto-import mechanism

### Phase 2: System Source Migration

1. Convert each existing `*_agg.py` to a plugin file with `@register`
2. Replace duplicated utility code with shared utility imports
3. Keep all source-specific scraping logic intact
4. Seed `aggregation_sources` table with system source rows (for state tracking)
5. Build new `aggregator.py` that reads plugins from registry
6. Wire into existing API endpoints
7. Run both old and new aggregators in parallel to validate output parity
8. Cut over to new aggregator

### Phase 3: User Source Infrastructure

1. Build `html_cleaner.py`
2. Build `llm_analyzer.py`
3. Build `user_source_engine.py`
4. Add `/sources/analyze` endpoint (LLM setup flow)
5. Add CRUD endpoints for user sources
6. Integrate user sources into aggregator's daily run
7. Add `needs_refresh` detection (zero items scraped)

### Phase 4: Cleanup

1. Delete individual scraper files (`app/services/aggregation_sources/` directory)
2. Delete `source_registry.py`
3. Delete old `content_aggregator.py`
4. Update imports across codebase

---

## 8. Files Created

```
app/services/aggregation/__init__.py
app/services/aggregation/registry.py
app/services/aggregation/aggregator.py
app/services/aggregation/user_source_engine.py
app/services/aggregation/html_cleaner.py
app/services/aggregation/llm_analyzer.py
app/services/aggregation/plugins/__init__.py
app/services/aggregation/plugins/anthropic.py
app/services/aggregation/plugins/openai.py
app/services/aggregation/plugins/xai.py
app/services/aggregation/plugins/deepmind.py
app/services/aggregation/plugins/deepseek.py
app/services/aggregation/plugins/qwen.py
app/services/aggregation/plugins/moonshot.py
app/services/aggregation/plugins/perplexity.py
app/services/aggregation/plugins/thinking_machines.py
app/services/aggregation/plugins/huggingface.py
app/services/aggregation/plugins/tavily.py
app/services/aggregation/plugins/nvidia_podcast.py
app/services/aggregation/plugins/dwarkesh_podcast.py
app/services/aggregation/plugins/rss_sequoia.py
app/services/aggregation/plugins/youtube_channels.py
app/services/aggregation/utils/__init__.py
app/services/aggregation/utils/date_parser.py
app/services/aggregation/utils/thumbnail.py
app/services/aggregation/utils/webdriver.py
app/services/aggregation/utils/html.py
app/api/v1/endpoints/sources.py
alembic/versions/xxxx_add_aggregation_sources.py
```

## 9. Files Deleted (Phase 4)

```
app/services/aggregation_sources/          # Entire directory (16 scraper files + utils)
app/services/source_registry.py
app/services/content_aggregator.py
```

## 10. Files Modified

```
app/db/models.py                           # Add AggregationSource model
app/api/v1/endpoints/aggregation.py        # Wire new aggregator
app/api/v1/endpoints/items.py              # Query DB instead of source_registry
app/api/v1/router.py                       # Add sources router
scripts/run_selenium_scrapers.py           # Read plugins from registry instead of hardcoded imports
```

---

## 11. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Site HTML changes break user source selectors | High | `needs_refresh` detection + user notification + one-click LLM re-analysis |
| LLM generates incorrect selectors | Medium | Test scrape preview before saving; user can manually edit selectors |
| Plugin migration introduces regressions | Medium | Shadow mode: run old and new aggregators in parallel, compare output |
| User sources scrape inappropriate content | Medium | Rate limiting per user + content type restrictions |
| LLM API costs during source setup | Low | LLM runs once per source setup, not per daily run; costs are negligible |
| System source plugins fail to auto-discover | Low | Unit test that all expected plugins are registered at import time |

## 12. Key Benefits

1. **Add a system source**: Drop a Python file in `plugins/`. No other changes needed.
2. **Add a user source**: Provide a URL. LLM does the rest. No code, no deploys.
3. **Zero per-run LLM cost**: LLM runs once at setup. Daily scraping is mechanical.
4. **Full Python control**: System sources keep all custom logic (hover thumbnails, PDF mining, API traversal). No loss of capability.
5. **Consistent behavior**: One date parser, one thumbnail extractor, one normalization pipeline shared across all system sources.
6. **Observability**: `last_run_at`, `last_error`, `last_item_count`, `run_count` tracked per source in the DB.
7. **User empowerment**: Users can add any blog/news page as a content source with a preview-before-save flow.
