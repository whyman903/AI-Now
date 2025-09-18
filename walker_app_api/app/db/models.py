"""Database models for the content aggregation service."""

from sqlalchemy import Column, String, Text, DateTime, JSON, Index, UniqueConstraint, Integer
from sqlalchemy.sql import func

from app.db.base import Base


class ContentItem(Base):
    """Store normalized pieces of content discovered by the aggregator."""

    __tablename__ = "content_items"

    id = Column(String, primary_key=True, server_default=func.gen_random_uuid())
    type = Column(String, nullable=False, index=True)
    title = Column(Text, nullable=False)
    url = Column(Text, nullable=False)
    author = Column(Text)
    published_at = Column(DateTime, index=True)
    thumbnail_url = Column(Text)
    meta_data = Column("metadata", JSON)
    clicks = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_content_items_type", "type"),
        Index("idx_content_items_published", "published_at"),
        UniqueConstraint("url", name="uq_content_items_url"),
    )


class FeedState(Base):
    """Persist HTTP caching metadata for upstream feeds."""

    __tablename__ = "feed_states"

    feed_url = Column(String, primary_key=True)
    etag = Column(String, nullable=True)
    last_modified = Column(String, nullable=True)
    last_checked = Column(DateTime, server_default=func.now(), onupdate=func.now())
    last_status = Column(String, nullable=True)
