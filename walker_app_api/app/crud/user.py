from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from app.db.models import User, UserBookmark, ContentItem


class UserCRUD:
    @staticmethod
    def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
        """Get user by ID"""
        return db.query(User).filter(User.id == user_id).first()
    
    @staticmethod
    def get_user_by_email(db: Session, email: str) -> Optional[User]:
        """Get user by email"""
        return db.query(User).filter(User.email == email).first()
    
    @staticmethod
    def get_user_bookmarks(db: Session, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get user's bookmarks with content details"""
        bookmarks = db.query(UserBookmark, ContentItem).join(
            ContentItem, UserBookmark.content_item_id == ContentItem.id
        ).filter(UserBookmark.user_id == user_id).order_by(
            UserBookmark.created_at.desc()
        ).limit(limit).all()
        
        return [
            {
                'bookmark_id': bookmark.id,
                'content': {
                    'id': content.id,
                    'title': content.title,
                    'content': content.content,
                    'type': content.type,
                    'source_url': content.source_url,
                    'author': content.author,
                    'published_at': content.published_at,
                    'thumbnail_url': content.thumbnail_url,
                    'meta_data': content.meta_data
                },
                'notes': bookmark.notes,
                'created_at': bookmark.created_at
            }
            for bookmark, content in bookmarks
        ]
    
    @staticmethod
    def get_user_stats(db: Session, user_id: str) -> Dict[str, Any]:
        """Get user statistics based on bookmarks"""
        # Total bookmarks
        total_bookmarks = db.query(UserBookmark).filter(
            UserBookmark.user_id == user_id
        ).count()
        
        # Recent bookmarks (last 30 days)
        month_ago = datetime.now() - timedelta(days=30)
        recent_bookmarks = db.query(UserBookmark).filter(
            UserBookmark.user_id == user_id,
            UserBookmark.created_at >= month_ago
        ).count()
        
        # Bookmarks by content type
        bookmarks_by_type = db.query(
            ContentItem.type,
            func.count(UserBookmark.id)
        ).join(ContentItem, UserBookmark.content_item_id == ContentItem.id)\
        .filter(UserBookmark.user_id == user_id)\
        .group_by(ContentItem.type).all()
        
        return {
            'user_id': user_id,
            'total_bookmarks': total_bookmarks,
            'recent_bookmarks_30d': recent_bookmarks,
            'bookmarks_by_type': dict(bookmarks_by_type),
            'engagement_level': 'high' if total_bookmarks > 20 else 'medium' if total_bookmarks > 5 else 'low'
        }


# Import the real auth function
from app.core.auth import get_current_user