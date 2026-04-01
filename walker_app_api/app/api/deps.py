"""Shared FastAPI dependencies for authentication."""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlparse

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_token
from app.db import models
from app.db.base import get_db

logger = logging.getLogger(__name__)

AGGREGATION_TOKEN_HEADER = "X-Aggregation-Token"
_bearer_scheme = HTTPBearer(auto_error=False)


def _valid_tokens() -> set[str]:
    """
    Collect valid aggregation tokens and validate them.
    
    Raises:
        ValueError: If any token is shorter than the minimum required length.
    """
    tokens: set[str] = set()
    primary: Optional[str] = settings.AGGREGATION_SERVICE_TOKEN
    secondary: Optional[str] = settings.AGGREGATION_SERVICE_TOKEN_NEXT
    
    min_length = settings.AGGREGATION_TOKEN_MIN_LENGTH
    
    if primary:
        if len(primary) < min_length:
            logger.error(f"Primary aggregation token is too short (minimum {min_length} characters)")
            raise ValueError(f"Primary token must be at least {min_length} characters")
        tokens.add(primary)
    if secondary:
        if len(secondary) < min_length:
            logger.error(f"Secondary aggregation token is too short (minimum {min_length} characters)")
            raise ValueError(f"Secondary token must be at least {min_length} characters")
        tokens.add(secondary)
    return tokens


def require_aggregation_token(request: Request) -> None:
    """
    Validate the aggregation token from request headers.
    
    Raises:
        HTTPException: 500 if tokens aren't configured, 401 if authentication fails.
    """
    try:
        tokens = _valid_tokens()
    except ValueError as e:
        logger.error(f"Token validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Aggregation token configuration error",
        )
    
    if not tokens:
        logger.error("Aggregation service token is not configured.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Aggregation token not configured",
        )

    provided = request.headers.get(AGGREGATION_TOKEN_HEADER)
    if not provided or provided not in tokens:
        # Use same error message for missing and invalid to prevent enumeration
        logger.warning(f"Aggregation authentication failed from {request.client.host if request.client else 'unknown'}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
        )


def require_analytics_origin(request: Request) -> None:
    """Reject analytics requests that don't originate from an allowed frontend origin."""
    allowed = set(settings.cors_origins_list)

    origin = request.headers.get("origin")
    if origin and origin in allowed:
        return

    referer = request.headers.get("referer")
    if referer:
        parsed = urlparse(referer)
        referer_origin = f"{parsed.scheme}://{parsed.netloc}"
        if referer_origin in allowed:
            return

    raise HTTPException(status_code=403, detail="Forbidden")


def _resolve_user(
    credentials: Optional[HTTPAuthorizationCredentials],
    db: Session,
) -> Optional[models.User]:
    if not credentials:
        return None
    token = credentials.credentials
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        ) from None

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token payload.",
        )

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive.",
        )
    return user


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    user = _resolve_user(credentials, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )
    return user


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> Optional[models.User]:
    if not credentials:
        return None
    return _resolve_user(credentials, db)


__all__ = [
    "AGGREGATION_TOKEN_HEADER",
    "require_aggregation_token",
    "require_analytics_origin",
    "get_current_user",
    "get_optional_user",
]
