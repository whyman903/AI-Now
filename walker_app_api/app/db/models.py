"""
Database models that exactly match the Node.js schema.
This ensures both backends can work with the same database structure.
"""

from sqlalchemy import Column, String, Text, Boolean, DateTime, JSON, ForeignKey, Index, UniqueConstraint, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class User(Base):
    """User model matching Node.js users table exactly"""
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, server_default=func.gen_random_uuid())
    email = Column(String, unique=True, nullable=False, index=True)
    password = Column(String, nullable=False)
    first_name = Column("first_name", String)
    last_name = Column("last_name", String) 
    profile_image_url = Column("profile_image_url", String)
    interests = Column(Text, nullable=False, server_default='{}')
    onboarding_completed = Column("onboarding_completed", Boolean, default=False)
    created_at = Column("created_at", DateTime, server_default=func.now())
    updated_at = Column("updated_at", DateTime, server_default=func.now(), onupdate=func.now())
    
    interactions = relationship("UserInteraction", back_populates="user")
    bookmarks = relationship("UserBookmark", back_populates="user")
    bookmark_folders = relationship("BookmarkFolder", back_populates="user")


class ContentItem(Base):
    """Content items model matching Node.js content_items table exactly"""
    __tablename__ = "content_items"
    
    id = Column(String, primary_key=True, server_default=func.gen_random_uuid())
    type = Column(String, nullable=False, index=True)
    title = Column(Text, nullable=False)
    url = Column("url", Text, nullable=False)
    author = Column(Text)
    published_at = Column("published_at", DateTime, index=True)
    thumbnail_url = Column("thumbnail_url", Text)
    meta_data = Column("metadata", JSON)
    clicks = Column(Integer, nullable=False, server_default='0')
    created_at = Column("created_at", DateTime, server_default=func.now())
    updated_at = Column("updated_at", DateTime, server_default=func.now(), onupdate=func.now())
    
    interactions = relationship("UserInteraction", back_populates="content_item")
    bookmarks = relationship("UserBookmark", back_populates="content_item")
    __table_args__ = (
        Index('idx_content_items_type', 'type'),
        Index('idx_content_items_published', 'published_at'),
        UniqueConstraint('url', name='uq_content_items_url'),
    )


class FeedState(Base):
    """Track ETag/Last-Modified and status for RSS feeds."""
    __tablename__ = "feed_states"

    feed_url = Column(String, primary_key=True)
    etag = Column(String, nullable=True)
    last_modified = Column(String, nullable=True)
    last_checked = Column(DateTime, server_default=func.now(), onupdate=func.now())
    last_status = Column(String, nullable=True)


class UserInteraction(Base):
    """User interactions model matching Node.js user_interactions table exactly"""
    __tablename__ = "user_interactions"
    
    id = Column(String, primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column("user_id", String, ForeignKey("users.id"), nullable=False)
    content_item_id = Column("content_item_id", String, ForeignKey("content_items.id"), nullable=False)
    interaction_type = Column("interaction_type", String, nullable=False)
    created_at = Column("created_at", DateTime, server_default=func.now())
    
    user = relationship("User", back_populates="interactions")
    content_item = relationship("ContentItem", back_populates="interactions")
    __table_args__ = (
        Index('idx_user_interactions_user_id', 'user_id'),
        Index('idx_user_interactions_content_id', 'content_item_id'),
    )


class BookmarkFolder(Base):
    """Bookmark folders model matching Node.js bookmark_folders table exactly"""
    __tablename__ = "bookmark_folders"
    
    id = Column(String, primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column("user_id", String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text)
    color = Column(String, default="#3b82f6")
    created_at = Column("created_at", DateTime, server_default=func.now())
    updated_at = Column("updated_at", DateTime, server_default=func.now(), onupdate=func.now())
    
    user = relationship("User", back_populates="bookmark_folders")
    bookmarks = relationship("UserBookmark", back_populates="folder")


class UserBookmark(Base):
    """User bookmarks model matching Node.js user_bookmarks table exactly"""
    __tablename__ = "user_bookmarks"
    
    id = Column(String, primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column("user_id", String, ForeignKey("users.id"), nullable=False)
    content_item_id = Column("content_item_id", String, ForeignKey("content_items.id"), nullable=False)
    folder_id = Column("folder_id", String, ForeignKey("bookmark_folders.id"))
    notes = Column(Text)
    created_at = Column("created_at", DateTime, server_default=func.now())
    
    user = relationship("User", back_populates="bookmarks")
    content_item = relationship("ContentItem", back_populates="bookmarks")
    folder = relationship("BookmarkFolder", back_populates="bookmarks")
    __table_args__ = (
        Index('idx_user_bookmarks_user_id', 'user_id'),
        Index('idx_user_bookmarks_content_id', 'content_item_id'),
    )
