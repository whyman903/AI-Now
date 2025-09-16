"""
Firecrawl Service for Web Scraping
Replaces Selenium-based scraping with Firecrawl API for better reliability and performance.
"""

import asyncio
import time
import logging
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from firecrawl import FirecrawlApp
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


class FirecrawlService:
    """
    Service for web scraping using Firecrawl API.
    Provides clean, structured data extraction without the complexity of Selenium.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Firecrawl service with API key."""
        # Prefer explicit arg, then environment, then app settings (.env via pydantic)
        self.api_key = api_key or os.getenv('FIRECRAWL_API_KEY') or settings.FIRECRAWL_API_KEY
        if not self.api_key or self.api_key == 'fc-test-key':
            logger.warning("FIRECRAWL_API_KEY not found or is placeholder. Firecrawl scraping will be disabled.")
            self.firecrawl = None
        else:
            try:
                self.firecrawl = FirecrawlApp(api_key=self.api_key)
                logger.info("Firecrawl service initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Firecrawl: {e}")
                self.firecrawl = None

        # Simple rate limiter (token spacing) to respect RPM caps
        try:
            rpm_env = os.getenv('FIRECRAWL_MAX_RPM')
            self._max_rpm = int(rpm_env) if rpm_env else 8  # default conservative
        except Exception:
            self._max_rpm = 8
        self._min_interval = 60.0 / max(1, self._max_rpm)
        self._rate_lock = asyncio.Lock()
        self._last_req_ts = 0.0

        # Small in-process cache to avoid re-scraping the same URL within TTL
        try:
            ttl_env = os.getenv('FIRECRAWL_SCRAPE_TTL_SECONDS')
            self._cache_ttl = int(ttl_env) if ttl_env else 6 * 60 * 60  # 6 hours
        except Exception:
            self._cache_ttl = 6 * 60 * 60
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_time: Dict[str, float] = {}

    async def _throttle(self):
        """Throttle Firecrawl calls to approximately self._max_rpm."""
        async with self._rate_lock:
            now = time.time()
            wait = self._min_interval - (now - self._last_req_ts)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_req_ts = time.time()

    async def _scrape_url_local(self, url: str, headers: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
        """Scrape a URL using local httpx + BeautifulSoup. Returns a dict with html and basic metadata.
        This avoids Firecrawl rate limits and works for most static pages.
        """
        ua = headers.get('User-Agent') if headers else None
        default_headers = {
            'User-Agent': ua or 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache',
        }
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=default_headers) as client:
                resp = await client.get(url)
                if resp.status_code >= 400:
                    # Try cloudscraper synchronously as a fallback for sites behind Cloudflare
                    try:
                        import cloudscraper  # type: ignore
                        def _get():
                            s = cloudscraper.create_scraper()
                            r = s.get(url, headers=default_headers, timeout=30)
                            r.raise_for_status()
                            return r.text
                        html_text = await asyncio.get_event_loop().run_in_executor(None, _get)
                        return self._build_local_scrape_payload(html_text, url)
                    except Exception:
                        return None
                return self._build_local_scrape_payload(resp.text, url)
        except Exception:
            return None

    def _build_local_scrape_payload(self, html_text: str, url: str) -> Dict[str, Any]:
        """Construct a Firecrawl-like payload from raw HTML: {html, metadata}.
        We only populate fields needed by existing extractors.
        """
        meta: Dict[str, Any] = {}
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_text, 'html.parser')
            # Title
            try:
                t = soup.find('title')
                if t and t.get_text():
                    meta['title'] = t.get_text().strip()
            except Exception:
                pass
            # Common meta tags
            for attr, key in (('name', 'description'), ('property', 'og:title'), ('property', 'og:description'),
                              ('property', 'og:image'), ('name', 'twitter:image'), ('name', 'twitter:image:src'),
                              ('property', 'article:published_time'), ('name', 'article:published_time')):
                try:
                    el = soup.find('meta', attrs={attr: key})
                    if el and el.get('content'):
                        meta[key] = el['content']
                except Exception:
                    pass
            # Record source URL
            meta['sourceURL'] = url
        except Exception:
            pass
        return {'html': html_text, 'metadata': meta}
    
    async def scrape_url(self, url: str, options: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Scrape a single URL using Firecrawl.
        
        Args:
            url: URL to scrape
            options: Additional scraping options for Firecrawl
            
        Returns:
            Dictionary containing scraped content or None if failed
        """
        if not self.firecrawl:
            logger.debug("Firecrawl not initialized. Skipping scrape.")
            return None

        try:
            # Serve from cache if fresh
            now_ts = time.time()
            ts = self._cache_time.get(url)
            if ts and (now_ts - ts) < self._cache_ttl:
                cached = self._cache.get(url)
                if cached is not None:
                    return cached

            # Prefer local scraping when Firecrawl is disabled via env
            if os.getenv('DISABLE_FIRECRAWL', 'false').lower() in ('1', 'true', 'yes'):
                local = await self._scrape_url_local(url)
                if local:
                    self._cache[url] = local
                    self._cache_time[url] = time.time()
                    return local

            await self._throttle()
            # Default options aligned with Firecrawl SDK
            # Include HTML so downstream extractors (e.g., Qwen, HF Papers) can parse structure.
            default_options: Dict[str, Any] = {
                'pageOptions': {
                    'includeHtml': True,
                    'onlyMainContent': False,
                }
            }

            if options:
                # shallow-merge at top-level, then deep-merge pageOptions if provided
                merged = {**default_options, **options}
                if 'pageOptions' in options:
                    merged['pageOptions'] = {**default_options.get('pageOptions', {}), **options['pageOptions']}
                default_options = merged

            logger.debug(f"Scraping URL: {url}")

            # Run Firecrawl scrape in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.firecrawl.scrape_url(url, params=default_options)
            )

            if result and ('content' in result or 'markdown' in result or 'html' in result):
                logger.debug(f"Successfully scraped {url}")
                # Cache successful result
                self._cache[url] = result
                self._cache_time[url] = time.time()
                return result
            else:
                # Safely handle unexpected result shapes
                err = result.get('error') if isinstance(result, dict) else 'No content returned'
                logger.warning(f"Failed to scrape {url} via Firecrawl: {err}; trying local scraper")
                local = await self._scrape_url_local(url)
                if local:
                    self._cache[url] = local
                    self._cache_time[url] = time.time()
                    return local
                # Cache negative briefly to reduce hammering
                self._cache[url] = None  # sentinel
                self._cache_time[url] = time.time()
                return None

        except Exception as e:
            msg = str(e)
            # Handle Firecrawl 429 backoff text: "retry after 22s"
            if 'Status code 429' in msg:
                import re
                m = re.search(r'retry after (\d+)s', msg)
                wait_s = int(m.group(1)) if m else 30
                logger.warning(f"Rate limited by Firecrawl. Sleeping {wait_s}s then retrying once for {url}")
                await asyncio.sleep(wait_s)
                try:
                    await self._throttle()
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        None,
                        lambda: self.firecrawl.scrape_url(url, params={'pageOptions': {'includeHtml': True, 'onlyMainContent': False}})
                    )
                    if result and ('content' in result or 'markdown' in result or 'html' in result):
                        self._cache[url] = result
                        self._cache_time[url] = time.time()
                        return result
                    # Fallback to local
                    local = await self._scrape_url_local(url)
                    if local:
                        self._cache[url] = local
                        self._cache_time[url] = time.time()
                        return local
                except Exception as e2:
                    logger.error(f"Retry failed for {url}: {e2}")
                return None
            else:
                logger.error(f"Error scraping {url}: {e}; trying local scraper")
                local = await self._scrape_url_local(url)
                if local:
                    self._cache[url] = local
                    self._cache_time[url] = time.time()
                    return local
                return None

    def _to_utc_naive(self, dt: datetime) -> datetime:
        """Convert potentially timezone-aware datetimes to UTC naive for DB storage consistency."""
        try:
            if dt.tzinfo is None:
                # Assume naive datetimes are already UTC
                return dt
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            return datetime.now(timezone.utc).replace(tzinfo=None)

    def _parse_datetime_candidate(self, value: Any) -> Optional[datetime]:
        """Parse a date/time candidate value into a datetime. Supports ISO strings and epochs."""
        if value is None:
            return None
        try:
            # Numeric epochs (seconds or ms)
            if isinstance(value, (int, float)):
                # Heuristic: treat 13+ digit as ms
                if value > 10_000_000_000:  # > ~2286-11-20 in seconds; so this is likely ms
                    value = value / 1000.0
                return datetime.fromtimestamp(float(value), tz=timezone.utc)
            # Strings
            if isinstance(value, str):
                s = value.strip()
                if not s:
                    return None
                # Some sites emit like '2024-09-15T10:30:00Z' or '2024-09-15 10:30:00+00:00'
                try:
                    from dateutil import parser as dateparser  # lazy import
                    dt = dateparser.parse(s)
                    if dt is None:
                        return None
                    # If parsed without tz, assume UTC (safer for server-side semantics)
                    if dt.tzinfo is None:
                        return dt.replace(tzinfo=timezone.utc)
                    return dt
                except Exception:
                    return None
        except Exception:
            return None
        return None

    def _extract_published_datetime(self, scraped_data: Dict[str, Any]) -> Optional[datetime]:
        """
        Try to extract a published datetime from Firecrawl result via metadata, JSON-LD, or HTML meta tags.
        Returns a UTC-naive datetime suitable for DB storage, or None if not found.
        """
        # 1) Directly from Firecrawl metadata
        metadata: Dict[str, Any] = scraped_data.get('metadata', {}) or {}
        candidate_keys = [
            # Common
            'published', 'published_at', 'publishedAt', 'date', 'datePublished', 'date_published',
            'publish_date', 'pubDate', 'timestamp', 'time', 'article:published_time', 'og:published_time',
            'dateCreated', 'dateModified', 'dc:date', 'dc.date', 'dcterms:created', 'release_date'
        ]
        # Firecrawl may flatten meta tags into metadata with keys like 'og:published_time'
        for key in candidate_keys:
            if key in metadata:
                dt = self._parse_datetime_candidate(metadata.get(key))
                if dt:
                    return self._to_utc_naive(dt)

        # 2) JSON-LD scripts
        try:
            html = scraped_data.get('html') or ''
            if html:
                from bs4 import BeautifulSoup
                import json
                soup = BeautifulSoup(html, 'html.parser')
                for script in soup.find_all('script', type=lambda t: t and 'ld+json' in t):
                    try:
                        data = json.loads(script.string or '')
                    except Exception:
                        continue
                    # Normalize to list
                    objs = data if isinstance(data, list) else [data]
                    for obj in objs:
                        if not isinstance(obj, dict):
                            continue
                        # Consider common article-like types
                        typ = obj.get('@type')
                        if isinstance(typ, list):
                            types = {t.lower() for t in typ if isinstance(t, str)}
                        else:
                            types = {str(typ).lower()} if typ else set()
                        if types.intersection({'article', 'newsarticle', 'blogposting', 'techarticle', 'report', 'webpage'}):
                            for k in ('datePublished', 'dateCreated', 'dateModified', 'uploadDate'):
                                if k in obj:
                                    dt = self._parse_datetime_candidate(obj.get(k))
                                    if dt:
                                        return self._to_utc_naive(dt)
        except Exception:
            pass

        # 3) HTML meta/time tags
        try:
            html = scraped_data.get('html') or ''
            if html:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, 'html.parser')
                meta_selectors = [
                    ('meta', {'property': 'article:published_time'}),
                    ('meta', {'name': 'article:published_time'}),
                    ('meta', {'property': 'og:published_time'}),
                    ('meta', {'name': 'og:published_time'}),
                    ('meta', {'name': 'pubdate'}),
                    ('meta', {'name': 'publish_date'}),
                    ('meta', {'name': 'date'}),
                    ('meta', {'property': 'date'}),
                    ('time', {'datetime': True}),
                ]
                for tag, attrs in meta_selectors:
                    el = soup.find(tag, attrs=attrs)
                    if el:
                        value = el.get('content') or el.get('datetime')
                        dt = self._parse_datetime_candidate(value)
                        if dt:
                            return self._to_utc_naive(dt)
        except Exception:
            pass

        # 4) Visible date text fallback (helps Anthropic xAI style pages)
        try:
            html = scraped_data.get('html') or ''
            if html:
                from bs4 import BeautifulSoup
                import re
                soup = BeautifulSoup(html, 'html.parser')

                # Prefer elements whose class hints at time/date/timestamp
                candidates = []
                try:
                    candidates.extend(soup.find_all(class_=lambda c: c and any(k in c.lower() for k in ('timestamp', 'time', 'date'))))
                except Exception:
                    pass

                # As a last resort, also scan the first chunk of page text
                texts = [
                    el.get_text(" ", strip=True) for el in candidates if hasattr(el, 'get_text')
                ]
                page_text = soup.get_text(" ", strip=True)
                if page_text:
                    texts.append(page_text[:4000])

                month_re = r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},\s+\d{4}"
                for t in texts:
                    m = re.search(month_re, t, flags=re.IGNORECASE)
                    if not m:
                        continue
                    # Clean around bullets or extra words
                    date_str = m.group(0)
                    dt = self._parse_datetime_candidate(date_str)
                    if dt:
                        return self._to_utc_naive(dt)
        except Exception:
            pass

        return None

    def _extract_thumbnail_from_scraped(self, scraped_data: Dict[str, Any]) -> Optional[str]:
        """Try to extract a representative thumbnail URL from Firecrawl result."""
        try:
            md = scraped_data.get('metadata') or {}
            # Common keys from meta extraction
            for k in (
                'og:image', 'twitter:image', 'twitter:image:src', 'image', 'thumbnail',
            ):
                if k in md and isinstance(md[k], str) and md[k].strip():
                    return md[k].strip()
        except Exception:
            pass
        # Fallback to parsing HTML meta tags
        try:
            html = scraped_data.get('html') or ''
            if not html:
                return None
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            for tag_name in ('meta', 'meta'):
                # property first, then name
                for attr in (('property', 'og:image'), ('name', 'og:image'), ('name', 'twitter:image'), ('name', 'twitter:image:src')):
                    el = soup.find(tag_name, attrs={attr[0]: attr[1]})
                    if el and el.get('content'):
                        return el['content']
        except Exception:
            return None
        return None
    
    async def extract_articles_from_page(
        self, 
        url: str, 
        source_config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Extract articles from a web page using Firecrawl.
        
        Args:
            url: URL to scrape
            source_config: Configuration for the specific source
            
        Returns:
            List of extracted articles with title, content, link, etc.
        """
        scraped_data = await self.scrape_url(url)
        if not scraped_data:
            return []
        
        articles = []
        
        try:
            # Get the HTML content for parsing specific elements if needed
            html_content = scraped_data.get('html', '')
            markdown_content = scraped_data.get('markdown', '')
            metadata = scraped_data.get('metadata', {})
            
            # For some sources, we might need to parse the HTML for specific elements
            # Firecrawl's markdown output is often sufficient for most content
            
            if source_config['name'] == 'Hugging Face Papers':
                articles = await self._extract_huggingface_papers(scraped_data, source_config)
            elif source_config['name'] == 'Anthropic':
                articles = await self._extract_anthropic_articles(scraped_data, source_config)
            elif source_config['name'] == 'xAI':
                articles = await self._extract_xai_articles(scraped_data, source_config)
            elif source_config['name'] == 'Qwen':
                articles = await self._extract_qwen_articles(scraped_data, source_config)
            else:
                # Generic extraction for other sources
                articles = await self._extract_generic_articles(scraped_data, source_config)
            
            logger.info(f"Extracted {len(articles)} articles from {source_config['name']}")
            return articles
            
        except Exception as e:
            logger.error(f"Error extracting articles from {url}: {e}")
            return []
    
    async def _extract_huggingface_papers(
        self, 
        scraped_data: Dict[str, Any], 
        source_config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extract papers from Hugging Face trending page."""
        articles = []
        
        try:
            # Parse the HTML content for paper-specific structure
            from bs4 import BeautifulSoup
            html_content = scraped_data.get('html', '')
            if not html_content:
                # Fallback: try to parse from markdown links if HTML not included
                md = scraped_data.get('markdown') or scraped_data.get('content') or ''
                if md:
                    # naive fallback – collect top links that look like papers
                    import re
                    links = re.findall(r'\[([^\]]+)\]\((/papers/[^\)]+)\)', md)
                    for idx, (title, href) in enumerate(links[:10], 1):
                        link = f"https://huggingface.co{href}" if href.startswith('/') else href
                        articles.append({
                            'title': title.strip(),
                            'content': '',
                            'source_url': link,
                            'source_name': source_config['name'],
                            'category': source_config['category'],
                            'content_type': 'research_paper',
                            'published_at': self._to_utc_naive(self._extract_published_datetime(scraped_data) or datetime.now(timezone.utc)),
                            'scraped_at': datetime.now(timezone.utc).replace(tzinfo=None),
                            'rank': idx
                        })
                return articles
            
            soup = BeautifulSoup(html_content, 'html.parser')
            paper_elements = soup.select('article.relative.overflow-hidden')
            
            for idx, paper in enumerate(paper_elements[:10], 1):  # Limit to top 10
                try:
                    title_elem = paper.select_one('h3 a')
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    link = title_elem.get('href', '')
                    if link.startswith('/'):
                        link = f"https://huggingface.co{link}"
                    
                    # Extract description
                    desc_elem = paper.select_one('div p')
                    description = desc_elem.get_text(strip=True) if desc_elem else ""
                    
                    # Extract authors
                    authors_elem = paper.select_one('p.text-gray-600.text-sm')
                    authors = authors_elem.get_text(strip=True) if authors_elem else ""
                    
                    # Try to determine published date from the page (listing often lacks per-item date)
                    published_dt = self._extract_published_datetime(scraped_data) or datetime.now(timezone.utc)
                    article_data = {
                        'title': title,
                        'content': f"{description}\n\nAuthors: {authors}" if authors else description,
                        'source_url': link,
                        'source_name': source_config['name'],
                        'category': source_config['category'],
                        'content_type': 'research_paper',
                        'published_at': self._to_utc_naive(published_dt),
                        'scraped_at': datetime.now(timezone.utc).replace(tzinfo=None),
                        'rank': idx
                    }
                    
                    articles.append(article_data)
                    
                except Exception as e:
                    logger.error(f"Error extracting paper {idx}: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error in Hugging Face papers extraction: {e}")
        
        return articles

    async def _extract_anthropic_articles(
        self, 
        scraped_data: Dict[str, Any], 
        source_config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extract Anthropic posts by collecting links then fetching each post page.
        Captures title, published date, thumbnail, and sets author.
        """
        articles: List[Dict[str, Any]] = []
        try:
            import re
            md = scraped_data.get('markdown') or scraped_data.get('content') or ''
            if not md:
                return articles

            pairs = re.findall(r'\[([^\]]+)\]\(([^\)]+)\)', md)
            seen = set()
            candidates: List[Dict[str, str]] = []
            for title, href in pairs:
                t = (title or '').strip()
                u = (href or '').strip()
                if len(t) < 3:
                    continue
                if u.startswith('/'):
                    u = f"https://www.anthropic.com{u}"
                if not u.startswith('https://www.anthropic.com/'):
                    continue
                if '/news/' not in u:
                    continue
                if u in seen:
                    continue
                seen.add(u)
                candidates.append({'title': re.sub(r'\s+', ' ', t), 'url': u})

            if not candidates:
                return articles

            sem = asyncio.Semaphore(3)
            max_items = 5

            async def fetch_detail(c: Dict[str, str]) -> Optional[Dict[str, Any]]:
                async with sem:
                    detail = await self.scrape_url(c['url'])
                if not detail:
                    return None
                page_title = (detail.get('metadata') or {}).get('title')
                title_val = page_title or c['title']
                published_dt = self._extract_published_datetime(detail) or (datetime.now(timezone.utc) - timedelta(minutes=1))
                thumb = self._extract_thumbnail_from_scraped(detail)
                return {
                    'title': title_val,
                    'content': (detail.get('markdown') or detail.get('content') or '')[:500] or f"Article from {source_config['name']}",
                    'source_url': c['url'],
                    'source_name': source_config['name'],
                    'category': source_config['category'],
                    'content_type': 'article',
                    'author': source_config['name'],
                    'published_at': self._to_utc_naive(published_dt),
                    'scraped_at': datetime.now(timezone.utc).replace(tzinfo=None),
                    'thumbnail_url': thumb,
                }

            tasks = [fetch_detail(c) for c in candidates[:max_items]]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, dict):
                    articles.append(r)

        except Exception as e:
            logger.error(f"Error in Anthropic articles extraction: {e}")
        return articles

    async def _extract_xai_articles(
        self,
        scraped_data: Dict[str, Any],
        source_config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extract articles from xAI blog using markdown link parsing.

        We rely on Firecrawl to render/collect the page. Then we parse markdown
        for post links, preferring URLs under `/blog/` or absolute x.ai links.
        """
        articles: List[Dict[str, Any]] = []
        try:
            import re
            md = scraped_data.get('markdown') or scraped_data.get('content') or ''
            if not md:
                return articles

            # Collect markdown links (title, url)
            pairs = re.findall(r'\[([^\]]+)\]\(([^\)]+)\)', md)
            seen = set()
            candidates: List[Dict[str, str]] = []
            for title, href in pairs:
                t = (title or '').strip()
                u = (href or '').strip()
                if len(t) < 3:
                    continue
                # Accept x.ai blog/news posts
                if u.startswith('/') and ('/blog/' in u or '/news/' in u):
                    u = f"https://x.ai{u}"
                elif not (u.startswith('https://x.ai/')):
                    continue
                if ('/blog/' not in u) and ('/news/' not in u):
                    continue
                if u in seen:
                    continue
                seen.add(u)
                candidates.append({'title': re.sub(r'\s+', ' ', t), 'url': u})

            if not candidates:
                return articles

            # Fetch each post page via Firecrawl to extract date and thumbnail
            # Limit concurrency and total items to keep it light
            max_items = 5
            sem = asyncio.Semaphore(3)

            async def fetch_detail(c: Dict[str, str]) -> Optional[Dict[str, Any]]:
                async with sem:
                    detail = await self.scrape_url(c['url'])
                if not detail:
                    return None
                # Prefer page-specific title if available
                page_title = (detail.get('metadata') or {}).get('title')
                title_val = page_title or c['title']
                published_dt = self._extract_published_datetime(detail) or (datetime.now(timezone.utc) - timedelta(minutes=1))
                thumb = self._extract_thumbnail_from_scraped(detail)
                return {
                    'title': title_val,
                    'content': (detail.get('markdown') or detail.get('content') or '')[:500] or f"Article from {source_config['name']}",
                    'source_url': c['url'],
                    'source_name': source_config['name'],
                    'category': source_config['category'],
                    'content_type': 'article',
                    'author': source_config['name'],
                    'published_at': self._to_utc_naive(published_dt),
                    'scraped_at': datetime.now(timezone.utc).replace(tzinfo=None),
                    'thumbnail_url': thumb,
                }

            tasks = [fetch_detail(c) for c in candidates[:max_items]]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, dict):
                    articles.append(r)

        except Exception as e:
            logger.error(f"Error in xAI articles extraction: {e}")
        return articles
    
    async def _extract_qwen_articles(
        self, 
        scraped_data: Dict[str, Any], 
        source_config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extract Qwen posts; fetch per-post to capture date/thumbnail and set author."""
        articles: List[Dict[str, Any]] = []
        
        try:
            from bs4 import BeautifulSoup
            html_content = scraped_data.get('html', '')
            candidates: List[Dict[str, str]] = []
            if html_content:
                soup = BeautifulSoup(html_content, 'html.parser')
                for article in soup.select('article.post-entry')[:10]:
                    title_elem = article.select_one('header.entry-header h2')
                    link_elem = article.select_one('a.entry-link')
                    if not title_elem or not link_elem:
                        continue
                    title = title_elem.get_text(strip=True)
                    url = link_elem.get('href', '')
                    if url.startswith('/'):
                        # Base of Qwen blog
                        url = f"https://qwenlm.github.io{url}"
                    candidates.append({'title': title, 'url': url})
            else:
                # Fallback: derive a single article from markdown if present
                md = scraped_data.get('markdown') or scraped_data.get('content') or ''
                if md:
                    title = scraped_data.get('metadata', {}).get('title', 'Qwen Blog')
                    candidates.append({'title': title, 'url': source_config['url']})

            if not candidates:
                return articles

            sem = asyncio.Semaphore(3)
            max_items = 5

            async def fetch_detail(c: Dict[str, str]) -> Optional[Dict[str, Any]]:
                async with sem:
                    detail = await self.scrape_url(c['url'])
                if not detail:
                    return None
                page_title = (detail.get('metadata') or {}).get('title')
                title_val = page_title or c['title']
                published_dt = self._extract_published_datetime(detail) or (datetime.now(timezone.utc) - timedelta(minutes=1))
                thumb = self._extract_thumbnail_from_scraped(detail)
                return {
                    'title': title_val,
                    'content': (detail.get('markdown') or detail.get('content') or '')[:500] or f"Article from {source_config['name']}",
                    'source_url': c['url'],
                    'source_name': source_config['name'],
                    'category': source_config['category'],
                    'content_type': 'article',
                    'author': source_config['name'],
                    'published_at': self._to_utc_naive(published_dt),
                    'scraped_at': datetime.now(timezone.utc).replace(tzinfo=None),
                    'thumbnail_url': thumb,
                }

            tasks = [fetch_detail(c) for c in candidates[:max_items]]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, dict):
                    articles.append(r)

        except Exception as e:
            logger.error(f"Error in Qwen articles extraction: {e}")
        
        return articles
    
    async def _extract_generic_articles(
        self, 
        scraped_data: Dict[str, Any], 
        source_config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generic article extraction for sources without specific handling."""
        articles = []
        
        try:
            # Use the markdown content for generic extraction
            markdown_content = scraped_data.get('markdown', '')
            metadata = scraped_data.get('metadata', {})
            
            # For generic sources, create a single article from the page content
            if markdown_content:
                title = metadata.get('title', 'Untitled')
                description = metadata.get('description', '')
                
                # Extract first few paragraphs as content
                lines = markdown_content.split('\n')
                content_lines = [line for line in lines if line.strip() and not line.startswith('#')]
                content = '\n'.join(content_lines[:5])  # First 5 non-header lines
                
                published_dt = self._extract_published_datetime(scraped_data) or datetime.now(timezone.utc)
                article_data = {
                    'title': title,
                    'content': description or content[:500],  # Use description or first 500 chars
                    'source_url': metadata.get('sourceURL') or metadata.get('sourceUrl') or source_config.get('url', ''),
                    'source_name': source_config['name'],
                    'category': source_config['category'],
                    'content_type': 'article',
                    'published_at': self._to_utc_naive(published_dt),
                    'scraped_at': datetime.now(timezone.utc).replace(tzinfo=None)
                }
                
                articles.append(article_data)
            
        except Exception as e:
            logger.error(f"Error in generic articles extraction: {e}")
        
        return articles
    
    async def health_check(self) -> bool:
        """Check if Firecrawl service is healthy."""
        if not self.firecrawl:
            return False
        
        try:
            # Test with a simple, reliable URL
            result = await self.scrape_url('https://httpbin.org/html')
            return result is not None and result.get('success', False)
        except Exception as e:
            logger.error(f"Firecrawl health check failed: {e}")
            return False


# Singleton instance
_firecrawl_service = None

def get_firecrawl_service() -> FirecrawlService:
    """Get the singleton Firecrawl service instance."""
    global _firecrawl_service
    if _firecrawl_service is None:
        _firecrawl_service = FirecrawlService()
    return _firecrawl_service
