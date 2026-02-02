from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Mapping, MutableMapping, Optional
from urllib.parse import urljoin

from app.core.config import settings
from .date_parser import ensure_naive_utc

_LEGACY_THUMBNAIL_REMAP = {
    "deepseek-logo.png": "/static/images/deepseek-brand.png",
    "thinking-machines.png": "/static/images/thinking-machines-brand.png",
}


def normalize_whitespace(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return " ".join(value.split())


def resolve_public_url(value: Optional[str]) -> Optional[str]:
    if not value:
        return value

    cleaned = value.strip()
    if not cleaned:
        return cleaned

    lower_cleaned = cleaned.lower()
    for legacy_suffix, replacement in _LEGACY_THUMBNAIL_REMAP.items():
        if lower_cleaned.endswith(legacy_suffix):
            cleaned = replacement
            break

    if cleaned.startswith(("http://", "https://", "data:")):
        return cleaned

    base = (settings.PUBLIC_BASE_URL or "").strip()
    if not base:
        return cleaned

    if not base.endswith("/"):
        base = base + "/"

    return urljoin(base, cleaned.lstrip("/"))


def build_meta(
    *,
    source_name: str,
    extraction_method: str,
    category: str = "ai_ml",
    date_iso: Optional[str] = None,
    date_display: Optional[str] = None,
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "source_name": source_name,
        "category": category,
        "extraction_method": extraction_method,
    }
    if date_iso:
        meta["date_iso"] = date_iso
    if date_display:
        meta["date_display"] = date_display
    if extra:
        meta.update(extra)
    return meta


def make_item(
    *,
    title: str,
    url: str,
    source_name: str,
    extraction_method: str,
    author: Optional[str] = None,
    published_at: Optional[datetime] = None,
    thumbnail_url: Optional[str] = None,
    item_type: Optional[str] = None,
    date_iso: Optional[str] = None,
    date_display: Optional[str] = None,
    extra_meta: Optional[Mapping[str, Any]] = None,
    extra_fields: Optional[MutableMapping[str, Any]] = None,
) -> Dict[str, Any]:
    resolved_thumbnail = resolve_public_url(thumbnail_url)

    item: Dict[str, Any] = {
        "title": title,
        "url": url,
        "author": author,
        "published_at": ensure_naive_utc(published_at),
        "thumbnail_url": resolved_thumbnail,
        "type": item_type or "research_lab",
        "meta_data": build_meta(
            source_name=source_name,
            extraction_method=extraction_method,
            date_iso=date_iso,
            date_display=date_display,
            extra=extra_meta,
        ),
    }
    if extra_fields:
        item.update(extra_fields)
    return item
