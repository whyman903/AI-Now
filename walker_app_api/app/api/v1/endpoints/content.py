from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session, aliased
from sqlalchemy import func, asc, desc
from app.db.base import get_db
from app.db.models import ContentItem

router = APIRouter()

@router.get("")
def get_content(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    content_type: Optional[str] = Query(None),
    exclude_type: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Get paginated content from database with content type diversification.
    This method interleaves content types to ensure variety in the feed
    while still prioritizing the most recently published items within each type.
    """
    
    # Base query to work with
    base_query = db.query(ContentItem)
    
    # Filter by content type if specified
    if content_type:
        base_query = base_query.filter(ContentItem.type == content_type)
    # Exclude a content type if requested
    if exclude_type:
        base_query = base_query.filter(ContentItem.type != exclude_type)
    
    # For research papers, we want to order by the rank from HuggingFace
    if content_type == 'research_paper':
        # Order by the latest scrape snapshot first (NULLS LAST), then by rank within that snapshot (NULLS LAST)
        query = base_query.order_by(
            desc(ContentItem.meta_data['scraped_date'].as_string()).nullslast(),
            asc(ContentItem.meta_data['rank'].as_float()).nullslast()
        )
    else:
        # Create a subquery that assigns a row number to each item, partitioned by type
        # and ordered by recency. This lets us pick the 1st of each type, then 2nd, etc.
        ranked_items_subquery = base_query.add_columns(
            func.row_number().over(
                partition_by=ContentItem.type,
                order_by=ContentItem.published_at.desc()
            ).label("rank_in_type")
        ).subquery()

        # We query from this subquery, using an alias to refer to its columns
        ranked_content = aliased(ContentItem, ranked_items_subquery)
        
        # The main query now orders by the rank within each type, which interleaves the content.
        # A secondary sort by published date keeps the most recent items from each type group at the top.
        query = db.query(ranked_content).order_by(
            ranked_items_subquery.c.rank_in_type,
            ranked_content.published_at.desc()
        )
    
    # Apply pagination (this is now safe on the diversified query)
    total = query.count()
    items = query.offset(offset).limit(limit).all()
    
    # Convert to camelCase for frontend compatibility
    serialized_items = []
    for item in items:
        item_dict = item.__dict__
        serialized_items.append({
            "id": item_dict.get("id"),
            "type": item_dict.get("type"),
            "title": item_dict.get("title"),
            "content": item_dict.get("content"),
            "aiSummary": item_dict.get("ai_summary"),
            "sourceUrl": item_dict.get("source_url"),  # Convert to camelCase
            "author": item_dict.get("author"),
            "publishedAt": item_dict.get("published_at"),
            "thumbnailUrl": item_dict.get("thumbnail_url"),  # Convert to camelCase
            "metadata": item_dict.get("meta_data"),
            "embedding": item_dict.get("embedding"),
            "createdAt": item_dict.get("created_at"),
            "updatedAt": item_dict.get("updated_at")
        })
    
    return {
        "items": serialized_items,
        "total": total,
        "limit": limit,
        "offset": offset
    }

@router.get("/trending")
def get_trending_content(
    limit: int = Query(20, ge=1, le=50),
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db)
):
    """Get trending content from database"""
    
    since = datetime.now() - timedelta(hours=hours)
    
    items = db.query(ContentItem)\
        .filter(ContentItem.published_at >= since)\
        .order_by(ContentItem.published_at.desc())\
        .limit(limit)\
        .all()
    
    # Convert to camelCase for frontend compatibility
    serialized_items = []
    for item in items:
        item_dict = item.__dict__
        serialized_items.append({
            "id": item_dict.get("id"),
            "type": item_dict.get("type"),
            "title": item_dict.get("title"),
            "content": item_dict.get("content"),
            "aiSummary": item_dict.get("ai_summary"),
            "sourceUrl": item_dict.get("source_url"),  # Convert to camelCase
            "author": item_dict.get("author"),
            "publishedAt": item_dict.get("published_at"),
            "thumbnailUrl": item_dict.get("thumbnail_url"),  # Convert to camelCase
            "metadata": item_dict.get("meta_data"),
            "embedding": item_dict.get("embedding"),
            "createdAt": item_dict.get("created_at"),
            "updatedAt": item_dict.get("updated_at")
        })
    
    return {"items": serialized_items}

@router.get("/stats")
def get_content_stats(db: Session = Depends(get_db)):
    """Get statistics about content in database"""
    
    total_items = db.query(ContentItem).count()
    
    # Group by content type
    type_stats = db.query(ContentItem.type, func.count(ContentItem.id))\
        .group_by(ContentItem.type)\
        .all()
    
    # Recent content (last 24 hours)
    since_24h = datetime.now() - timedelta(hours=24)
    recent_count = db.query(ContentItem)\
        .filter(ContentItem.created_at >= since_24h)\
        .count()
    
    return {
        "total_items": total_items,
        "recent_24h": recent_count,
        "by_type": dict(type_stats)
    }

@router.get("/{content_id}")
def get_content_item(
    content_id: str,
    db: Session = Depends(get_db)
):
    """Get a specific content item"""
    
    item = db.query(ContentItem).filter(ContentItem.id == content_id).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Content not found")
    
    # Convert to camelCase for frontend compatibility
    item_dict = item.__dict__
    return {
        "id": item_dict.get("id"),
        "type": item_dict.get("type"),
        "title": item_dict.get("title"),
        "content": item_dict.get("content"),
        "aiSummary": item_dict.get("ai_summary"),
        "sourceUrl": item_dict.get("source_url"),  # Convert to camelCase
        "author": item_dict.get("author"),
        "publishedAt": item_dict.get("published_at"),
        "thumbnailUrl": item_dict.get("thumbnail_url"),  # Convert to camelCase
        "metadata": item_dict.get("meta_data"),
        "embedding": item_dict.get("embedding"),
        "createdAt": item_dict.get("created_at"),
        "updatedAt": item_dict.get("updated_at")
    }
