#!/usr/bin/env python3
"""
Run unified content aggregation - combines RSS feeds and web scraping with comprehensive thumbnails
No sample data or fallbacks - only real content from verified sources
"""

import asyncio
import sys
import os
import json
from dotenv import load_dotenv

# Construct the path to the .env file which is in the same directory as the script
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=dotenv_path)

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.content_aggregator_firecrawl import get_aggregator_firecrawl
from sqlalchemy.orm import Session
from app.db.base import engine
from app.db.models import ContentItem

async def main():
    """Run comprehensive content aggregation"""
    print("🚀 Starting unified content aggregation...")
    print("=" * 70)
    
    aggregator = get_aggregator_firecrawl()
    try:
        # Run unified aggregation
        results = await aggregator.aggregate_all_content()
        
        # Display results as a pretty-printed JSON object for clarity
        print("\n📊 Aggregation Results Summary:")
        print(json.dumps(results, indent=2))
        
        # Final database stats
        db = Session(engine)
        try:
            total_items = db.query(ContentItem).count()
            items_with_thumbnails = db.query(ContentItem).filter(
                ContentItem.thumbnail_url.isnot(None)
            ).count()
            
            print(f"\n📊 Final Database Stats:")
            print(f"   Total items: {total_items}")
            print(f"   Items with thumbnails: {items_with_thumbnails}")
            if total_items > 0:
                thumbnail_percentage = (items_with_thumbnails / total_items) * 100
                print(f"   Overall thumbnail coverage: {thumbnail_percentage:.1f}%")
            
            # Show recent items by source
            print(f"\n📰 Recent Content Sources:")
            from sqlalchemy import text
            recent_sources = db.execute(text("""
                SELECT 
                    metadata->>'source_name' as source_name,
                    COUNT(*) as item_count,
                    COUNT(thumbnail_url) as thumbnail_count
                FROM content_items 
                WHERE created_at >= NOW() - INTERVAL '24 hours'
                AND metadata->>'source_name' IS NOT NULL
                GROUP BY metadata->>'source_name'
                ORDER BY item_count DESC
            """)).fetchall()
            
            for row in recent_sources:
                source_name, item_count, thumb_count = row
                print(f"   {source_name}: {item_count} items ({thumb_count} thumbnails)")
            
        finally:
            db.close()
        
        print(f"\n✅ Unified aggregation completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during aggregation: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        pass

if __name__ == "__main__":
    asyncio.run(main())