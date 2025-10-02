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
    DB_POOL_SIZE: int = 5  # Connection pool size
    DB_MAX_OVERFLOW: int = 10  # Max connections beyond pool_size
    DB_POOL_TIMEOUT: int = 30  # Seconds to wait for connection

    OPENAI_API_KEY: Optional[str] = None

    # CORS settings
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:5174,http://localhost:5000,http://localhost:3000"
    
    # HTTP client settings
    HTTP_CLIENT_TIMEOUT: float = 30.0
    HTTP_CLIENT_USER_AGENT: str = "Mozilla/5.0 (compatible; ContentAggregator/1.0)"

    # Aggregation endpoint security
    AGGREGATION_SERVICE_TOKEN: Optional[str] = None
    AGGREGATION_SERVICE_TOKEN_NEXT: Optional[str] = None
    AGGREGATION_TOKEN_MIN_LENGTH: int = 32  # Minimum token length for security
    
    # Content processing settings
    MAX_CONTENT_AGE_DAYS: int = 30
    CONTENT_FETCH_INTERVAL_HOURS: int = 12
    
    # Background task settings
    BACKGROUND_TASK_SHUTDOWN_TIMEOUT: float = 5.0
    
    # Server settings (for direct uvicorn run)
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000
    
    # Logging
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_FORMAT: str = "json"  # json or text
    
    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS_ORIGINS string into list"""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
    
    class Config:
        env_file = ".env"


settings = Settings()
