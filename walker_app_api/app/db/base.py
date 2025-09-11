from sqlalchemy import create_engine, text, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Create all tables in the database"""
    from app.db.models import User, ContentItem, UserInteraction, BookmarkFolder, UserBookmark
    Base.metadata.create_all(bind=engine)


def ensure_content_items_compat_schema():
    """Ensure columns expected by the ORM exist in content_items."""
    try:
        with engine.begin() as conn:
            inspector = inspect(conn)
            cols = {c['name'] for c in inspector.get_columns('content_items')}

            if 'ai_summary' not in cols:
                try:
                    conn.execute(text("ALTER TABLE content_items ADD COLUMN ai_summary text"))
                except Exception:
                    pass

            if 'normalized_url' not in cols:
                try:
                    conn.execute(text("ALTER TABLE content_items ADD COLUMN normalized_url text"))
                except Exception:
                    pass

            if 'embedding' not in cols:
                try:
                    conn.execute(text("ALTER TABLE content_items ADD COLUMN embedding text"))
                except Exception:
                    pass

            try:
                if conn.dialect.name == 'postgresql':
                    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_content_items_normalized_url ON content_items(normalized_url) WHERE normalized_url IS NOT NULL"))
            except Exception:
                pass
    except Exception as e:
        print(f"WARN: ensure_content_items_compat_schema: {e}")
