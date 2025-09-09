from fastapi import FastAPI, WebSocket, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import logging
from starlette.websockets import WebSocketDisconnect
from sqlalchemy.orm import Session

from app.api.v1.api import api_router
from app.core.config import settings
from app.db.base import create_tables
from app.db.base import get_db
from jose import JWTError, jwt

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Content Aggregation API for TrendCurate",
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# CORS middleware for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:5000", "http://localhost:3000"],  # Add frontend URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
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

@app.on_event("startup")
async def startup_event():
    """Initialize database tables on startup"""
    logger.info("Creating database tables...")
    create_tables()
    logger.info("Content Aggregation API started successfully")

@app.websocket("/api/v1/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    # Verify JWT token for websocket
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=1008)
            return
        
        # Get user from database
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