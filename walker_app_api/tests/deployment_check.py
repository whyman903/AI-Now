#!/usr/bin/env python3
"""
Pre-deployment validation script.
Run this before deploying to catch configuration issues early.
"""
import os
import sys
from pathlib import Path

def check_env_vars():
    """Check critical environment variables."""
    print("🔍 Checking environment variables...")
    
    required_vars = {
        "DATABASE_URL": "Database connection string",
        "AGGREGATION_SERVICE_TOKEN": "Token for aggregation endpoints",
    }
    
    optional_vars = {
        "AGGREGATION_SERVICE_TOKEN_NEXT": "Secondary token for rotation",
        "CORS_ORIGINS": "Allowed CORS origins",
        "LOG_LEVEL": "Logging level",
        "SENTRY_DSN": "Sentry error tracking",
    }
    
    missing = []
    for var, desc in required_vars.items():
        value = os.getenv(var)
        if not value:
            missing.append(f"  ❌ {var}: {desc}")
        else:
            # Security checks
            if var == "AGGREGATION_SERVICE_TOKEN" and len(value) < 32:
                print(f"  ⚠️  {var}: Token is too short (minimum 32 chars)")
            elif var == "DATABASE_URL" and value.startswith("sqlite"):
                print(f"  ⚠️  {var}: Using SQLite (not recommended for production)")
            else:
                print(f"  ✅ {var}: Set")
    
    for var, desc in optional_vars.items():
        value = os.getenv(var)
        if value:
            print(f"  ✅ {var}: Set")
        else:
            print(f"  ℹ️  {var}: Not set ({desc})")
    
    if missing:
        print("\n❌ Missing required environment variables:")
        print("\n".join(missing))
        return False
    
    return True

def check_files():
    """Check required files exist."""
    print("\n🔍 Checking required files...")
    
    required_files = [
        "pyproject.toml",
        "alembic.ini",
        "alembic/env.py",
        ".env.example",
    ]
    
    missing = []
    for file_path in required_files:
        path = Path(file_path)
        if path.exists():
            print(f"  ✅ {file_path}")
        else:
            print(f"  ❌ {file_path}")
            missing.append(file_path)
    
    if missing:
        print(f"\n⚠️  Missing files: {', '.join(missing)}")
        return False
    
    return True

def check_database():
    """Check database connectivity."""
    print("\n🔍 Checking database connection...")
    
    try:
        from sqlalchemy import create_engine, text
        from app.core.config import settings
        
        engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("  ✅ Database connection successful")
        return True
    except Exception as e:
        print(f"  ❌ Database connection failed: {e}")
        return False

def check_migrations():
    """Check if migrations are up to date."""
    print("\n🔍 Checking database migrations...")
    
    try:
        import subprocess
        result = subprocess.run(
            ["alembic", "current"],
            capture_output=True,
            text=True,
            check=True
        )
        print(f"  ✅ Current migration: {result.stdout.strip()}")
        return True
    except Exception as e:
        print(f"  ⚠️  Could not check migrations: {e}")
        return False

def main():
    """Run all deployment checks."""
    print("=" * 60)
    print("🚀 Walker App - Deployment Readiness Check")
    print("=" * 60)
    
    checks = [
        check_env_vars(),
        check_files(),
        check_database(),
        check_migrations(),
    ]
    
    print("\n" + "=" * 60)
    if all(checks):
        print("✅ All checks passed! Ready for deployment.")
        print("=" * 60)
        return 0
    else:
        print("❌ Some checks failed. Please fix the issues above.")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
