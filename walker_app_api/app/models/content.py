from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ContentType(str, Enum):
    VIDEO = "video"
    PODCAST = "podcast"
    RESEARCH_PAPER = "research_paper"
    ARTICLE = "article"
    DISCUSSION = "discussion"


class ContentSource(str, Enum):
    YOUTUBE = "youtube"
    ARXIV = "arxiv"
    HACKER_NEWS = "hacker_news"
    RSS = "rss"
    FIRECRAWL = "firecrawl"


class ContentItem(BaseModel):
    id: Optional[str] = None
    title: str
    description: Optional[str] = None
    content_type: ContentType
    source: ContentSource
    source_id: str
    url: str
    author: Optional[str] = None
    published_at: datetime
    duration_seconds: Optional[int] = None
    transcript: Optional[str] = None
    tags: List[str] = []
    meta_data: Dict[str, Any] = {}
    engagement_score: Optional[float] = None
    quality_score: Optional[float] = None
    created_at: datetime
    updated_at: datetime


class TranscriptSegment(BaseModel):
    start_time: float
    end_time: float
    text: str
    confidence: Optional[float] = None