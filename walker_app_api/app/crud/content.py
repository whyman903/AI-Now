from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from app.db.models import ContentItem


class ContentCRUD:
    @staticmethod
    def create_content(db: Session, content_data: dict) -> ContentItem:
        """Create content in database"""
        existing = db.query(ContentItem).filter(
            ContentItem.source_url == content_data.get('source_url')
        ).first()
        
        if existing:
            for key, value in content_data.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            db.commit()
            db.refresh(existing)
            return existing
        
        db_content = ContentItem(**content_data)
        db.add(db_content)
        db.commit()
        db.refresh(db_content)
        return db_content
    
    @staticmethod
    def get_content_by_id(db: Session, content_id: str) -> Optional[ContentItem]:
        """Get content by ID"""
        return db.query(ContentItem).filter(ContentItem.id == content_id).first()
    
    @staticmethod
    def get_recent_content(db: Session, 
                          hours_back: int = 24,
                          limit: int = 100,
                          content_type: Optional[str] = None) -> List[ContentItem]:
        """Get recent content within specified time window"""
        cutoff_date = datetime.now() - timedelta(hours=hours_back)
        
        query = db.query(ContentItem).filter(ContentItem.published_at >= cutoff_date)
        
        if content_type:
            query = query.filter(ContentItem.type == content_type)
        
        return query.order_by(ContentItem.published_at.desc()).limit(limit).all()
    
    @staticmethod
    def search_content(db: Session, 
                      query: str,
                      limit: int = 50,
                      content_type: Optional[str] = None) -> List[ContentItem]:
        """Search content by title and content"""
        search_filter = or_(
            ContentItem.title.ilike(f'%{query}%'),
            ContentItem.content.ilike(f'%{query}%')
        )
        
        db_query = db.query(ContentItem).filter(search_filter)
        
        if content_type:
            db_query = db_query.filter(ContentItem.type == content_type)
        
        return db_query.order_by(ContentItem.published_at.desc()).limit(limit).all()
    
    @staticmethod
    def get_content_stats(db: Session) -> Dict[str, Any]:
        """Get content statistics"""
        total_content = db.query(ContentItem).count()
        
        # Content by type
        content_by_type = db.query(
            ContentItem.type,
            func.count(ContentItem.id)
        ).group_by(ContentItem.type).all()
        
        # Content with thumbnails
        with_thumbnails = db.query(ContentItem).filter(
            ContentItem.thumbnail_url.isnot(None)
        ).count()
        
        # Recent content (last 24 hours)
        recent_cutoff = datetime.now() - timedelta(hours=24)
        recent_count = db.query(ContentItem).filter(
            ContentItem.created_at >= recent_cutoff
        ).count()
        
        return {
            'total_content': total_content,
            'content_by_type': dict(content_by_type),
            'content_with_thumbnails': with_thumbnails,
            'thumbnail_percentage': (with_thumbnails / total_content * 100) if total_content > 0 else 0,
            'recent_content_24h': recent_count
        }
    
    @staticmethod
    def cleanup_old_content(db: Session, days_to_keep: int = 60) -> int:
        """Remove content older than specified days"""
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        
        deleted_count = db.query(ContentItem)\
            .filter(ContentItem.published_at < cutoff_date)\
            .delete()
        
        db.commit()
        return deleted_count