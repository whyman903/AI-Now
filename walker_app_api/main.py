from fastapi import FastAPI, WebSocket, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import logging
from starlette.websockets import WebSocketDisconnect
from sqlalchemy.orm import Session
import httpx
from contextlib import asynccontextmanager

from app.api.v1.api import api_router
from app.core.config import settings
from app.db.base import get_db
from jose import JWTError, jwt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Content Aggregation API started successfully")
    
    app.state.http_client = httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers={'User-Agent': 'Mozilla/5.0 (compatible; ContentAggregator/1.0)'}
    )
    try:
        from app.services.content_aggregator import get_content_aggregator
        get_content_aggregator().set_http_client(app.state.http_client)
    except Exception as e:
        logger.warning(f"Unable to inject HTTP client into aggregator: {e}")

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
            _asyncio.create_task(agg.aggregate_all_content())
    except Exception as e:
        logger.warning(f"Skipping initial aggregation trigger: {e}")
    
    yield
    
    client = getattr(app.state, 'http_client', None)
    if client:
        try:
            await client.aclose()
        except Exception:
            pass

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Content Aggregation API for TrendCurate",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:5000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
def read_root():
    return {
        "message": "TrendCurate Content Aggregation API",
        "status": "running",
        "version": settings.VERSION
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.websocket("/api/v1/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=1008)
            return
        
        from app.db.models import User
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            await websocket.close(code=1008)
            return
    except JWTError:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Message text was: {data}")
    except WebSocketDisconnect:
        pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
