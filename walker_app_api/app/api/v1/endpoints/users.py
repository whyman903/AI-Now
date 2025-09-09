from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from datetime import datetime
from app.schemas.user import User, UserCreate
from sqlalchemy.orm import Session
from app.db.base import engine
from app.db.models import User as UserModel, UserBookmark, ContentItem

router = APIRouter()

@router.post("/", response_model=User)
def create_user(user: UserCreate):
    """Create a new user"""
    # In production, this would save to database properly
    user_id = str(user.email)  # Using email as ID for simplicity
    
    return {
        "id": user_id,
        "email": user.email,
        "is_active": True
    }

@router.get("/{user_id}/profile")
def get_user_profile(user_id: str):
    """Get user's basic profile based on bookmarks"""
    db = Session(engine)
    try:
        # Get user's bookmarks to understand interests
        bookmarks = db.query(UserBookmark, ContentItem).join(
            ContentItem, UserBookmark.content_item_id == ContentItem.id
        ).filter(UserBookmark.user_id == user_id).all()
        
        if not bookmarks:
            return {
                "user_id": user_id,
                "total_bookmarks": 0,
                "interests": [],
                "preferred_sources": [],
                "content_types": []
            }
        
        # Extract interests from bookmarked content
        interests = set()
        sources = {}
        content_types = {}
        
        for bookmark, content in bookmarks:
            # Extract tags from metadata
            if content.meta_data and 'tags' in content.meta_data:
                for tag in content.meta_data['tags']:
                    interests.add(tag)
            
            # Count sources
            source_name = content.meta_data.get('source_name', 'unknown') if content.meta_data else 'unknown'
            sources[source_name] = sources.get(source_name, 0) + 1
            
            # Count content types
            content_types[content.type] = content_types.get(content.type, 0) + 1
        
        # Sort by frequency
        top_sources = sorted(sources.items(), key=lambda x: x[1], reverse=True)[:5]
        top_types = sorted(content_types.items(), key=lambda x: x[1], reverse=True)[:3]
        
        return {
            "user_id": user_id,
            "total_bookmarks": len(bookmarks),
            "interests": list(interests),
            "preferred_sources": [source for source, count in top_sources],
            "content_types": [ctype for ctype, count in top_types]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting user profile: {str(e)}")
    finally:
        db.close()

@router.get("/{user_id}/stats")
def get_user_stats(user_id: str):
    """Get user engagement statistics based on bookmarks"""
    db = Session(engine)
    try:
        # Get bookmark count by time period
        total_bookmarks = db.query(UserBookmark).filter(
            UserBookmark.user_id == user_id
        ).count()
        
        # Get recent bookmarks (last 30 days)
        from datetime import timedelta
        cutoff_date = datetime.now() - timedelta(days=30)
        recent_bookmarks = db.query(UserBookmark).filter(
            UserBookmark.user_id == user_id,
            UserBookmark.created_at >= cutoff_date
        ).count()
        
        return {
            "user_id": user_id,
            "total_bookmarks": total_bookmarks,
            "recent_bookmarks_30d": recent_bookmarks,
            "engagement_level": "high" if recent_bookmarks > 10 else "medium" if recent_bookmarks > 3 else "low"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting user stats: {str(e)}")
    finally:
        db.close()

# Remove the interests update endpoint since we're deriving interests from bookmarks