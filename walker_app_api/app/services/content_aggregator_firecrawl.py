"""
Unified Content Aggregator using RSS, YouTube RSS and Firecrawl.
Streamlined for consistent normalization, thumbnail enrichment, and persistence.
"""

import asyncio
import httpx
import feedparser
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from collections import OrderedDict, defaultdict

from app.db.base import SessionLocal
from app.db.models import ContentItem, FeedState
from app.services.firecrawl_service import get_firecrawl_service

logger = logging.getLogger(__name__)


class ContentAggregatorFirecrawl:
    """
    Updated content aggregation service that uses Firecrawl instead of Selenium.
    Fetches content from:
    - RSS feeds (news, blogs, podcasts, academic papers)
    - YouTube channels via RSS
    - Web scraping via Firecrawl API
    """
    
    def __init__(self):
        """Initialize the content aggregator with all sources."""
        self.client: Optional[httpx.AsyncClient] = None
        # Per-host concurrency limit
        self._per_host_limit = 4
        self._host_limiters: Dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(self._per_host_limit))
        # Small in-memory LRU cache for thumbnails
        self._thumb_cache: OrderedDict[str, Optional[str]] = OrderedDict()
        self._thumb_cache_size = 256
        
        # Initialize all content sources
        self._initialize_rss_sources()
        self._initialize_youtube_sources()
        self._initialize_web_scraper_sources()
        
    def _initialize_rss_sources(self):
        """Initialize RSS feed sources from the core configuration."""
        self.rss_sources = [
            # AI/ML Research & Company Blogs
            {"name": "OpenAI Blog", "url": "https://openai.com/blog/rss.xml", "category": "ai_ml", "type": "blog"},
            {"name": "Google AI Blog", "url": "https://research.google/blog/rss", "category": "ai_ml", "type": "blog"},
            {"name": "DeepMind Blog", "url": "https://deepmind.google/blog/rss.xml", "category": "ai_ml", "type": "blog"},
            {"name": "Microsoft Research", "url": "https://www.microsoft.com/en-us/research/feed/", "category": "ai_ml", "type": "blog"},
            {"name": "NVIDIA Developer Blog", "url": "https://developer.nvidia.com/blog/feed/", "category": "ai_ml", "type": "blog"},
            # {"name": "Hugging Face Blog", "url": "https://huggingface.co/blog/feed.xml", "category": "ai_ml", "type": "blog"},
            
            # Podcasts
            # {"name": "Lex Fridman Podcast", "url": "https://lexfridman.com/feed/podcast/", "category": "ai_ml", "type": "podcast"},
            {"name": "Y Combinator Podcast", "url": "https://www.ycombinator.com/blog/feed/", "category": "startup", "type": "podcast"},
            
            # Startup/Business
            {"name": "Sequoia Capital", "url": "https://www.sequoiacap.com/feed/", "category": "startup", "type": "blog"},
        ]

    def set_http_client(self, client: httpx.AsyncClient) -> None:
        """Inject a shared AsyncClient managed by app lifespan."""
        self.client = client

    # -------------------- Utilities --------------------

    def _utcnow_naive(self) -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def canonicalize(self, url: str) -> str:
        """Canonicalize a URL for dedupe: lower host/scheme, strip fragment, sort query, drop trackers."""
        try:
            if not url:
                return url
            parsed = urlparse(url)
            scheme = (parsed.scheme or 'https').lower()
            netloc = parsed.netloc.lower()
            # Drop default ports
            if netloc.endswith(':80') and scheme == 'http':
                netloc = netloc[:-3]
            if netloc.endswith(':443') and scheme == 'https':
                netloc = netloc[:-4]
            path = parsed.path or '/'
            # Normalize trailing slash (keep only root slash)
            if path != '/' and path.endswith('/'):
                path = path[:-1]
            # Strip fragment
            fragment = ''
            # Clean query params
            tracking = {
                'utm_source','utm_medium','utm_campaign','utm_term','utm_content',
                'gclid','fbclid','igshid','mc_cid','mc_eid','ref','ref_', 'yclid'
            }
            q = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=False) if k not in tracking]
            q.sort()
            query = urlencode(q)
            return urlunparse((scheme, netloc, path, '', query, fragment))
        except Exception:
            return url

    async def _get(self, url: str, headers: Optional[Dict[str, str]] = None) -> httpx.Response:
        if not self.client:
            # Fallback ephemeral client, in case not injected (should be injected at app startup)
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as temp:
                return await temp.get(url, headers=headers)
        host = urlparse(url).netloc.lower()
        sem = self._host_limiters[host]
        async with sem:
            return await self.client.get(url, headers=headers)
        
    def _initialize_youtube_sources(self):
        """Initialize YouTube channel sources."""
        self.youtube_channels = [
            # AI Research & Education
            {"name": "3Blue1Brown", "channel_id": "UCYO_jab_esuFRV4b17AJtAw", "category": "ai_ml"},
            {"name": "Two Minute Papers", "channel_id": "UCbfYPyITQ-7l4upoX8nvctg", "category": "ai_ml"},
            {"name": "Yannic Kilcher", "channel_id": "UCZHmQk67mSJgfCCTn7xBfew", "category": "ai_ml"},
            {"name": "AI Explained", "channel_id": "UCNJ1Ymd5yFuUPtn21xtRbbw", "category": "ai_ml"},
            {"name": "Machine Learning Street Talk", "channel_id": "UCMLtBahI5DMrt0NPvDSoIRQ", "category": "ai_ml"},
            {"name": "Lex Fridman", "channel_id": "UCSHZKyawb77ixDdsGog4iWA", "category": "ai_ml"},
            
            # Company Channels
            {"name": "OpenAI", "channel_id": "UCXZCJLdBC09xxGZ6gcdrc6A", "category": "ai_ml"},
            {"name": "Google DeepMind", "channel_id": "UCP7jMXSY2xbc3KCAE0MHQ-A", "category": "ai_ml"},
            
            # Programming & Tech
            {"name": "Y Combinator", "channel_id": "UCcefcZRL2oaA_uBNeo5UOWg", "category": "startup"},
        ]
        
    def _initialize_web_scraper_sources(self):
        """
        Initialize web scraper sources for Firecrawl.
        Note: selectors are kept for backward compatibility but Firecrawl handles extraction differently.
        """
        self.web_scraper_sources = [
            {
                "name": "Anthropic",
                "url": "https://www.anthropic.com/news",
                "category": "ai_ml",
                "selectors": {
                    "container": "a.CardSpotlight_spotlightCard__a_XQp",
                    "title": "h3",
                    "link": "self",
                    "content": "p.paragraph-m"
                }
            },
            {
                "name": "xAI",
                "url": "https://x.ai/blog",
                "category": "ai_ml",
                "selectors": {
                    "container": "a",
                    "title": "a",
                    "link": "self",
                    "content": "p"
                }
            },
            {
                "name": "Qwen",
                "url": "https://qwenlm.github.io/blog/",
                "category": "ai_ml",
                "selectors": {
                    "container": "article.post-entry",
                    "title": "header.entry-header h2",
                    "link": "a.entry-link",
                    "content": "div.entry-content p"
                }
            },
            {
                "name": "Hugging Face Papers",
                "url": "https://huggingface.co/papers/trending",
                "category": "ai_ml",
                "selectors": {
                    "container": "article.relative.overflow-hidden",
                    "title": "h3 a",
                    "link": "h3 a",
                    "content": "div p",
                    "authors": "p.text-gray-600.text-sm",
                    "rank": "position"
                }
            },
        ]
    
    async def aggregate_all_content(self) -> Dict[str, Any]:
        """
        Main aggregation method that fetches content from all sources.
        Returns statistics about the aggregation process.
        """
        logger.info("Starting unified content aggregation with Firecrawl...")
        start_time = self._utcnow_naive()
        
        results = {
            'started_at': start_time.isoformat(),
            'sources': {},
            'total_new_items': 0,
            'total_items_updated': 0,
            'items_with_thumbnails': 0,
            'errors': []
        }
        
        # Run all aggregation tasks concurrently
        tasks = [
            self._aggregate_rss_feeds(),
            self._aggregate_youtube_channels(),
            self._aggregate_web_scrapers_firecrawl()
        ]

        source_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        source_names = ['rss_feeds', 'youtube_channels', 'web_scrapers']
        for i, result in enumerate(source_results):
            source_name = source_names[i]

            if isinstance(result, Exception):
                error_msg = f"Error in {source_name}: {str(result)}"
                logger.error(error_msg)
                results['errors'].append(error_msg)
                results['sources'][source_name] = {'error': str(result)}
            else:
                results['sources'][source_name] = result
                results['total_new_items'] += result.get('items_added', 0)
                results['total_items_updated'] += result.get('items_updated', 0)
                results['items_with_thumbnails'] += result.get('items_with_thumbnails', 0)
        
        # Calculate final statistics
        end_time = self._utcnow_naive()
        results['completed_at'] = end_time.isoformat()
        results['duration_seconds'] = (end_time - start_time).total_seconds()
        
        logger.info(f"Aggregation completed: {results['total_new_items']} new items in {results['duration_seconds']:.2f}s")
        
        return results
    
    async def _aggregate_rss_feeds(self) -> Dict[str, Any]:
        """Aggregate content from RSS feeds."""
        logger.info("Aggregating RSS feeds...")
        
        items_added = 0
        items_processed = 0
        items_with_thumbnails = 0
        items_updated = 0
        
        # Process feeds concurrently in batches
        batch_size = 6
        for i in range(0, len(self.rss_sources), batch_size):
            batch = self.rss_sources[i:i + batch_size]
            tasks = [self._process_rss_feed(feed) for feed in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for j, result in enumerate(batch_results):
                feed_config = batch[j]
                feed_name = feed_config['name']
                
                if isinstance(result, Exception):
                    logger.error(f"Error processing {feed_name}: {result}")
                    continue
                    
                if isinstance(result, list) and result:
                    items_processed += len(result)
                    # Persist in one go (handles dedupe + thumbnail enrichment)
                    persist_stats = await self._persist_items(result)
                    items_added += persist_stats['items_added']
                    items_with_thumbnails += persist_stats['items_with_thumbnails']
                    items_updated += persist_stats.get('items_updated', 0)
                    source_items_added = persist_stats['items_added']
                    
                    logger.info(f"Processed {feed_name}: Found {len(result)} items, added {source_items_added} new.")
        
        logger.info(f"RSS aggregation: {items_added} new items from {len(self.rss_sources)} feeds")
        
        return {
            'items_processed': items_processed,
            'items_added': items_added,
            'items_with_thumbnails': items_with_thumbnails,
            'items_updated': items_updated
        }
    
    async def _aggregate_youtube_channels(self) -> Dict[str, Any]:
        """Aggregate content from YouTube channels via RSS."""
        logger.info("Aggregating YouTube channels...")
        
        items_added = 0
        items_processed = 0
        items_with_thumbnails = 0
        items_updated = 0
        
        for channel in self.youtube_channels:
            try:
                # YouTube RSS feed URL
                rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel['channel_id']}"
                
                response = await self._get(rss_url)
                if response.status_code != 200:
                    logger.error(f"Failed to fetch {channel['name']}: HTTP {response.status_code}")
                    continue
                
                # Parse RSS feed
                feed = feedparser.parse(response.text)
                channel_items: List[Dict[str, Any]] = []

                for entry in feed.entries[:10]:  # Limit per channel
                    # Extract video ID from Atom
                    video_id = getattr(entry, 'yt_videoid', None)
                    if not video_id and hasattr(entry, 'id') and isinstance(entry.id, str):
                        # entry.id often like 'yt:video:VIDEO_ID'
                        parts = entry.id.split(':')
                        if parts and parts[-1]:
                            video_id = parts[-1]
                    # Thumbnails via media if provided
                    thumbnail_url = None
                    try:
                        thumbs = getattr(entry, 'media_thumbnail', None) or getattr(entry, 'media_thumbnails', None)
                        if thumbs and isinstance(thumbs, list) and thumbs[0].get('url'):
                            thumbnail_url = thumbs[0]['url']
                    except Exception:
                        pass
                    if not thumbnail_url and video_id:
                        # hqdefault is reliable
                        thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                    published_at = (
                        datetime(*entry.published_parsed[:6]) if getattr(entry, 'published_parsed', None)
                        else self._utcnow_naive()
                    )

                    channel_items.append({
                        'type': 'youtube_video',
                        'title': entry.title,
                        'url': entry.link,
                        'author': channel['name'],
                        'published_at': published_at,
                        'thumbnail_url': thumbnail_url,
                        'meta_data': {
                            'source_name': channel['name'],
                            'category': channel['category'],
                            'video_id': video_id,
                            'channel_id': channel['channel_id'],
                            'extraction_method': 'youtube_rss',
                        },
                    })

                items_processed += len(channel_items)
                persist_stats = await self._persist_items(channel_items)
                items_added += persist_stats['items_added']
                items_with_thumbnails += persist_stats['items_with_thumbnails']
                items_updated += persist_stats.get('items_updated', 0)

                logger.info(f"Processed {channel['name']}: Found {len(feed.entries)} videos, added {persist_stats['items_added']} new.")
                
            except Exception as e:
                logger.error(f"Error processing YouTube channel {channel['name']}: {e}")
                continue
        
        logger.info(f"YouTube aggregation: {items_added} new videos from {len(self.youtube_channels)} channels")
        
        return {
            'items_processed': items_processed,
            'items_added': items_added,
            'items_with_thumbnails': items_with_thumbnails,
            'items_updated': items_updated
        }
    
    async def _aggregate_web_scrapers_firecrawl(self) -> Dict[str, Any]:
        """Aggregate content from web scrapers using Firecrawl."""
        logger.info("Aggregating web scrapers with Firecrawl...")
        
        items_added = 0
        items_processed = 0
        items_with_thumbnails = 0
        items_updated = 0
        updated_hf_papers = []
        
        # Get Firecrawl service
        firecrawl_service = get_firecrawl_service()
        
        if not firecrawl_service.firecrawl:
            logger.warning("Firecrawl service not available. Skipping web scraper aggregation.")
            return {
                'items_processed': 0,
                'items_added': 0,
                'items_with_thumbnails': 0,
                'error': 'Firecrawl service not available'
            }
        
        for source in self.web_scraper_sources:
            try:
                logger.info(f"Processing {source['name']} with Firecrawl...")
                
                # Extract articles using Firecrawl
                articles = await firecrawl_service.extract_articles_from_page(source['url'], source)
                
                items_processed += len(articles)
                # Normalize metadata and persist in one go
                normalized = []
                for article_data in articles:
                    # Normalize common metadata
                    meta = {
                        'source_name': article_data['source_name'],
                        'source': self._extract_source_from_url(article_data['source_url']),
                        'category': article_data['category'],
                        'extraction_method': 'firecrawl',
                    }

                    # Include rank and scraped_date for trending papers (Hugging Face)
                    if article_data.get('rank') is not None:
                        meta['rank'] = article_data.get('rank')
                    # Frontend expects 'scraped_date' to group by most recent snapshot
                    if article_data.get('scraped_at'):
                        try:
                            meta['scraped_date'] = article_data['scraped_at'].isoformat()
                        except Exception:
                            meta['scraped_date'] = str(article_data.get('scraped_at'))

                    normalized.append({
                        'type': article_data.get('content_type', 'article'),
                        'title': article_data['title'],
                        'url': article_data['source_url'],
                        'author': article_data.get('author', ''),
                        'published_at': article_data['published_at'],
                        'thumbnail_url': article_data.get('thumbnail_url'),
                        'meta_data': meta,
                    })

                persist_stats = await self._persist_items(normalized)
                items_added += persist_stats['items_added']
                items_with_thumbnails += persist_stats['items_with_thumbnails']
                items_updated += persist_stats.get('items_updated', 0)
                # Capture details for HF papers that were updated for better observability
                if source['name'] == 'Hugging Face Papers' and persist_stats.get('updated_details'):
                    updated_hf_papers.extend(persist_stats['updated_details'])

                logger.info(f"Processed {source['name']}: Found {len(articles)} items, added {persist_stats['items_added']} new.")
                
            except Exception as e:
                logger.error(f"Error processing web scraper {source['name']}: {e}")
                continue
        
        logger.info(f"Web scraper aggregation with Firecrawl: {items_added} new items, {items_updated} updated")
        if updated_hf_papers:
            try:
                logger.info("Updated Hugging Face ranks:")
                for d in updated_hf_papers[:10]:
                    logger.info(f"  rank {d.get('rank')} · {d.get('title')} · date {d.get('scraped_date')}")
            except Exception:
                pass
        
        return {
            'items_processed': items_processed,
            'items_added': items_added,
            'items_with_thumbnails': items_with_thumbnails,
            'items_updated': items_updated
        }
    
    # Helper methods (simplified versions of the originals)
    
    async def _process_rss_feed(self, feed_config: Dict[str, str]) -> List[Dict[str, Any]]:
        """Process a single RSS feed."""
        try:
            # Conditional GET using stored ETag/Last-Modified
            from app.db.base import SessionLocal
            db = SessionLocal()
            headers: Dict[str, str] = {}
            try:
                state = db.query(FeedState).filter(FeedState.feed_url == feed_config['url']).first()
                if state:
                    if state.etag:
                        headers['If-None-Match'] = state.etag
                    if state.last_modified:
                        headers['If-Modified-Since'] = state.last_modified
            except Exception:
                pass
            finally:
                db.close()

            response = await self._get(feed_config['url'], headers=headers)
            if response.status_code != 200:
                if response.status_code == 304:
                    # Not modified
                    try:
                        db = SessionLocal()
                        st = db.query(FeedState).filter(FeedState.feed_url == feed_config['url']).first()
                        if not st:
                            st = FeedState(feed_url=feed_config['url'])
                            db.add(st)
                        st.last_status = '304'
                        db.commit()
                    except Exception:
                        pass
                    finally:
                        db.close()
                    return []
                raise Exception(f"HTTP {response.status_code}")
            
            feed = feedparser.parse(response.text)
            items = []
            
            for entry in feed.entries[:15]:  # Limit per feed
                # Parse published date
                published_at = self._utcnow_naive()
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    try:
                        published_at = datetime(*entry.published_parsed[:6])
                    except:
                        pass
                # Map blog -> article for consistency
                rss_type = feed_config.get('type', 'article')
                if rss_type == 'blog':
                    rss_type = 'article'

                # thumbnail from media if present
                thumb = None
                try:
                    thumbs = getattr(entry, 'media_thumbnail', None) or getattr(entry, 'media_thumbnails', None)
                    if thumbs and isinstance(thumbs, list) and thumbs[0].get('url'):
                        thumb = thumbs[0]['url']
                except Exception:
                    pass

                item_data = {
                    'type': rss_type,
                    'title': entry.title,
                    'url': entry.link,
                    'author': feed_config['name'],
                    'published_at': published_at,
                    'thumbnail_url': thumb,
                    'meta_data': {
                        'source_name': feed_config['name'],
                        'category': feed_config['category'],
                        'extraction_method': 'rss',
                        'scraped_at': self._utcnow_naive().isoformat(),
                    }
                }
                
                items.append(item_data)

            # Update feed state with new validators
            try:
                db = SessionLocal()
                st = db.query(FeedState).filter(FeedState.feed_url == feed_config['url']).first()
                if not st:
                    st = FeedState(feed_url=feed_config['url'])
                    db.add(st)
                st.etag = response.headers.get('ETag') or st.etag
                st.last_modified = response.headers.get('Last-Modified') or st.last_modified
                st.last_status = str(response.status_code)
                db.commit()
            except Exception:
                pass
            finally:
                db.close()
            
            return items
            
        except Exception as e:
            logger.error(f"Error processing RSS feed {feed_config['name']}: {e}")
            return []
    
    async def _extract_thumbnail(self, url: str) -> Optional[str]:
        """Extract thumbnail from a URL."""
        # LRU cache check
        if url in self._thumb_cache:
            # move to end (recently used)
            val = self._thumb_cache.pop(url)
            self._thumb_cache[url] = val
            return val

        try:
            response = await self._get(url)
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Try various meta tags for thumbnails
            meta_tags = [
                'og:image',
                'twitter:image',
                'twitter:image:src'
            ]
            
            for tag in meta_tags:
                meta = soup.find('meta', property=tag) or soup.find('meta', name=tag)
                if meta and meta.get('content'):
                    thumb = meta['content']
                    # update cache
                    self._thumb_cache[url] = thumb
                    # enforce size
                    if len(self._thumb_cache) > self._thumb_cache_size:
                        self._thumb_cache.popitem(last=False)
                    return thumb
            
            self._thumb_cache[url] = None
            if len(self._thumb_cache) > self._thumb_cache_size:
                self._thumb_cache.popitem(last=False)
            return None
            
        except Exception as e:
            logger.debug(f"Error extracting thumbnail from {url}: {e}")
            return None
    
    def _extract_source_from_url(self, url: str) -> str:
        """Extract source organization from URL."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Remove www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]
            
            # Extract main domain name
            parts = domain.split('.')
            if len(parts) >= 2:
                return parts[-2].title()
            
            return domain.title()
            
        except:
            return "Unknown"

    async def _persist_items(self, items: List[Dict[str, Any]]) -> Dict[str, int]:
        """Upsert items by source_url. For existing Hugging Face papers, update rank/scraped_date.
        Also enrich thumbnails for new items. Returns counts for added, updated, and with thumbnails.
        """
        # Normalize and drop invalid items
        candidates = [i for i in items if (i.get('url') or i.get('source_url')) and i.get('title')]
        if not candidates:
            return {'items_added': 0, 'items_with_thumbnails': 0}

        # Compute normalized URLs and prepare lookup keys
        for i in candidates:
            i['url'] = i.get('url') or i.get('source_url')
            i['url'] = self.canonicalize(i['url'])

        urls = [i['url'] for i in candidates]

        db = SessionLocal()
        has_norm_col = False

        # Fetch existing items keyed by normalized_url and source_url
        existing_items_by_url = {ci.url: ci for ci in db.query(ContentItem).filter(ContentItem.url.in_(urls)).all()}

        # First, handle updates for existing items (especially HF trending)
        items_updated = 0
        updated_details = []
        for item in candidates:
            existing = existing_items_by_url.get(item['url'])
            if not existing:
                continue

            try:
                # Special handling for Hugging Face trending papers (update rank/snapshot)
                is_hf_paper = False
                try:
                    is_hf_paper = (
                        (item.get('type') == 'research_paper') and
                        (item.get('meta_data') or {}).get('source_name') == 'Hugging Face Papers'
                    )
                except Exception:
                    is_hf_paper = False

                changed = False
                if is_hf_paper:
                    existing_meta = existing.meta_data or {}
                    incoming_meta = item.get('meta_data') or {}
                    if 'rank' in incoming_meta and existing_meta.get('rank') != incoming_meta['rank']:
                        existing_meta['rank'] = incoming_meta['rank']
                        changed = True
                    if 'scraped_date' in incoming_meta and existing_meta.get('scraped_date') != incoming_meta['scraped_date']:
                        existing_meta['scraped_date'] = incoming_meta['scraped_date']
                        changed = True
                    if 'source_name' in incoming_meta:
                        existing_meta['source_name'] = incoming_meta['source_name']
                    # Update author/title if they changed slightly
                    if item.get('author') and item['author'] != (existing.author or ''):
                        existing.author = item['author']
                        changed = True
                    if item.get('title') and item['title'] != existing.title:
                        existing.title = item['title']
                        changed = True
                    if changed:
                        existing.meta_data = existing_meta
                else:
                    # Generic updates for existing items
                    if item.get('published_at'):
                        try:
                            if (not getattr(existing, 'published_at', None)) or (existing.published_at and existing.published_at > item['published_at']):
                                existing.published_at = item['published_at']
                                changed = True
                        except Exception:
                            pass
                    if not getattr(existing, 'thumbnail_url', None) and item.get('thumbnail_url'):
                        existing.thumbnail_url = item['thumbnail_url']
                        changed = True
                    if item.get('author') and item.get('author') != getattr(existing, 'author', None):
                        existing.author = item['author']
                        changed = True

                if changed:
                    items_updated += 1
                    try:
                        updated_details.append({
                            'title': getattr(existing, 'title', ''),
                            'rank': (existing.meta_data or {}).get('rank') if is_hf_paper else None,
                            'scraped_date': (existing.meta_data or {}).get('scraped_date') if is_hf_paper else None
                        })
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(f"Failed updating existing item metadata for {item.get('url')}: {e}")

        # Determine which are new
        new_items = [i for i in candidates if (i['url'] not in existing_items_by_url)]
        if not new_items:
            db.commit()
            db.close()
            return {'items_added': 0, 'items_with_thumbnails': 0, 'items_updated': items_updated, 'updated_details': updated_details}

        # Enrich thumbnails concurrently for those missing
        sem = asyncio.Semaphore(5)

        async def enrich(item: Dict[str, Any]):
            if not item.get('thumbnail_url'):
                async with sem:
                    thumb = await self._extract_thumbnail(item['url'])
                if thumb:
                    item['thumbnail_url'] = thumb

        await asyncio.gather(*(enrich(i) for i in new_items))

        with_thumbs = 0
        for i in new_items:
            if i.get('thumbnail_url'):
                with_thumbs += 1
            # Remove any transient field not in model
            i_clean = {k: v for k, v in i.items() if k not in ['scraped_at', 'source_url', 'content', 'normalized_url', 'ai_summary', 'embedding']}
            try:
                db.add(ContentItem(**i_clean))
            except Exception:
                # Fallback to add (may raise on duplicates if constraint exists)
                try:
                    db.add(ContentItem(**i_clean))
                except Exception:
                    pass

        try:
            db.commit()
        finally:
            db.close()

        return {'items_added': len(new_items), 'items_with_thumbnails': with_thumbs, 'items_updated': items_updated, 'updated_details': updated_details}


# Singleton instance
_aggregator = None

def get_aggregator_firecrawl() -> ContentAggregatorFirecrawl:
    """Get the singleton content aggregator instance."""
    global _aggregator
    if _aggregator is None:
        _aggregator = ContentAggregatorFirecrawl()
    return _aggregator
