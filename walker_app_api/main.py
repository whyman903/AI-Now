from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import logging
import httpx
from contextlib import asynccontextmanager
import sys
import json
from datetime import datetime

from app.api.v1.api import api_router
from app.core.config import settings


# Configure logging based on environment
class JSONFormatter(logging.Formatter):
    """Format logs as JSON for production"""
    def format(self, record):
        log_obj = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)


def setup_logging():
    """Configure logging based on settings"""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    
    handler = logging.StreamHandler(sys.stdout)
    
    if settings.LOG_FORMAT == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        )
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(handler)
    
    # Silence noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


setup_logging()
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Content Aggregation API starting...")
    
    # Initialize HTTP client
    app.state.http_client = httpx.AsyncClient(
        timeout=settings.HTTP_CLIENT_TIMEOUT,
        follow_redirects=True,
        headers={'User-Agent': settings.HTTP_CLIENT_USER_AGENT}
    )
    
    # Inject HTTP client into aggregator
    try:
        from app.services.content_aggregator import get_content_aggregator
        get_content_aggregator().set_http_client(app.state.http_client)
    except Exception as e:
        logger.warning(f"Unable to inject HTTP client into aggregator: {e}")

    # Track background tasks for proper shutdown
    app.state.background_tasks = set()
    
    # Trigger initial aggregation if database is empty
    try:
        from app.db.base import SessionLocal
        from app.db.models import ContentItem
        db = SessionLocal()
        try:
            count = db.query(ContentItem).count()
        finally:
            db.close()
        
        if count == 0:
            logger.info("No content found. Triggering initial aggregation in background...")
            agg = get_content_aggregator()
            import asyncio as _asyncio
            task = _asyncio.create_task(agg.aggregate_all_content())
            app.state.background_tasks.add(task)
            task.add_done_callback(app.state.background_tasks.discard)
    except Exception as e:
        logger.warning(f"Skipping initial aggregation trigger: {e}")
    
    logger.info("Content Aggregation API startup complete")
    
    yield
    
    # Shutdown: Cancel background tasks
    logger.info("Shutting down...")
    background_tasks = getattr(app.state, 'background_tasks', set())
    if background_tasks:
        logger.info(f"Cancelling {len(background_tasks)} background task(s)")
        for task in background_tasks:
            if not task.done():
                task.cancel()
        # Wait for cancellation with timeout
        import asyncio
        try:
            await asyncio.wait_for(
                asyncio.gather(*background_tasks, return_exceptions=True),
                timeout=settings.BACKGROUND_TASK_SHUTDOWN_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning(f"Background tasks did not complete within {settings.BACKGROUND_TASK_SHUTDOWN_TIMEOUT}s timeout")
    
    # Close HTTP client
    client = getattr(app.state, 'http_client', None)
    if client:
        try:
            await client.aclose()
            logger.info("HTTP client closed")
        except Exception as e:
            logger.error(f"Error closing HTTP client: {e}")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Content Aggregation API for AI-Now",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
def read_root():
    return {
        "message": "AI-Now Content Aggregation API",
        "status": "running",
        "version": settings.VERSION
    }

@app.get("/health")
async def health_check():
    """
    Health check endpoint that verifies critical services.
    
    Returns 200 if all critical services are operational,
    503 if database is down.
    """
    health_status = {
        "status": "healthy",
        "services": {
            "api": "up",
            "database": "unknown",
        }
    }
    
    # Check database
    try:
        from app.db.base import SessionLocal
        db = SessionLocal()
        try:
            db.execute("SELECT 1")
            health_status["services"]["database"] = "up"
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        health_status["services"]["database"] = "down"
        health_status["status"] = "unhealthy"
    
    status_code = 200 if health_status["status"] == "healthy" else 503
    
    from fastapi.responses import JSONResponse
    return JSONResponse(
        content=health_status,
        status_code=status_code
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.SERVER_HOST, port=settings.SERVER_PORT)
