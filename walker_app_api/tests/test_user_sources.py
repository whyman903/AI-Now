"""Tests for Phase 3: html_cleaner, llm_analyzer preview, user_source_engine, sources API."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.aggregation.html_cleaner import clean_html
from app.services.aggregation.llm_analyzer import (
    AnalysisResult,
    SelectorSet,
    _extract_preview,
    _first_srcset_url,
)
from app.services.aggregation.user_source_engine import (
    _first_srcset_url as engine_first_srcset,
    _parse_date,
    _resolve_url,
    scrape_user_source,
)


# ---------------------------------------------------------------------------
# html_cleaner tests
# ---------------------------------------------------------------------------

class TestHTMLCleaner:
    def test_removes_scripts_and_styles(self):
        html = "<div><script>alert(1)</script><style>.x{}</style><p>hello</p></div>"
        result = clean_html(html)
        assert "alert" not in result
        assert ".x{}" not in result
        assert "hello" in result

    def test_removes_nav_footer_header(self):
        html = "<nav>menu</nav><main><p>content</p></main><footer>foot</footer>"
        result = clean_html(html)
        assert "menu" not in result
        assert "content" in result
        assert "foot" not in result

    def test_strips_non_keep_attributes(self):
        html = '<div class="x" data-foo="bar" onclick="evil()" id="main"><p>hi</p></div>'
        result = clean_html(html)
        assert 'class="x"' in result
        assert 'id="main"' in result
        assert "data-foo" not in result
        assert "onclick" not in result

    def test_preserves_href_and_src(self):
        html = '<a href="/link" data-track="1">click</a><img src="img.png" data-lazy="1"/>'
        result = clean_html(html)
        assert 'href="/link"' in result
        assert 'src="img.png"' in result
        assert "data-track" not in result
        assert "data-lazy" not in result

    def test_removes_empty_elements(self):
        html = "<div><span></span><p>text</p><div></div></div>"
        result = clean_html(html)
        assert "text" in result
        # Empty span and inner div should be removed
        assert "<span>" not in result or "<span></span>" not in result

    def test_truncates_to_max_chars(self):
        html = "<p>" + "x" * 20_000 + "</p>"
        result = clean_html(html, max_chars=500)
        assert len(result) <= 500

    def test_empty_input(self):
        assert clean_html("") == ""

    def test_collapses_whitespace(self):
        html = "<p>  hello    world  </p>"
        result = clean_html(html)
        # Multiple spaces should be collapsed
        assert "  " not in result or result.count("  ") == 0

    def test_keeps_time_datetime_attribute(self):
        html = '<time datetime="2024-01-15">Jan 15</time>'
        result = clean_html(html)
        assert 'datetime="2024-01-15"' in result

    def test_removes_form_elements(self):
        html = '<form><input type="text"/><button>Submit</button></form><p>content</p>'
        result = clean_html(html)
        assert "<form>" not in result
        assert "<input" not in result
        assert "<button>" not in result
        assert "content" in result


# ---------------------------------------------------------------------------
# llm_analyzer preview + srcset tests
# ---------------------------------------------------------------------------

class TestFirstSrcsetUrl:
    def test_single_url(self):
        assert _first_srcset_url("image.jpg 300w") == "image.jpg"

    def test_multiple_urls(self):
        assert _first_srcset_url("small.jpg 300w, large.jpg 600w") == "small.jpg"

    def test_density_descriptor(self):
        assert _first_srcset_url("img@2x.png 2x, img@1x.png 1x") == "img@2x.png"

    def test_none_input(self):
        assert _first_srcset_url(None) is None

    def test_empty_string(self):
        assert _first_srcset_url("") is None

    def test_url_only_no_descriptor(self):
        assert _first_srcset_url("image.png") == "image.png"

    def test_engine_version_matches(self):
        """user_source_engine has its own copy — verify it works the same."""
        assert engine_first_srcset("a.jpg 1x, b.jpg 2x") == "a.jpg"
        assert engine_first_srcset(None) is None


class TestExtractPreview:
    SAMPLE_HTML = """
    <div class="post">
        <h2><a href="/post-1">First Post</a></h2>
        <time datetime="2024-06-01">Jun 1</time>
        <img src="thumb1.jpg"/>
        <span class="author">Alice</span>
    </div>
    <div class="post">
        <h2><a href="/post-2">Second Post</a></h2>
        <time datetime="2024-06-02">Jun 2</time>
        <img src="thumb2.jpg"/>
        <span class="author">Bob</span>
    </div>
    <div class="post">
        <h2><a href="/post-3">Third Post</a></h2>
    </div>
    """

    def _selectors(self, **overrides) -> SelectorSet:
        defaults = {
            "item_container": "div.post",
            "title": "h2",
            "url": "a",
            "date": "time",
            "thumbnail": "img",
            "author": "span.author",
        }
        defaults.update(overrides)
        return SelectorSet(**defaults)

    def test_extracts_all_fields(self):
        items = _extract_preview(self.SAMPLE_HTML, self._selectors())
        assert len(items) == 3
        assert items[0]["title"] == "First Post"
        assert items[0]["url"] == "/post-1"
        assert items[0]["date"] == "2024-06-01"
        assert items[0]["thumbnail"] == "thumb1.jpg"
        assert items[0]["author"] == "Alice"

    def test_missing_optional_fields(self):
        items = _extract_preview(self.SAMPLE_HTML, self._selectors())
        # Third post has no date, thumbnail, or author
        third = items[2]
        assert third["title"] == "Third Post"
        assert "date" not in third
        assert "thumbnail" not in third
        assert "author" not in third

    def test_max_items_limit(self):
        items = _extract_preview(self.SAMPLE_HTML, self._selectors(), max_items=1)
        assert len(items) == 1

    def test_no_containers_matched(self):
        items = _extract_preview(self.SAMPLE_HTML, self._selectors(item_container="div.nonexistent"))
        assert items == []

    def test_optional_selectors_none(self):
        sel = self._selectors(date=None, thumbnail=None, author=None)
        items = _extract_preview(self.SAMPLE_HTML, sel)
        assert len(items) == 3
        assert "date" not in items[0]
        assert "thumbnail" not in items[0]
        assert "author" not in items[0]

    def test_srcset_thumbnail(self):
        html = """
        <div class="post">
            <h2><a href="/p">Title</a></h2>
            <img srcset="small.jpg 300w, big.jpg 600w"/>
        </div>
        """
        items = _extract_preview(html, self._selectors())
        assert items[0]["thumbnail"] == "small.jpg"


# ---------------------------------------------------------------------------
# user_source_engine tests
# ---------------------------------------------------------------------------

class TestResolveUrl:
    def test_absolute_url_unchanged(self):
        assert _resolve_url("https://example.com/page", "https://base.com") == "https://example.com/page"

    def test_relative_url_joined(self):
        assert _resolve_url("/blog/post", "https://example.com") == "https://example.com/blog/post"

    def test_url_prefix_override(self):
        result = _resolve_url("/post", "https://example.com", url_prefix="https://cdn.example.com")
        assert result == "https://cdn.example.com/post"

    def test_none_returns_none(self):
        assert _resolve_url(None, "https://example.com") is None

    def test_empty_string_returns_none(self):
        assert _resolve_url("", "https://example.com") is None

    def test_strips_whitespace(self):
        assert _resolve_url("  https://example.com/x  ", "https://base.com") == "https://example.com/x"


class TestParseDate:
    def test_iso_date(self):
        dt = _parse_date("2024-06-15T12:00:00Z")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 6
        assert dt.tzinfo is None  # naive UTC

    def test_human_date(self):
        dt = _parse_date("June 15, 2024")
        assert dt is not None
        assert dt.year == 2024

    def test_none_input(self):
        assert _parse_date(None) is None

    def test_empty_string(self):
        assert _parse_date("") is None

    def test_garbage_returns_none(self):
        assert _parse_date("not a date at all xyz") is None


class TestScrapeUserSource:
    BLOG_HTML = """
    <html><body>
    <article class="entry">
        <h2 class="title"><a href="https://blog.example.com/post-1">First Article</a></h2>
        <time datetime="2024-06-01">June 1, 2024</time>
        <img class="thumb" src="https://blog.example.com/img1.jpg"/>
        <span class="byline">Alice</span>
    </article>
    <article class="entry">
        <h2 class="title"><a href="/post-2">Second Article</a></h2>
        <time datetime="2024-06-02">June 2, 2024</time>
        <img class="thumb" src="/img2.jpg"/>
        <span class="byline">Bob</span>
    </article>
    <article class="entry">
        <h2 class="title"><a href="/post-2">Second Article</a></h2>
        <time datetime="2024-06-02">June 2, 2024</time>
    </article>
    </body></html>
    """

    def _make_source(self, **overrides) -> SimpleNamespace:
        defaults = {
            "key": "user_test_blog",
            "url": "https://blog.example.com",
            "name": "Test Blog",
            "category": "custom",
            "content_types": ["article"],
            "url_prefix": None,
            "selectors": {
                "item_container": "article.entry",
                "title": "h2.title",
                "url": "h2.title a",
                "date": "time",
                "thumbnail": "img.thumb",
                "author": "span.byline",
            },
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    @patch("app.services.aggregation.user_source_engine._fetch_html")
    def test_extracts_items(self, mock_fetch):
        mock_fetch.return_value = self.BLOG_HTML
        source = self._make_source()
        items = scrape_user_source(source)

        assert len(items) == 2  # third is deduped (same URL as second)
        assert items[0]["title"] == "First Article"
        assert items[0]["url"] == "https://blog.example.com/post-1"
        assert items[0]["author"] == "Alice"
        assert items[0]["thumbnail_url"] == "https://blog.example.com/img1.jpg"

    @patch("app.services.aggregation.user_source_engine._fetch_html")
    def test_resolves_relative_urls(self, mock_fetch):
        mock_fetch.return_value = self.BLOG_HTML
        source = self._make_source()
        items = scrape_user_source(source)

        # Second item has relative URL /post-2
        assert items[1]["url"] == "https://blog.example.com/post-2"
        assert items[1]["thumbnail_url"] == "https://blog.example.com/img2.jpg"

    @patch("app.services.aggregation.user_source_engine._fetch_html")
    def test_deduplicates_urls(self, mock_fetch):
        mock_fetch.return_value = self.BLOG_HTML
        source = self._make_source()
        items = scrape_user_source(source)

        urls = [i["url"] for i in items]
        assert len(urls) == len(set(urls))

    def test_no_url_returns_empty(self):
        source = self._make_source(url=None)
        assert scrape_user_source(source) == []

    def test_missing_selectors_returns_empty(self):
        source = self._make_source(selectors={})
        assert scrape_user_source(source) == []

    @patch("app.services.aggregation.user_source_engine._fetch_html")
    def test_no_containers_returns_empty(self, mock_fetch):
        mock_fetch.return_value = "<html><body><p>No articles here</p></body></html>"
        source = self._make_source()
        assert scrape_user_source(source) == []

    @patch("app.services.aggregation.user_source_engine._fetch_html")
    def test_optional_selectors_omitted(self, mock_fetch):
        mock_fetch.return_value = self.BLOG_HTML
        source = self._make_source(selectors={
            "item_container": "article.entry",
            "title": "h2.title",
            "url": "h2.title a",
        })
        items = scrape_user_source(source)
        assert len(items) == 2
        # Author falls back to source name when no author selector
        assert items[0]["author"] == "Test Blog"

    @patch("app.services.aggregation.user_source_engine._fetch_html")
    def test_url_prefix_used(self, mock_fetch):
        mock_fetch.return_value = self.BLOG_HTML
        source = self._make_source(url_prefix="https://cdn.example.com")
        items = scrape_user_source(source)
        # Second item's relative /post-2 should use url_prefix
        assert items[1]["url"] == "https://cdn.example.com/post-2"

    @patch("app.services.aggregation.user_source_engine._fetch_html")
    def test_content_type_from_source(self, mock_fetch):
        mock_fetch.return_value = self.BLOG_HTML
        source = self._make_source(content_types=["blog_post"])
        items = scrape_user_source(source)
        assert items[0]["type"] == "blog_post"

    @patch("app.services.aggregation.user_source_engine._fetch_html")
    def test_srcset_thumbnail(self, mock_fetch):
        html = """
        <article class="entry">
            <h2 class="title"><a href="/p">Post</a></h2>
            <img class="thumb" srcset="small.jpg 300w, big.jpg 600w"/>
        </article>
        """
        mock_fetch.return_value = html
        source = self._make_source()
        items = scrape_user_source(source)
        assert items[0]["thumbnail_url"] == "https://blog.example.com/small.jpg"

    @patch("app.services.aggregation.user_source_engine._fetch_html")
    def test_meta_data_includes_category(self, mock_fetch):
        mock_fetch.return_value = self.BLOG_HTML
        source = self._make_source(category="ai_research")
        items = scrape_user_source(source)
        assert items[0]["meta_data"]["category"] == "ai_research"
        assert items[0]["meta_data"]["extraction_method"] == "user_css_selectors"
        assert items[0]["meta_data"]["source_name"] == "Test Blog"
