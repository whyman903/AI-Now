"""Security helpers for hashing credentials and issuing tokens."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
import hashlib
import hmac
import secrets

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash

from app.core.config import settings

PasswordHasherType = PasswordHasher

_password_hasher: PasswordHasherType = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,
    parallelism=2,
    hash_len=32,
)


def hash_password(password: str) -> str:
    """Hash a password using Argon2id."""
    if not password:
        raise ValueError("Password must not be empty.")
    return _password_hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against the stored Argon2 hash."""
    if not password or not hashed:
        return False
    try:
        return _password_hasher.verify(hashed, password)
    except (VerifyMismatchError, InvalidHash):
        return False
    except Exception:
        return False


def create_access_token(
    subject: str,
    expires_delta: Optional[timedelta] = None,
    additional_claims: Optional[Dict[str, Any]] = None,
) -> Tuple[str, datetime]:
    """Create a signed JWT access token."""
    now = datetime.now(timezone.utc)
    expires = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))

    payload: Dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "aud": settings.ACCESS_TOKEN_AUDIENCE,
    }
    if settings.ACCESS_TOKEN_ISSUER:
        payload["iss"] = settings.ACCESS_TOKEN_ISSUER
    if additional_claims:
        payload.update(additional_claims)

    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, expires


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and validate an access token."""
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        audience=settings.ACCESS_TOKEN_AUDIENCE,
        issuer=settings.ACCESS_TOKEN_ISSUER,
        options={"require": ["exp", "iat", "nbf", "sub"]},
    )


def generate_refresh_token() -> str:
    """Generate a secure refresh token string."""
    return secrets.token_urlsafe(settings.AUTH_REFRESH_TOKEN_BYTES)


def hash_refresh_token(token: str) -> str:
    """Hash refresh tokens before persistence."""
    secret = settings.JWT_SECRET_KEY.encode("utf-8")
    digest = hmac.new(secret, token.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest


def refresh_token_expiry(now: Optional[datetime] = None) -> datetime:
    """Compute the refresh token expiry timestamp."""
    now = now or datetime.now(timezone.utc)
    return now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)


def constant_time_equals(val1: str, val2: str) -> bool:
    """Constant-time comparison helper."""
    return hmac.compare_digest(val1, val2)
