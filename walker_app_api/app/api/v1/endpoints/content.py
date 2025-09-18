from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session, aliased
from sqlalchemy import func, asc, desc
from app.db.base import get_db
from app.db.models import ContentItem

router = APIRouter()

def _to_iso_utc(dt: datetime):
    """Serialize datetimes as ISO8601 with Z (UTC). Handles naive values as UTC."""
    if not dt:
        return None
    try:
        if dt.tzinfo is None:
            # Naive assumed to be UTC in our storage
            return dt.isoformat() + 'Z'
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        try:
            return dt.isoformat()
        except Exception:
            return None

@router.get("")
def get_content(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    content_type: Optional[str] = Query(None),
    exclude_type: Optional[str] = Query(None),
    order: Optional[str] = Query(None, description="Ordering strategy: 'recent' or 'interleave' (default). For research_paper, rank ordering applies."),
    source: Optional[str] = Query(None, description="Filter by content author."),
    db: Session = Depends(get_db)
):
    """
    Get paginated content from database with content type diversification.
    This method interleaves content types to ensure variety in the feed
    while still prioritizing the most recently published items within each type.
    """

    # Base query to work with
    base_query = db.query(ContentItem)

    if source:
        base_query = base_query.filter(ContentItem.author == source)
    
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
        # Choose ordering strategy (default to recency)
        strategy = (order or 'recent').lower()
        if strategy == 'recent':
            # Plain recent ordering
            query = base_query.order_by(ContentItem.published_at.desc())
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
            "url": item_dict.get("url"),
            "sourceUrl": item_dict.get("url"),
            "author": item_dict.get("author"),
            "publishedAt": _to_iso_utc(item_dict.get("published_at")),
            "thumbnailUrl": item_dict.get("thumbnail_url"),
            "metadata": item_dict.get("meta_data"),
            "clicks": item_dict.get("clicks"),
            "createdAt": _to_iso_utc(item_dict.get("created_at")),
            "updatedAt": _to_iso_utc(item_dict.get("updated_at"))
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
    source: Optional[str] = Query(None, description="Filter by content author."),
    db: Session = Depends(get_db)
):
    """Get trending content from database"""
    
    since = datetime.now() - timedelta(hours=hours)
    
    query = db.query(ContentItem).filter(ContentItem.published_at >= since)

    if source:
        query = query.filter(ContentItem.author == source)

    items = query.order_by(ContentItem.published_at.desc()).limit(limit).all()
    
    # Convert to camelCase for frontend compatibility
    serialized_items = []
    for item in items:
        item_dict = item.__dict__
        serialized_items.append({
            "id": item_dict.get("id"),
            "type": item_dict.get("type"),
            "title": item_dict.get("title"),
            "url": item_dict.get("url"),
            "sourceUrl": item_dict.get("url"),
            "author": item_dict.get("author"),
            "publishedAt": _to_iso_utc(item_dict.get("published_at")),
            "thumbnailUrl": item_dict.get("thumbnail_url"),
            "metadata": item_dict.get("meta_data"),
            "clicks": item_dict.get("clicks"),
            "createdAt": _to_iso_utc(item_dict.get("created_at")),
            "updatedAt": _to_iso_utc(item_dict.get("updated_at"))
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
        "url": item_dict.get("url"),
        "sourceUrl": item_dict.get("url"),
        "author": item_dict.get("author"),
        "publishedAt": _to_iso_utc(item_dict.get("published_at")),
        "thumbnailUrl": item_dict.get("thumbnail_url"),
        "metadata": item_dict.get("meta_data"),
        "clicks": item_dict.get("clicks"),
        "createdAt": _to_iso_utc(item_dict.get("created_at")),
        "updatedAt": _to_iso_utc(item_dict.get("updated_at"))
    }
