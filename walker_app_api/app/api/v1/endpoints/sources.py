"""User-source CRUD, LLM-assisted CSS selector analysis, and visibility management."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.base import get_db
from app.db.models import AggregationSource, User
from app.services.aggregation.html_cleaner import clean_html
from app.services.aggregation.llm_analyzer import AnalysisResult, SelectorSet, analyze_page
from app.services.aggregation.registry import get_all_plugins
from app.services.aggregation.rss_discovery import discover_feed_url, validate_feed
from app.services.aggregation.user_source_engine import scrape_user_source

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic request / response schemas
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    url: HttpUrl
    name: Optional[str] = None


class AnalyzeResponse(BaseModel):
    url: str
    extraction_method: str
    selectors: Optional[SelectorSet] = None
    feed_url: Optional[str] = None
    feed_title: Optional[str] = None
    feed_item_count: Optional[int] = None
    preview_items: List[Dict[str, Any]] = []
    confidence: str
    needs_javascript: bool = False
    js_indicators: List[str] = []
    notes: Optional[str] = None
    warnings: List[str] = []
    existing_source: Optional[Dict[str, Any]] = None


class CreateSourceRequest(BaseModel):
    url: HttpUrl
    name: str
    category: str = "custom"
    content_types: List[str] = ["article"]
    extraction_method: str = "css_selectors"
    selectors: Optional[SelectorSet] = None
    feed_url: Optional[str] = None
    url_prefix: Optional[str] = None


class UpdateSourceRequest(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    category: Optional[str] = None
    selectors: Optional[SelectorSet] = None
    extraction_method: Optional[str] = None
    feed_url: Optional[str] = None


class VisibilityRequest(BaseModel):
    enabled: bool


class BulkVisibilityRequest(BaseModel):
    sources: Dict[str, bool]


class SourceResponse(BaseModel):
    key: str
    name: str
    source_type: str
    category: str
    content_types: List[str]
    url: Optional[str] = None
    enabled: bool
    last_run_at: Optional[str] = None
    last_item_count: Optional[int] = None
    created_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:40]


def _user_source_key(user_id: str, name: str) -> str:
    short_id = str(user_id).replace("-", "")[:8]
    return f"user_{short_id}_{_slugify(name)}"


def _fetch_raw_html(url: str) -> str:
    """Fetch a page and return its raw HTML."""
    import httpx

    with httpx.Client(
        timeout=20.0,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; WalkerApp/1.0; +https://walkerapp.com)"
        },
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text


def _serialize_source(source: AggregationSource) -> Dict[str, Any]:
    content_types = source.content_types or []
    if not isinstance(content_types, list):
        content_types = [content_types]
    return {
        "key": source.key,
        "name": source.name,
        "sourceType": source.source_type,
        "category": source.category,
        "contentTypes": content_types,
        "url": source.url,
        "enabled": source.enabled,
        "extractionMethod": getattr(source, "extraction_method", "css_selectors"),
        "feedUrl": getattr(source, "feed_url", None),
        "requiresJs": source.requires_js,
        "lastRunAt": source.last_run_at.isoformat() + "Z" if source.last_run_at else None,
        "lastItemCount": source.last_item_count,
        "createdAt": source.created_at.isoformat() + "Z" if source.created_at else None,
    }


def _get_user_source(
    key: str, user: User, db: Session
) -> AggregationSource:
    source = db.query(AggregationSource).filter(AggregationSource.key == key).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found.")
    if source.source_type != "user":
        raise HTTPException(status_code=403, detail="Cannot modify a system source.")
    if str(source.created_by) != str(user.id):
        raise HTTPException(status_code=403, detail="Not the owner of this source.")
    return source


def _is_selenium_available() -> bool:
    """Check if Selenium/Chrome is available in the current environment."""
    if getattr(settings, "DISABLE_SELENIUM_AGENTS", False):
        return False

    chrome_candidates = [
        getattr(settings, "CHROME_BINARY_PATH", None),
        os.environ.get("GOOGLE_CHROME_BIN"),
        os.environ.get("CHROME_BINARY"),
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for candidate in chrome_candidates:
        if candidate and os.path.exists(candidate):
            return True

    for binary in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        if shutil.which(binary):
            return True

    return False


def _fetch_html_with_selenium(url: str) -> str:
    """Render *url* with headless Chrome and return the rendered HTML."""
    from app.services.aggregation.utils.webdriver import create_chrome_driver, autoscroll_page

    driver = None
    try:
        driver = create_chrome_driver()
        driver.get(url)
        autoscroll_page(driver, max_attempts=10)
        return driver.page_source
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def _build_rss_preview(feed_url: str, max_items: int = 5) -> List[Dict[str, Any]]:
    """Parse *feed_url* and return a short preview of feed entries."""
    try:
        import feedparser
    except ImportError:
        return []

    import httpx

    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(feed_url)
            resp.raise_for_status()
    except Exception:
        return []

    feed = feedparser.parse(resp.text)
    items: List[Dict[str, Any]] = []
    for entry in feed.entries[:max_items]:
        item: Dict[str, Any] = {
            "title": entry.get("title"),
            "url": entry.get("link"),
        }
        for date_field in ("published", "updated"):
            if entry.get(date_field):
                item["date"] = entry[date_field]
                break
        if entry.get("author"):
            item["author"] = entry["author"]
        items.append(item)
    return items


def _find_existing_source(url: str, user_id, db: Session) -> Optional[AggregationSource]:
    """Check if this user already has a source registered for *url*."""
    return (
        db.query(AggregationSource)
        .filter(
            AggregationSource.url == url,
            AggregationSource.created_by == user_id,
            AggregationSource.source_type == "user",
        )
        .first()
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/analyze", status_code=200)
async def analyze_url(
    body: AnalyzeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fetch a URL, run the full detection flow (dedup, RSS, LLM, Selenium fallback)."""
    url = str(body.url)

    # ---- Step 1: Dedup check ----
    existing = _find_existing_source(url, user.id, db)
    if existing:
        return AnalyzeResponse(
            url=url,
            extraction_method=getattr(existing, "extraction_method", "css_selectors"),
            selectors=SelectorSet(**existing.selectors) if existing.selectors else None,
            feed_url=getattr(existing, "feed_url", None),
            preview_items=[],
            confidence="high",
            notes="This URL is already registered as a source.",
            existing_source=_serialize_source(existing),
        ).model_dump(by_alias=True)

    # ---- Step 2: Fetch raw HTML ----
    try:
        raw_html = await asyncio.to_thread(_fetch_raw_html, url)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to fetch URL: {exc}",
        )

    # ---- Step 3: RSS discovery ----
    try:
        feed_url = await asyncio.to_thread(discover_feed_url, raw_html, url)
    except Exception:
        feed_url = None

    if feed_url:
        is_valid, item_count, feed_title = await asyncio.to_thread(validate_feed, feed_url)
        if is_valid and item_count > 0:
            preview_items = await asyncio.to_thread(_build_rss_preview, feed_url)
            return AnalyzeResponse(
                url=url,
                extraction_method="rss",
                feed_url=feed_url,
                feed_title=feed_title,
                feed_item_count=item_count,
                preview_items=preview_items,
                confidence="high",
                notes=f"Found RSS/Atom feed with {item_count} items.",
            ).model_dump(by_alias=True)

    # ---- Step 4: LLM CSS analysis ----
    cleaned = clean_html(raw_html)
    if not cleaned or len(cleaned) < 100:
        raise HTTPException(
            status_code=422,
            detail="Page content too short after cleaning; cannot analyze.",
        )

    try:
        result: AnalysisResult = await analyze_page(url, cleaned)
    except Exception as exc:
        logger.exception("LLM analysis failed for %s", url)
        raise HTTPException(
            status_code=502,
            detail=f"LLM analysis failed: {exc}",
        )

    # If static extraction succeeded, return CSS selectors method
    if result.preview_items and not result.needs_javascript:
        return AnalyzeResponse(
            url=url,
            extraction_method="css_selectors",
            selectors=result.selectors,
            preview_items=result.preview_items,
            confidence=result.confidence,
            needs_javascript=False,
            js_indicators=result.js_indicators,
            notes=result.notes,
            warnings=result.warnings,
        ).model_dump(by_alias=True)

    # ---- Step 5: Selenium fallback ----
    if result.needs_javascript or not result.preview_items:
        if _is_selenium_available():
            try:
                rendered_html = await asyncio.to_thread(_fetch_html_with_selenium, url)
                from app.services.aggregation.llm_analyzer import _extract_preview
                selenium_preview = _extract_preview(rendered_html, result.selectors)
                if selenium_preview:
                    return AnalyzeResponse(
                        url=url,
                        extraction_method="selenium",
                        selectors=result.selectors,
                        preview_items=selenium_preview,
                        confidence=result.confidence,
                        needs_javascript=True,
                        js_indicators=result.js_indicators,
                        notes=result.notes,
                        warnings=result.warnings,
                    ).model_dump(by_alias=True)
            except Exception as exc:
                logger.warning("Selenium fallback failed for %s: %s", url, exc)

    # ---- Step 6: Return whatever we have ----
    final_confidence = result.confidence
    final_warnings = list(result.warnings)
    if not result.preview_items:
        final_confidence = "low"
        if result.needs_javascript and not _is_selenium_available():
            final_warnings.append(
                "Page appears to require JavaScript but Selenium is not available."
            )

    return AnalyzeResponse(
        url=url,
        extraction_method="selenium" if result.needs_javascript else "css_selectors",
        selectors=result.selectors,
        preview_items=result.preview_items,
        confidence=final_confidence,
        needs_javascript=result.needs_javascript,
        js_indicators=result.js_indicators,
        notes=result.notes,
        warnings=final_warnings,
    ).model_dump(by_alias=True)


@router.post("", status_code=201)
def create_source(
    body: CreateSourceRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save a confirmed user source with validated extraction configuration."""
    # Validate extraction_method / field combinations
    method = body.extraction_method
    if method not in ("rss", "css_selectors", "selenium"):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid extraction_method '{method}'. Must be rss, css_selectors, or selenium.",
        )
    if method == "rss" and not body.feed_url:
        raise HTTPException(
            status_code=422,
            detail="feed_url is required when extraction_method is 'rss'.",
        )
    if method in ("css_selectors", "selenium") and not body.selectors:
        raise HTTPException(
            status_code=422,
            detail=f"selectors are required when extraction_method is '{method}'.",
        )

    key = _user_source_key(str(user.id), body.name)

    existing = db.query(AggregationSource).filter(AggregationSource.key == key).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A source with key '{key}' already exists.",
        )

    source = AggregationSource(
        key=key,
        name=body.name,
        source_type="user",
        category=body.category,
        content_types=body.content_types,
        url=str(body.url),
        selectors=body.selectors.model_dump() if body.selectors else None,
        url_prefix=body.url_prefix,
        extraction_method=method,
        feed_url=body.feed_url,
        requires_js=(method == "selenium"),
        created_by=user.id,
        enabled=True,
        default_enabled=False,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return _serialize_source(source)


@router.get("")
def list_sources(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List system plugins and the current user's own custom sources."""
    # System plugins
    system = []
    for plugin in get_all_plugins():
        system.append({
            "key": plugin.key,
            "name": plugin.name,
            "sourceType": "system",
            "category": plugin.category,
            "contentTypes": plugin.content_types,
            "url": None,
            "enabled": True,
            "lastRunAt": None,
            "lastItemCount": None,
            "createdAt": None,
        })

    # User sources
    user_sources = (
        db.query(AggregationSource)
        .filter(
            AggregationSource.created_by == user.id,
            AggregationSource.source_type == "user",
        )
        .all()
    )
    user_serialized = [_serialize_source(s) for s in user_sources]

    return {
        "total": len(system) + len(user_serialized),
        "sources": system + user_serialized,
    }


# NOTE: /visibility/bulk must be registered before /{key} to avoid FastAPI
# treating "visibility" as a path parameter.

@router.put("/visibility/bulk")
def bulk_visibility(
    body: BulkVisibilityRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Batch-toggle visibility for multiple user sources."""
    if not body.sources:
        return {"updated": [], "count": 0}

    keys = list(body.sources.keys())
    sources = (
        db.query(AggregationSource)
        .filter(
            AggregationSource.key.in_(keys),
            AggregationSource.created_by == user.id,
            AggregationSource.source_type == "user",
        )
        .all()
    )

    updated: List[Dict[str, Any]] = []
    for source in sources:
        desired = body.sources.get(source.key)
        if desired is not None and source.enabled != desired:
            source.enabled = desired
            updated.append(_serialize_source(source))

    db.commit()
    return {"updated": updated, "count": len(updated)}


@router.get("/{key}")
def get_source(
    key: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get details for a single source (system or user-owned)."""
    # Check system plugins first
    for plugin in get_all_plugins():
        if plugin.key == key:
            return {
                "key": plugin.key,
                "name": plugin.name,
                "sourceType": "system",
                "category": plugin.category,
                "contentTypes": plugin.content_types,
                "url": None,
                "enabled": True,
            }

    # Check user sources
    source = db.query(AggregationSource).filter(AggregationSource.key == key).first()
    if not source or str(source.created_by) != str(user.id):
        raise HTTPException(status_code=404, detail="Source not found.")
    return _serialize_source(source)


@router.patch("/{key}")
def update_source(
    key: str,
    body: UpdateSourceRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a user-owned source."""
    source = _get_user_source(key, user, db)

    if body.name is not None:
        source.name = body.name
    if body.enabled is not None:
        source.enabled = body.enabled
    if body.category is not None:
        source.category = body.category
    if body.selectors is not None:
        source.selectors = body.selectors.model_dump()
    if body.extraction_method is not None:
        if body.extraction_method not in ("rss", "css_selectors", "selenium"):
            raise HTTPException(
                status_code=422,
                detail=f"Invalid extraction_method '{body.extraction_method}'.",
            )
        source.extraction_method = body.extraction_method
        source.requires_js = (body.extraction_method == "selenium")
    if body.feed_url is not None:
        source.feed_url = body.feed_url

    db.commit()
    db.refresh(source)
    return _serialize_source(source)


@router.delete("/{key}", status_code=204)
def delete_source(
    key: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a user-owned source."""
    source = _get_user_source(key, user, db)
    db.delete(source)
    db.commit()


@router.post("/{key}/test")
def test_source(
    key: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Dry-run scrape with current selectors — does not persist items."""
    source = _get_user_source(key, user, db)

    try:
        items = scrape_user_source(source)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Scrape failed: {exc}",
        )

    return {
        "source": source.key,
        "itemCount": len(items),
        "items": items[:10],
    }


@router.post("/{key}/refresh")
async def refresh_source(
    key: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Re-fetch the URL and run the full detection flow to update extraction config."""
    source = _get_user_source(key, user, db)

    if not source.url:
        raise HTTPException(status_code=400, detail="Source has no URL configured.")

    # ---- Step 1: Fetch raw HTML ----
    try:
        raw_html = await asyncio.to_thread(_fetch_raw_html, source.url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {exc}")

    # ---- Step 2: Re-check for RSS feed ----
    detected_method = None
    detected_feed_url = None
    detected_feed_title = None
    rss_preview: List[Dict[str, Any]] = []

    try:
        feed_url = await asyncio.to_thread(discover_feed_url, raw_html, source.url)
    except Exception:
        feed_url = None

    if feed_url:
        is_valid, item_count, feed_title = await asyncio.to_thread(validate_feed, feed_url)
        if is_valid and item_count > 0:
            detected_method = "rss"
            detected_feed_url = feed_url
            detected_feed_title = feed_title
            rss_preview = await asyncio.to_thread(_build_rss_preview, feed_url)

    # ---- Step 3: LLM analysis (if not RSS) ----
    result: Optional[AnalysisResult] = None
    if not detected_method:
        cleaned = clean_html(raw_html)
        if not cleaned or len(cleaned) < 100:
            raise HTTPException(
                status_code=422,
                detail="Page content too short after cleaning; cannot analyze.",
            )

        try:
            result = await analyze_page(source.url, cleaned)
        except Exception as exc:
            logger.exception("LLM refresh failed for %s", source.key)
            raise HTTPException(status_code=502, detail=f"LLM analysis failed: {exc}")

        if result.preview_items and not result.needs_javascript:
            detected_method = "css_selectors"
        elif result.needs_javascript or not result.preview_items:
            # ---- Step 4: Selenium fallback ----
            if _is_selenium_available():
                try:
                    rendered_html = await asyncio.to_thread(_fetch_html_with_selenium, source.url)
                    from app.services.aggregation.llm_analyzer import _extract_preview
                    selenium_preview = _extract_preview(rendered_html, result.selectors)
                    if selenium_preview:
                        detected_method = "selenium"
                except Exception as exc:
                    logger.warning("Selenium fallback failed during refresh for %s: %s", source.key, exc)

            if not detected_method:
                detected_method = "selenium" if result.needs_javascript else "css_selectors"

    # ---- Update the source record ----
    if detected_method == "rss":
        source.extraction_method = "rss"
        source.feed_url = detected_feed_url
        source.requires_js = False
        source.llm_analysis = {
            "feed_title": detected_feed_title,
            "refreshed_at": datetime.now(timezone.utc).isoformat(),
        }
    elif result:
        source.extraction_method = detected_method or "css_selectors"
        source.selectors = result.selectors.model_dump()
        source.requires_js = (detected_method == "selenium")
        source.llm_analysis = {
            "confidence": result.confidence,
            "notes": result.notes,
            "needs_javascript": result.needs_javascript,
            "refreshed_at": datetime.now(timezone.utc).isoformat(),
        }

    source.needs_refresh = False
    db.commit()
    db.refresh(source)

    response: Dict[str, Any] = {
        "source": source.key,
        "extractionMethod": source.extraction_method,
    }
    if detected_method == "rss":
        response["feedUrl"] = detected_feed_url
        response["feedTitle"] = detected_feed_title
        response["previewItems"] = rss_preview
        response["confidence"] = "high"
    elif result:
        response["selectors"] = result.selectors.model_dump()
        response["previewItems"] = result.preview_items
        response["confidence"] = result.confidence
        response["notes"] = result.notes
        response["warnings"] = result.warnings
        response["needsJavascript"] = result.needs_javascript

    return response


# ---------------------------------------------------------------------------
# Visibility endpoints
# ---------------------------------------------------------------------------

@router.post("/{key}/visibility")
def toggle_visibility(
    key: str,
    body: VisibilityRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Toggle a single source's sidebar visibility."""
    source = _get_user_source(key, user, db)
    source.enabled = body.enabled
    db.commit()
    db.refresh(source)
    return _serialize_source(source)
