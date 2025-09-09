#!/usr/bin/env python3
"""
Standalone script to clear all content items from the database.
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Add the app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings

def clear_content_items():
    """Connects to the database and deletes all rows from the content_items table."""
    
    print("Connecting to the database...")
    if not settings.DATABASE_URL:
        print("❌ DATABASE_URL not configured.")
        return

    try:
        engine = create_engine(settings.DATABASE_URL)
        with Session(engine) as db:
            print("Deleting all items from content_items table...")
            
            # Use raw SQL for a simple and fast delete operation
            result = db.execute(text("DELETE FROM content_items;"))
            db.commit()
            
            print(f"✅ Successfully deleted {result.rowcount} items.")
            
    except Exception as e:
        print(f"❌ An error occurred: {e}")

if __name__ == "__main__":
    print("⚠️  This script will permanently delete all content from the database.")
    confirm = input("Are you sure you want to continue? (yes/no): ")
    if confirm.lower() == 'yes':
        clear_content_items()
    else:
        print("Operation cancelled.")
