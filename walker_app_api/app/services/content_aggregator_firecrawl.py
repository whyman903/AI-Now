"""
Unified Content Aggregator using RSS, YouTube RSS and Firecrawl.
Streamlined for consistent normalization, thumbnail enrichment, and persistence.
"""

import asyncio
import httpx
import feedparser
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from sqlalchemy.orm import Session

from app.db.base import engine
from app.db.models import ContentItem
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
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={'User-Agent': 'Mozilla/5.0 (compatible; ContentAggregator/1.0)'}
        )
        
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
            {"name": "Hugging Face Blog", "url": "https://huggingface.co/blog/feed.xml", "category": "ai_ml", "type": "blog"},
            
            # Podcasts
            {"name": "Lex Fridman Podcast", "url": "https://lexfridman.com/feed/podcast/", "category": "ai_ml", "type": "podcast"},
            {"name": "Y Combinator Podcast", "url": "https://www.ycombinator.com/blog/feed/", "category": "startup", "type": "podcast"},
            
            # Startup/Business
            {"name": "Sequoia Capital", "url": "https://www.sequoiacap.com/feed/", "category": "startup", "type": "blog"},
        ]
        
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
        logger.info("🚀 Starting unified content aggregation with Firecrawl...")
        start_time = datetime.now()
        
        results = {
            'started_at': start_time.isoformat(),
            'sources': {},
            'total_new_items': 0,
            'items_with_thumbnails': 0,
            'errors': []
        }
        
        db = Session(engine)
        try:
            # Run all aggregation tasks concurrently
            tasks = [
                self._aggregate_rss_feeds(db),
                self._aggregate_youtube_channels(db),
                self._aggregate_web_scrapers_firecrawl(db)
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
                    results['items_with_thumbnails'] += result.get('items_with_thumbnails', 0)
            
            db.commit()
            
        except Exception as e:
            logger.error(f"Error in unified aggregation: {e}")
            db.rollback()
            results['errors'].append(str(e))
        finally:
            db.close()
        
        # Calculate final statistics
        end_time = datetime.now()
        results['completed_at'] = end_time.isoformat()
        results['duration_seconds'] = (end_time - start_time).total_seconds()
        
        logger.info(f"✅ Aggregation completed: {results['total_new_items']} new items in {results['duration_seconds']:.2f}s")
        
        return results
    
    async def _aggregate_rss_feeds(self, db: Session) -> Dict[str, Any]:
        """Aggregate content from RSS feeds."""
        logger.info("📡 Aggregating RSS feeds...")
        
        items_added = 0
        items_processed = 0
        items_with_thumbnails = 0
        
        # Process feeds concurrently in batches
        batch_size = 5
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
                    persist_stats = await self._persist_items(db, result)
                    items_added += persist_stats['items_added']
                    items_with_thumbnails += persist_stats['items_with_thumbnails']
                    source_items_added = persist_stats['items_added']
                    
                    logger.info(f"Processed {feed_name}: Found {len(result)} items, added {source_items_added} new.")
        
        logger.info(f"✅ RSS aggregation: {items_added} new items from {len(self.rss_sources)} feeds")
        
        return {
            'items_processed': items_processed,
            'items_added': items_added,
            'items_with_thumbnails': items_with_thumbnails
        }
    
    async def _aggregate_youtube_channels(self, db: Session) -> Dict[str, Any]:
        """Aggregate content from YouTube channels via RSS."""
        logger.info("📺 Aggregating YouTube channels...")
        
        items_added = 0
        items_processed = 0
        items_with_thumbnails = 0
        
        for channel in self.youtube_channels:
            try:
                # YouTube RSS feed URL
                rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel['channel_id']}"
                
                response = await self.client.get(rss_url)
                if response.status_code != 200:
                    logger.error(f"Failed to fetch {channel['name']}: HTTP {response.status_code}")
                    continue
                
                # Parse RSS feed
                feed = feedparser.parse(response.text)
                channel_items: List[Dict[str, Any]] = []

                for entry in feed.entries[:10]:  # Limit per channel
                    # Extract video ID and build normalized item
                    video_id = entry.link.split('v=')[-1] if 'v=' in entry.link else ''
                    # hqdefault exists more reliably than maxresdefault
                    thumbnail_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg" if video_id else None
                    published_at = (
                        datetime(*entry.published_parsed[:6])
                        if hasattr(entry, 'published_parsed') and entry.published_parsed
                        else datetime.now()
                    )

                    channel_items.append({
                        'type': 'video',
                        'title': entry.title,
                        'content': (entry.summary[:500] if hasattr(entry, 'summary') else ''),
                        'source_url': entry.link,
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
                persist_stats = await self._persist_items(db, channel_items)
                items_added += persist_stats['items_added']
                items_with_thumbnails += persist_stats['items_with_thumbnails']

                logger.info(f"Processed {channel['name']}: Found {len(feed.entries)} videos, added {persist_stats['items_added']} new.")
                
            except Exception as e:
                logger.error(f"Error processing YouTube channel {channel['name']}: {e}")
                continue
        
        logger.info(f"✅ YouTube aggregation: {items_added} new videos from {len(self.youtube_channels)} channels")
        
        return {
            'items_processed': items_processed,
            'items_added': items_added,
            'items_with_thumbnails': items_with_thumbnails
        }
    
    async def _aggregate_web_scrapers_firecrawl(self, db: Session) -> Dict[str, Any]:
        """Aggregate content from web scrapers using Firecrawl."""
        logger.info("🌐 Aggregating web scrapers with Firecrawl...")
        
        items_added = 0
        items_processed = 0
        items_with_thumbnails = 0
        
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
                    normalized.append({
                        'type': article_data.get('content_type', 'article'),
                        'title': article_data['title'],
                        'content': (article_data.get('content') or '')[:500],
                        'source_url': article_data['source_url'],
                        'author': article_data.get('author', ''),
                        'published_at': article_data['published_at'],
                        'thumbnail_url': article_data.get('thumbnail_url'),
                        'meta_data': {
                            'source_name': article_data['source_name'],
                            'source': self._extract_source_from_url(article_data['source_url']),
                            'category': article_data['category'],
                            'rank': article_data.get('rank'),
                            'extraction_method': 'firecrawl',
                            'scraped_at': article_data['scraped_at'].isoformat() if article_data.get('scraped_at') else None,
                        },
                    })

                persist_stats = await self._persist_items(db, normalized)
                items_added += persist_stats['items_added']
                items_with_thumbnails += persist_stats['items_with_thumbnails']

                logger.info(f"Processed {source['name']}: Found {len(articles)} items, added {persist_stats['items_added']} new.")
                
            except Exception as e:
                logger.error(f"Error processing web scraper {source['name']}: {e}")
                continue
        
        logger.info(f"✅ Web scraper aggregation with Firecrawl: {items_added} new items")
        
        return {
            'items_processed': items_processed,
            'items_added': items_added,
            'items_with_thumbnails': items_with_thumbnails
        }
    
    # Helper methods (simplified versions of the originals)
    
    async def _process_rss_feed(self, feed_config: Dict[str, str]) -> List[Dict[str, Any]]:
        """Process a single RSS feed."""
        try:
            response = await self.client.get(feed_config['url'])
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}")
            
            feed = feedparser.parse(response.text)
            items = []
            
            for entry in feed.entries[:15]:  # Limit per feed
                # Parse published date
                published_at = datetime.now()
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    try:
                        published_at = datetime(*entry.published_parsed[:6])
                    except:
                        pass
                # Map blog -> article for consistency
                rss_type = feed_config.get('type', 'article')
                if rss_type == 'blog':
                    rss_type = 'article'

                item_data = {
                    'type': rss_type,
                    'title': entry.title,
                    'content': getattr(entry, 'summary', '')[:500],
                    'source_url': entry.link,
                    'author': feed_config['name'],
                    'published_at': published_at,
                    'meta_data': {
                        'source_name': feed_config['name'],
                        'category': feed_config['category'],
                        'extraction_method': 'rss',
                        'scraped_at': datetime.now().isoformat(),
                    }
                }
                
                items.append(item_data)
            
            return items
            
        except Exception as e:
            logger.error(f"Error processing RSS feed {feed_config['name']}: {e}")
            return []
    
    async def _extract_thumbnail(self, url: str) -> Optional[str]:
        """Extract thumbnail from a URL."""
        try:
            response = await self.client.get(url)
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
                    return meta['content']
            
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

    async def _persist_items(self, db: Session, items: List[Dict[str, Any]]) -> Dict[str, int]:
        """Deduplicate by source_url, enrich thumbnails if missing, and add to session.
        Returns counts for added items and how many with thumbnails.
        """
        # Normalize and drop invalid items
        candidates = [i for i in items if i.get('source_url') and i.get('title')]
        if not candidates:
            return {'items_added': 0, 'items_with_thumbnails': 0}

        urls = [i['source_url'] for i in candidates]
        # Fetch existing URLs in one query
        existing = set(
            u for (u,) in db.query(ContentItem.source_url).filter(ContentItem.source_url.in_(urls)).all()
        )
        new_items = [i for i in candidates if i['source_url'] not in existing]
        if not new_items:
            return {'items_added': 0, 'items_with_thumbnails': 0}

        # Enrich thumbnails concurrently for those missing
        sem = asyncio.Semaphore(5)

        async def enrich(item: Dict[str, Any]):
            if not item.get('thumbnail_url'):
                async with sem:
                    thumb = await self._extract_thumbnail(item['source_url'])
                if thumb:
                    item['thumbnail_url'] = thumb

        await asyncio.gather(*(enrich(i) for i in new_items))

        with_thumbs = 0
        for i in new_items:
            if i.get('thumbnail_url'):
                with_thumbs += 1
            # Remove any transient field not in model
            i_clean = {k: v for k, v in i.items() if k != 'scraped_at'}
            db.add(ContentItem(**i_clean))

        return {'items_added': len(new_items), 'items_with_thumbnails': with_thumbs}


# Singleton instance
_aggregator = None

def get_aggregator_firecrawl() -> ContentAggregatorFirecrawl:
    """Get the singleton content aggregator instance."""
    global _aggregator
    if _aggregator is None:
        _aggregator = ContentAggregatorFirecrawl()
    return _aggregator
