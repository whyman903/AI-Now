"""
Firecrawl Service for Web Scraping
Replaces Selenium-based scraping with Firecrawl API for better reliability and performance.
"""

import asyncio
import logging
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from firecrawl import FirecrawlApp
import httpx

logger = logging.getLogger(__name__)


class FirecrawlService:
    """
    Service for web scraping using Firecrawl API.
    Provides clean, structured data extraction without the complexity of Selenium.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Firecrawl service with API key."""
        self.api_key = api_key or os.getenv('FIRECRAWL_API_KEY')
        if not self.api_key or self.api_key == 'fc-test-key':
            logger.warning("FIRECRAWL_API_KEY not found or is placeholder. Firecrawl scraping will be disabled.")
            self.firecrawl = None
        else:
            try:
                self.firecrawl = FirecrawlApp(api_key=self.api_key)
                logger.info("✅ Firecrawl service initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Firecrawl: {e}")
                self.firecrawl = None
    
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
                return result
            else:
                # Safely handle unexpected result shapes
                err = result.get('error') if isinstance(result, dict) else 'No content returned'
                logger.warning(f"Failed to scrape {url}: {err}")
                return None

        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
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
                            'published_at': datetime.now(),
                            'scraped_at': datetime.now(),
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
                    
                    article_data = {
                        'title': title,
                        'content': f"{description}\n\nAuthors: {authors}" if authors else description,
                        'source_url': link,
                        'source_name': source_config['name'],
                        'category': source_config['category'],
                        'content_type': 'research_paper',
                        'published_at': datetime.now(),
                        'scraped_at': datetime.now(),
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
        """Extract articles from Anthropic news page using markdown content."""
        articles = []
        
        try:
            import re
            markdown_content = scraped_data.get('markdown', '')
            if not markdown_content:
                return articles
            
            # Extract article links from markdown using regex
            article_patterns = re.findall(r'\[([^\]]+)\]\(([^\)]+)\)', markdown_content)
            
            for title, url in article_patterns:
                if '/news/' in url and len(title.strip()) > 10:
                    # Clean up the title (remove extra formatting)
                    clean_title = re.sub(r'\*\*([^*]+)\*\*', r'\1', title.strip())
                    clean_title = re.sub(r'\\n.*', '', clean_title).strip()
                    
                    if not clean_title or len(clean_title) < 5:
                        continue
                    
                    # Make sure URL is absolute
                    if url.startswith('/'):
                        url = f"https://www.anthropic.com{url}"
                    
                    article_data = {
                        'title': clean_title,
                        'content': f"Article from {source_config['name']}",
                        'source_url': url,
                        'source_name': source_config['name'],
                        'category': source_config['category'],
                        'content_type': 'article',
                        'published_at': datetime.now(),
                        'scraped_at': datetime.now()
                    }
                    
                    articles.append(article_data)
                    
                    # Limit to top 10 articles
                    if len(articles) >= 10:
                        break
            
        except Exception as e:
            logger.error(f"Error in Anthropic articles extraction: {e}")
        
        return articles
    
    async def _extract_qwen_articles(
        self, 
        scraped_data: Dict[str, Any], 
        source_config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extract articles from Qwen blog page."""
        articles = []
        
        try:
            from bs4 import BeautifulSoup
            html_content = scraped_data.get('html', '')
            if not html_content:
                # Fallback: derive a single article from markdown if present
                md = scraped_data.get('markdown') or scraped_data.get('content') or ''
                if md:
                    title = scraped_data.get('metadata', {}).get('title', 'Qwen Blog')
                    articles.append({
                        'title': title,
                        'content': md[:500],
                        'source_url': source_config['url'],
                        'source_name': source_config['name'],
                        'category': source_config['category'],
                        'content_type': 'article',
                        'published_at': datetime.now(),
                        'scraped_at': datetime.now()
                    })
                return articles
            
            soup = BeautifulSoup(html_content, 'html.parser')
            article_elements = soup.select('article.post-entry')
            
            for article in article_elements[:10]:  # Limit to top 10
                try:
                    title_elem = article.select_one('header.entry-header h2')
                    link_elem = article.select_one('a.entry-link')
                    
                    if not title_elem or not link_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    link = link_elem.get('href', '')
                    
                    # Extract content
                    content_elem = article.select_one('div.entry-content p')
                    content = content_elem.get_text(strip=True) if content_elem else ""
                    
                    article_data = {
                        'title': title,
                        'content': content,
                        'source_url': link,
                        'source_name': source_config['name'],
                        'category': source_config['category'],
                        'content_type': 'article',
                        'published_at': datetime.now(),
                        'scraped_at': datetime.now()
                    }
                    
                    articles.append(article_data)
                    
                except Exception as e:
                    logger.error(f"Error extracting Qwen article: {e}")
                    continue
            
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
                
                article_data = {
                    'title': title,
                    'content': description or content[:500],  # Use description or first 500 chars
                    'source_url': metadata.get('sourceURL') or metadata.get('sourceUrl') or source_config.get('url', ''),
                    'source_name': source_config['name'],
                    'category': source_config['category'],
                    'content_type': 'article',
                    'published_at': datetime.now(),
                    'scraped_at': datetime.now()
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
