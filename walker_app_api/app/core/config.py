from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    PROJECT_NAME: str = "FeedCurator API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    PUBLIC_BASE_URL: Optional[str] = None
    
    # Database
    DATABASE_URL: str
    SECRET_KEY: str
    
    # API Keys - only the ones we actually use
    OPENAI_API_KEY: Optional[str] = None
    
    # Redis for caching and queues
    REDIS_URL: str = "redis://localhost:6379"
    
    # Content processing settings
    MAX_CONTENT_AGE_DAYS: int = 30
    CONTENT_FETCH_INTERVAL_HOURS: int = 6
    
    class Config:
        env_file = ".env"


settings = Settings()
