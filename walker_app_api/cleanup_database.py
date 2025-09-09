#!/usr/bin/env python3
"""
Database cleanup script to remove test data and irrelevant content.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.base import get_db
from app.db.models import ContentItem
from sqlalchemy import or_, and_

def cleanup_test_data():
    """Remove test data and irrelevant content from database"""
    
    db = next(get_db())
    try:
        print("Starting database cleanup...")
        
        # Count items before cleanup
        total_before = db.query(ContentItem).count()
        print(f"Total items before cleanup: {total_before}")
        
        # 1. Remove items with unknown source (likely test data)
        unknown_source_items = []
        all_items = db.query(ContentItem).all()
        
        for item in all_items:
            if (item.meta_data is None or 
                'source' not in item.meta_data or 
                item.meta_data.get('source') == 'unknown'):
                unknown_source_items.append(item)
        
        print(f"Removing {len(unknown_source_items)} items with unknown/missing source...")
        for item in unknown_source_items:
            db.delete(item)
        
        # 2. Remove items with test patterns in title or content
        test_patterns = ['sample', 'test', 'example', 'demo', 'lorem ipsum', 'placeholder']
        test_items = []
        
        all_items = db.query(ContentItem).all()
        for item in all_items:
            title_lower = item.title.lower() if item.title else ''
            content_lower = item.content.lower() if item.content else ''
            
            # Check for test patterns
            for pattern in test_patterns:
                if (pattern in title_lower or pattern in content_lower):
                    # Skip if it's legitimate content that happens to contain these words
                    # (e.g., research papers about "demo" applications)
                    if pattern == 'demo' and item.meta_data and item.meta_data.get('source') == 'arxiv':
                        continue  # Keep arXiv papers that mention demo
                    test_items.append(item)
                    break
        
        print(f"Removing {len(test_items)} items with test patterns...")
        for item in test_items:
            db.delete(item)
        
        # 3. Remove items with obviously fake URLs
        fake_url_patterns = [
            'youtube.com/watch?v=sample',
            'example.com',
            'test.com',
            'placeholder.com'
        ]
        
        fake_url_items = []
        remaining_items = db.query(ContentItem).all()
        for item in remaining_items:
            if item.source_url:
                for pattern in fake_url_patterns:
                    if pattern in item.source_url:
                        fake_url_items.append(item)
                        break
        
        print(f"Removing {len(fake_url_items)} items with fake URLs...")
        for item in fake_url_items:
            db.delete(item)
        
        # 4. Remove duplicates (same source_url)
        print("Removing duplicate items...")
        duplicates_removed = 0
        
        # Find all unique source URLs
        unique_urls = set()
        all_remaining = db.query(ContentItem).all()
        
        for item in all_remaining:
            if item.source_url in unique_urls:
                db.delete(item)
                duplicates_removed += 1
            else:
                unique_urls.add(item.source_url)
        
        print(f"Removed {duplicates_removed} duplicate items")
        
        # Commit all changes
        db.commit()
        
        # Count items after cleanup  
        total_after = db.query(ContentItem).count()
        removed_count = total_before - total_after
        
        print(f"\nCleanup complete!")
        print(f"Items before: {total_before}")
        print(f"Items after: {total_after}")
        print(f"Items removed: {removed_count}")
        
        # Show remaining content by source
        print(f"\nRemaining content by source:")
        from collections import Counter
        sources = Counter()
        remaining_items = db.query(ContentItem).all()
        for item in remaining_items:
            if item.meta_data and 'source' in item.meta_data:
                sources[item.meta_data['source']] += 1
            else:
                sources['unknown'] += 1
        
        for source, count in sources.items():
            print(f"  {source}: {count} items")
            
    except Exception as e:
        print(f"Error during cleanup: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    cleanup_test_data()