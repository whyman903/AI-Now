from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    refresh_token_expiry,
    verify_password,
)
from app.db import models


@dataclass(frozen=True)
class TokenBundle:
    access_token: str
    access_token_expires_at: datetime
    refresh_token: str
    refresh_token_expires_at: datetime


class AuthError(Exception):
    """Base class for auth-related errors."""


class InvalidCredentialsError(AuthError):
    """Raised when user credentials are invalid."""


class InactiveUserError(AuthError):
    """Raised when an inactive user attempts to authenticate."""


class AuthService:
    """Encapsulates user registration, authentication, and session management."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _normalize_email(self, email: str) -> str:
        normalized = email.strip().lower()
        if not normalized:
            raise ValueError("Email must not be empty.")
        return normalized

    def _get_user_by_email(self, email: str) -> Optional[models.User]:
        normalized = self._normalize_email(email)
        return (
            self.db.query(models.User)
            .filter(func.lower(models.User.email) == normalized)
            .one_or_none()
        )

    def register_user(self, email: str, password: str, display_name: Optional[str] = None) -> models.User:
        normalized_email = self._normalize_email(email)

        existing = self.db.query(models.User).filter(func.lower(models.User.email) == normalized_email).first()
        if existing:
            raise AuthError("A user with that email already exists.")

        password_hash = hash_password(password)
        user = models.User(
            email=normalized_email,
            display_name=display_name,
            password_hash=password_hash,
            auth_provider="local",
            is_active=True,
        )
        self.db.add(user)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise AuthError("A user with that email already exists.") from exc
        return user

    def authenticate_local_user(self, email: str, password: str) -> models.User:
        user = self._get_user_by_email(email)
        if not user:
            raise InvalidCredentialsError("Invalid email or password.")
        if user.auth_provider != "local" or not user.password_hash:
            raise InvalidCredentialsError("Invalid email or password.")
        if not user.is_active:
            raise InactiveUserError("User account is inactive.")
        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("Invalid email or password.")
        return user

    def issue_tokens(
        self,
        user: models.User,
        *,
        user_agent: Optional[str],
        ip_address: Optional[str],
    ) -> TokenBundle:
        aware_now = datetime.now(timezone.utc)
        now_naive = aware_now.replace(tzinfo=None)
        access_token, access_expires = create_access_token(str(user.id))

        refresh_token = generate_refresh_token()
        refresh_expires_aware = refresh_token_expiry(aware_now)
        refresh_expires_naive = refresh_expires_aware.replace(tzinfo=None)
        refresh_hash = hash_refresh_token(refresh_token)

        token_model = models.UserRefreshToken(
            user_id=user.id,
            token_hash=refresh_hash,
            issued_at=now_naive,
            expires_at=refresh_expires_naive,
            last_used_at=now_naive,
            user_agent=(user_agent or "")[:512] or None,
            ip_address=(ip_address or "")[:64] or None,
        )

        self.db.add(token_model)
        try:
            self.db.flush()
        except IntegrityError as exc:  # pragma: no cover - defensive unique constraint check
            self.db.rollback()
            raise AuthError("Unable to create session token.") from exc

        user.last_login_at = now_naive
        self.db.add(user)

        return TokenBundle(
            access_token=access_token,
            access_token_expires_at=access_expires,
            refresh_token=refresh_token,
            refresh_token_expires_at=refresh_expires_aware,
        )

    def get_refresh_token(self, refresh_token: str) -> Tuple[models.User, models.UserRefreshToken]:
        refresh_hash = hash_refresh_token(refresh_token)
        token_model = (
            self.db.query(models.UserRefreshToken)
            .filter(models.UserRefreshToken.token_hash == refresh_hash)
            .first()
        )
        if not token_model:
            raise InvalidCredentialsError("Invalid refresh token.")
        if token_model.revoked_at is not None:
            raise InvalidCredentialsError("Refresh token has been revoked.")

        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        if token_model.expires_at and token_model.expires_at <= now_naive:
            raise InvalidCredentialsError("Refresh token has expired.")

        user = self.db.query(models.User).filter(models.User.id == token_model.user_id).first()
        if not user or not user.is_active:
            raise InvalidCredentialsError("Invalid refresh token.")

        return user, token_model

    def rotate_refresh_token(
        self,
        existing_token: models.UserRefreshToken,
        *,
        user_agent: Optional[str],
        ip_address: Optional[str],
    ) -> TokenBundle:
        """Rotate refresh token as part of a token refresh request."""
        aware_now = datetime.now(timezone.utc)
        now_naive = aware_now.replace(tzinfo=None)
        existing_token.revoked_at = now_naive
        existing_token.last_used_at = now_naive
        self.db.add(existing_token)

        user = self.db.query(models.User).filter(models.User.id == existing_token.user_id).first()
        if not user:
            raise InvalidCredentialsError("Invalid refresh token.")

        return self.issue_tokens(user, user_agent=user_agent, ip_address=ip_address)

    def revoke_refresh_token(self, refresh_token: str) -> None:
        refresh_hash = hash_refresh_token(refresh_token)
        token_model = (
            self.db.query(models.UserRefreshToken)
            .filter(models.UserRefreshToken.token_hash == refresh_hash)
            .first()
        )
        if not token_model:
            return

        token_model.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.db.add(token_model)

    def revoke_all_user_tokens(self, user_id: str) -> int:
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        tokens = (
            self.db.query(models.UserRefreshToken)
            .filter(
                models.UserRefreshToken.user_id == user_id,
                models.UserRefreshToken.revoked_at.is_(None),
            )
            .all()
        )
        for token in tokens:
            token.revoked_at = now_naive
            self.db.add(token)
        return len(tokens)
