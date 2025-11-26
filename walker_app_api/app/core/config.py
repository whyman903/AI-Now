from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "AI-Now API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    PUBLIC_BASE_URL: Optional[str] = None
    ACCESS_TOKEN_AUDIENCE: str = "walker-app"
    ACCESS_TOKEN_ISSUER: Optional[str] = None
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    REFRESH_TOKEN_COOKIE_NAME: str = "walker_refresh_token"
    AUTH_COOKIE_DOMAIN: Optional[str] = None
    AUTH_COOKIE_SECURE: bool = True
    AUTH_COOKIE_SAMESITE: str = "none"
    AUTH_COOKIE_PATH: str = "/"
    AUTH_REFRESH_TOKEN_BYTES: int = 48
    JWT_SECRET_KEY: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    
    # Database
    DATABASE_URL: str
    DB_POOL_SIZE: int = 5  # Connection pool size
    DB_MAX_OVERFLOW: int = 10  # Max connections beyond pool_size
    DB_POOL_TIMEOUT: int = 30  # Seconds to wait for connection

    OPENAI_API_KEY: Optional[str] = None

    # CORS settings
    CORS_ORIGINS: str = "http://localhost:5173,https://ai-now.vercel.app,http://localhost:5174,http://localhost:5000,http://localhost:3000"
    
    XAI_API_KEY: Optional[str] = None
    TAVILY_API_KEY: Optional[str] = None
    
    # HTTP client settings
    HTTP_CLIENT_TIMEOUT: float = 30.0
    HTTP_CLIENT_USER_AGENT: str = "Mozilla/5.0 (compatible; ContentAggregator/1.0)"

    # Aggregation endpoint security
    AGGREGATION_SERVICE_TOKEN: Optional[str] = None
    AGGREGATION_SERVICE_TOKEN_NEXT: Optional[str] = None
    AGGREGATION_TOKEN_MIN_LENGTH: int = 32  # Minimum token length for security

    # Web scraping / Selenium configuration
    CHROME_BINARY_PATH: Optional[str] = None
    DISABLE_SELENIUM_AGENTS: bool = False
    
    # Content processing settings
    MAX_CONTENT_AGE_DAYS: int = 30
    CONTENT_FETCH_INTERVAL_HOURS: int = 12
    
    # Background task settings
    BACKGROUND_TASK_SHUTDOWN_TIMEOUT: float = 5.0

    # Analytics queue
    ANALYTICS_QUEUE_MAXSIZE: int = 5000
    ANALYTICS_QUEUE_BATCH_SIZE: int = 100
    ANALYTICS_QUEUE_FLUSH_SECONDS: float = 0.5
    
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


settings = Settings()
