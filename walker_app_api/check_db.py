
"""
Check existing database tables
"""
from sqlalchemy import inspect, text
from app.db.base import engine

def check_tables():
    """Check existing tables in database"""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    print("Existing tables:")
    for table in tables:
        print(f"  - {table}")
        
        # Get columns for each table
        columns = inspector.get_columns(table)
        for col in columns:
            print(f"    {col['name']}: {col['type']}")
        print()
    
    return tables

def drop_all_tables():
    """Drop all tables - BE CAREFUL!"""
    with engine.connect() as conn:
        # Drop all tables in reverse dependency order
        tables_to_drop = [
            "content_items",
            "feed_states",
        ]
        
        for table in tables_to_drop:
            try:
                conn.execute(text(f'DROP TABLE IF EXISTS {table} CASCADE'))
                print(f"Dropped table: {table}")
            except Exception as e:
                print(f"Error dropping {table}: {e}")
        
        conn.commit()

if __name__ == "__main__":
    print("Checking database tables...")
    tables = check_tables()
    
    if tables:
        response = input("\nDo you want to drop all existing tables? (yes/no): ")
        if response.lower() == 'yes':
            drop_all_tables()
            print("\nAll tables dropped.")
    else:
        print("No tables found.")
