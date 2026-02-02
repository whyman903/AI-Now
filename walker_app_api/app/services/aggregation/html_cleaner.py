"""Clean raw HTML into a minimal representation suitable for LLM analysis."""

from __future__ import annotations

import re
from typing import Optional

from bs4 import BeautifulSoup, Comment, Tag

# Tags to remove entirely (including their children)
REMOVE_TAGS = frozenset({
    "script", "style", "noscript", "svg", "iframe", "link", "meta",
    "nav", "footer", "header", "aside", "form", "button", "input",
    "select", "textarea", "label", "fieldset", "dialog",
})

# Attributes to keep on remaining tags
KEEP_ATTRS = frozenset({
    "href", "src", "class", "id", "datetime", "aria-label",
    "alt", "title", "role", "srcset",
})


def clean_html(raw_html: str, max_chars: int = 15_000) -> str:
    """Strip *raw_html* to a compact, LLM-friendly representation.

    The result preserves structural tags (article, section, div, a, h1-h6,
    img, time, span, p, ul, ol, li) and a small set of meaningful attributes
    while removing scripts, styles, navigation, and decorative noise.

    Parameters
    ----------
    raw_html:
        The full HTML source of the page.
    max_chars:
        Truncate the cleaned output to at most this many characters.
    """
    soup = BeautifulSoup(raw_html, "html.parser")

    # 1. Remove comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # 2. Remove unwanted tags (and all their children)
    for tag in soup.find_all(REMOVE_TAGS):
        tag.decompose()

    # 3. Strip unwanted attributes from remaining tags
    for tag in soup.find_all(True):
        if not isinstance(tag, Tag):
            continue
        attrs = dict(tag.attrs)
        for attr_name in list(attrs.keys()):
            if attr_name not in KEEP_ATTRS:
                del tag.attrs[attr_name]

    # 4. Remove empty elements (no text, no children with text)
    _remove_empty(soup)

    # 5. Render back to string and collapse whitespace
    html = soup.decode_contents()
    html = _collapse_whitespace(html)

    # 6. Truncate
    if len(html) > max_chars:
        html = html[:max_chars]
        # Try to avoid cutting mid-tag
        last_close = html.rfind(">")
        if last_close != -1 and last_close > max_chars - 200:
            html = html[: last_close + 1]

    return html.strip()


def _remove_empty(soup: BeautifulSoup) -> None:
    """Remove tags that contain no meaningful text or child elements."""
    changed = True
    while changed:
        changed = False
        for tag in soup.find_all(True):
            if not isinstance(tag, Tag):
                continue
            # Keep self-closing / void elements that carry info
            if tag.name in ("img", "br", "hr", "input"):
                continue
            # Keep anchors and time even if visually empty (href/datetime carry data)
            if tag.name in ("a", "time") and tag.attrs:
                continue
            text = tag.get_text(strip=True)
            if not text and not tag.find(["img", "video", "picture"]):
                tag.decompose()
                changed = True


def _collapse_whitespace(html: str) -> str:
    """Collapse runs of whitespace / blank lines to a single space or newline."""
    # Collapse multiple blank lines
    html = re.sub(r"\n\s*\n+", "\n", html)
    # Collapse runs of spaces/tabs within lines
    html = re.sub(r"[ \t]+", " ", html)
    # Remove space around tags
    html = re.sub(r"\s*(<[^>]+>)\s*", r"\1", html)
    return html
