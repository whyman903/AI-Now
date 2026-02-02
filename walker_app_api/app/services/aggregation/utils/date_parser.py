from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional, Tuple

from dateutil import parser as dateparser


def ensure_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo:
        try:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            return dt
    return dt


def parse_date(value: Optional[str | datetime]) -> Optional[datetime]:
    """Parse a date string or datetime to a naive UTC datetime.

    Tries strategies in order:
    1. Already a datetime object
    2. ISO 8601 format
    3. dateutil fuzzy parse (handles "Sep 15, 2025", relative dates, etc.)
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return ensure_naive_utc(value)
    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    try:
        parsed = dateparser.parse(text, fuzzy=True)
    except Exception:
        return None
    if not parsed:
        return None
    return ensure_naive_utc(parsed)


def format_date_display(dt: Optional[datetime]) -> Optional[str]:
    """Format a datetime as 'Mon DD, YYYY' for display."""
    if dt is None:
        return None
    return dt.strftime("%b %d, %Y")


def format_date_iso(dt: Optional[datetime]) -> Optional[str]:
    """Format a datetime as ISO 8601 string."""
    if dt is None:
        return None
    return dt.isoformat()
