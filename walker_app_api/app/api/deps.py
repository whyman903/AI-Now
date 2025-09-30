"""Shared FastAPI dependencies for authentication."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException, Request, status

from app.core.config import settings

logger = logging.getLogger(__name__)

AGGREGATION_TOKEN_HEADER = "X-Aggregation-Token"


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


__all__ = [
    "AGGREGATION_TOKEN_HEADER",
    "require_aggregation_token",
]
