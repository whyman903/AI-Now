from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_optional_user
from app.core.config import settings
from app.db.base import get_db
from app.db import models
from app.schemas.auth import LogoutResponse, RefreshResponse, TokenResponse
from app.schemas.user import SessionResponse, UserCreateRequest, UserLoginRequest, UserPublic
from app.services.auth_service import AuthError, AuthService, InactiveUserError, InvalidCredentialsError

router = APIRouter()


def _samesite() -> str:
    value = (settings.AUTH_COOKIE_SAMESITE or "lax").lower()
    if value not in {"lax", "strict", "none"}:
        value = "lax"
    return value.capitalize()


def _set_refresh_cookie(response: Response, token: str, expires_at: datetime) -> None:
    response.set_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=bool(settings.AUTH_COOKIE_SECURE),
        samesite=_samesite(),
        domain=settings.AUTH_COOKIE_DOMAIN,
        path=settings.AUTH_COOKIE_PATH,
        expires=int(expires_at.timestamp()),
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        domain=settings.AUTH_COOKIE_DOMAIN,
        path=settings.AUTH_COOKIE_PATH,
    )


def _build_token_response(user: models.User, bundle, response: Response) -> TokenResponse:
    _set_refresh_cookie(response, bundle.refresh_token, bundle.refresh_token_expires_at)
    now = datetime.now(timezone.utc)
    expires_in = max(0, int((bundle.access_token_expires_at - now).total_seconds()))
    return TokenResponse(
        access_token=bundle.access_token,
        expires_in=expires_in,
        user=UserPublic.model_validate(user),
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user with email and password",
)
def register_user(
    payload: UserCreateRequest,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    service = AuthService(db)
    try:
        user = service.register_user(payload.email, payload.password, payload.display_name)
        bundle = service.issue_tokens(
            user,
            user_agent=request.headers.get("user-agent"),
            ip_address=(request.client.host if request.client else None),
        )
        db.commit()
        db.refresh(user)
    except AuthError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _build_token_response(user, bundle, response)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate with email and password",
)
def login_user(
    payload: UserLoginRequest,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    service = AuthService(db)
    try:
        user = service.authenticate_local_user(payload.email, payload.password)
        bundle = service.issue_tokens(
            user,
            user_agent=request.headers.get("user-agent"),
            ip_address=(request.client.host if request.client else None),
        )
        db.commit()
        db.refresh(user)
    except InvalidCredentialsError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except InactiveUserError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return _build_token_response(user, bundle, response)


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    summary="Rotate refresh token and issue a new access token",
)
def refresh_token(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> RefreshResponse:
    raw_token = request.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token missing.")

    service = AuthService(db)
    try:
        user, existing_token = service.get_refresh_token(raw_token)
        bundle = service.rotate_refresh_token(
            existing_token,
            user_agent=request.headers.get("user-agent"),
            ip_address=(request.client.host if request.client else None),
        )
        db.commit()
        db.refresh(user)
    except (InvalidCredentialsError, InactiveUserError) as exc:
        db.rollback()
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    _set_refresh_cookie(response, bundle.refresh_token, bundle.refresh_token_expires_at)
    now = datetime.now(timezone.utc)
    expires_in = max(0, int((bundle.access_token_expires_at - now).total_seconds()))
    return RefreshResponse(
        access_token=bundle.access_token,
        expires_in=expires_in,
    )


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Revoke refresh token and clear cookie",
)
def logout_user(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LogoutResponse:
    raw_token = request.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)
    if raw_token:
        service = AuthService(db)
        service.revoke_refresh_token(raw_token)
        db.commit()
    _clear_refresh_cookie(response)
    return LogoutResponse()


@router.get(
    "/session",
    response_model=SessionResponse,
    summary="Return the current authenticated user, if any",
)
def read_session(
    user: models.User | None = Depends(get_optional_user),
) -> SessionResponse:
    if not user:
        return SessionResponse(user=None)
    return SessionResponse(user=UserPublic.model_validate(user))
