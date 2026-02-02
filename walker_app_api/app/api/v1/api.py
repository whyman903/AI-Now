from fastapi import APIRouter
from app.api.v1.endpoints import aggregation, analytics, auth, content, items, sources, users

api_router = APIRouter()
api_router.include_router(content.router, prefix="/content", tags=["content"])
api_router.include_router(items.router, prefix="/sources", tags=["sources"])
api_router.include_router(sources.router, prefix="/sources/user", tags=["user-sources"])
api_router.include_router(aggregation.router, prefix="/aggregation", tags=["aggregation"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
