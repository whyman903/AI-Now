from sqlalchemy import create_engine, text, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import make_url
from app.core.config import settings
import socket


def _log_db_dns_info():
    """Best-effort logging of DB hostname and DNS resolution.

    Does not raise; only prints helpful diagnostics once at import time.
    """
    try:
        url = make_url(settings.DATABASE_URL)
    except Exception as e:  # pragma: no cover - defensive
        print(f"DB-CONFIG: Unable to parse DATABASE_URL: {e}")
        return

    # Only meaningful for networked DBs like Postgres
    if not url.host or not url.drivername.startswith("postgresql"):
        print("DB-CONFIG: Non-network DB or no host; skipping DNS check.")
        return

    host = url.host
    port = url.port or 5432
    print(f"DB-CONFIG: Using DB host '{host}' on port {port} (driver={url.drivername}).")

    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        addrs = sorted({ai[4][0] for ai in infos})
        if addrs:
            print(f"DB-CONFIG: Host resolves to: {', '.join(addrs)}")
        else:
            print("DB-CONFIG: DNS returned no addresses.")
    except Exception as e:
        print(f"DB-CONFIG: DNS resolution failed for '{host}': {e}")


_log_db_dns_info()

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=3600,  # Recycle connections after 1 hour
)
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
    from app.db import models  # Ensure model metadata is registered

    Base.metadata.create_all(bind=engine)
    _drop_legacy_user_tables()


def _drop_legacy_user_tables() -> None:
    """Remove legacy user-centric tables that are no longer required."""
    legacy_tables = [
        "user_bookmarks",
        "bookmark_folders",
        "user_interactions",
        "users",
    ]

    try:
        with engine.begin() as conn:
            existing = set(inspect(conn).get_table_names())
            for table in legacy_tables:
                if table not in existing:
                    continue
                if conn.dialect.name == "postgresql":
                    conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                else:
                    conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
    except Exception as exc:
        print(f"WARN: unable to drop legacy user tables: {exc}")


def ensure_content_items_compat_schema():
    """Ensure columns expected by the ORM exist in content_items."""
    try:
        with engine.begin() as conn:
            inspector = inspect(conn)
            cols = {c['name'] for c in inspector.get_columns('content_items')}

            # Ensure new lean columns exist
            if 'url' not in cols:
                try:
                    conn.execute(text("ALTER TABLE content_items ADD COLUMN url text"))
                except Exception:
                    pass
                try:
                    # Backfill from legacy source_url if present
                    legacy_cols = {c['name'] for c in inspector.get_columns('content_items')}
                    if 'source_url' in legacy_cols:
                        conn.execute(text("UPDATE content_items SET url = source_url WHERE url IS NULL"))
                except Exception:
                    pass

            if 'clicks' not in cols:
                try:
                    conn.execute(text("ALTER TABLE content_items ADD COLUMN clicks integer DEFAULT 0 NOT NULL"))
                except Exception:
                    pass

            try:
                if conn.dialect.name == 'postgresql':
                    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_content_items_url ON content_items(url) WHERE url IS NOT NULL"))
            except Exception:
                pass
    except Exception as e:
        print(f"WARN: ensure_content_items_compat_schema: {e}")
