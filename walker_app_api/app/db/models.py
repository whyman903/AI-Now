"""Database models for the content aggregation service."""

from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    JSON,
    Index,
    UniqueConstraint,
    Integer,
    ForeignKey,
    Float,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
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


class UserSession(Base):
    """Track user sessions for analytics."""

    __tablename__ = "user_sessions"

    session_id = Column(String(128), primary_key=True)
    user_id = Column(String(128), index=True)
    first_seen = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    last_seen = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    user_agent = Column(Text)
    ip_address = Column(String(64))
    referrer = Column(Text)
    page_views = Column(Integer, nullable=False, server_default="0")
    interactions = Column(Integer, nullable=False, server_default="0")


class ContentInteraction(Base):
    """Track user interactions with content items."""

    __tablename__ = "content_interactions"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    content_id = Column(String, ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(String(128), ForeignKey("user_sessions.session_id", ondelete="SET NULL"))
    user_id = Column(String(128))
    interaction_type = Column(String(64), nullable=False)
    timestamp = Column(DateTime, nullable=False, server_default=func.now())
    source_page = Column(String(255))
    position = Column(Integer)
    referrer = Column(Text)
    user_agent = Column(Text)
    meta_data = Column("metadata", JSON)

    __table_args__ = (
        Index("ix_content_interactions_content_id", "content_id"),
        Index("ix_content_interactions_session_id", "session_id"),
        Index("ix_content_interactions_timestamp", "timestamp"),
        Index("ix_content_interactions_type", "interaction_type"),
    )


class SearchQuery(Base):
    """Track search queries for analytics and improvement."""

    __tablename__ = "search_queries"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    session_id = Column(String(128), ForeignKey("user_sessions.session_id", ondelete="SET NULL"), index=True)
    user_id = Column(String(128))
    query = Column(Text, nullable=False)
    timestamp = Column(DateTime, nullable=False, server_default=func.now())
    results_count = Column(Integer)
    filters = Column(JSON)
    clicked_result_id = Column(String(128))
    clicked_position = Column(Integer)
    referrer = Column(Text)
    user_agent = Column(Text)
    __table_args__ = (
        Index("ix_search_queries_query", "query"),
        Index("ix_search_queries_timestamp", "timestamp"),
        Index("ix_search_queries_session_id", "session_id"),
    )

class AggregationRun(Base):
    """Store a summary of unified aggregation executions."""

    __tablename__ = "aggregation_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    started_at = Column(DateTime, nullable=False, index=True)
    completed_at = Column(DateTime)
    duration_seconds = Column(Float)
    status = Column(String(32), nullable=False, server_default="completed", index=True)
    total_new_items = Column(Integer, nullable=False, server_default="0")
    total_items_updated = Column(Integer, nullable=False, server_default="0")
    items_with_thumbnails = Column(Integer, nullable=False, server_default="0")
    error_count = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime, server_default=func.now())

    sources = relationship(
        "AggregationRunSource",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class AggregationRunSource(Base):
    """Store per-source statistics for a given aggregation run."""

    __tablename__ = "aggregation_run_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("aggregation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_name = Column(String, nullable=False)
    source_type = Column(String, nullable=False)
    items_added = Column(Integer, nullable=False, server_default="0")
    items_updated = Column(Integer, nullable=False, server_default="0")
    items_with_thumbnails = Column(Integer, nullable=False, server_default="0")
    error_message = Column(Text)
    metrics = Column(JSON)

    run = relationship("AggregationRun", back_populates="sources")

    __table_args__ = (
        Index("ix_aggregation_run_sources_run_id", "run_id"),
        Index("ix_aggregation_run_sources_source_type", "source_type"),
    )
