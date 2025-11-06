from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import models
from app.db.base import get_db
from app.schemas.preferences import (
    SourcePreferencePatchRequest,
    SourcePreferencesResponse,
    SourcePreferencesUpsertRequest,
    SourcePreferenceState,
)
from app.services.preference_service import PreferenceService, UnknownSourceError
from app.services.source_registry import list_sources

logger = logging.getLogger(__name__)
router = APIRouter()


def _serialize_preferences(preference_map: dict[str, bool]) -> SourcePreferencesResponse:
    preferences = [
        SourcePreferenceState(sourceKey=definition.key, enabled=preference_map.get(definition.key, definition.default_enabled))
        for definition in list_sources()
    ]
    return SourcePreferencesResponse(preferences=preferences)


@router.get(
    "/me/preferences/sources",
    response_model=SourcePreferencesResponse,
    summary="List the current user's source preferences",
)
def read_source_preferences(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SourcePreferencesResponse:
    service = PreferenceService(db)
    preferences = service.list_preferences(str(current_user.id))
    return _serialize_preferences(preferences)


@router.put(
    "/me/preferences/sources",
    response_model=SourcePreferencesResponse,
    summary="Replace the current user's source preferences",
)
def upsert_source_preferences(
    payload: SourcePreferencesUpsertRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SourcePreferencesResponse:
    enabled_count = sum(1 for v in payload.preferences.values() if v)
    logger.info(
        "Saving preferences for user %s: %s/%s sources enabled",
        current_user.id,
        enabled_count,
        len(payload.preferences),
    )
    logger.debug("Preferences data: %s", payload.preferences)
    
    service = PreferenceService(db)
    try:
        preferences = service.replace_preferences(str(current_user.id), payload.preferences)
        db.commit()
        logger.info("Preferences saved successfully for user %s", current_user.id)
    except UnknownSourceError as exc:
        logger.error("Unknown source error: %s", exc)
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Error saving preferences: %s", exc)
        db.rollback()
        raise
    
    return _serialize_preferences(preferences)


@router.patch(
    "/me/preferences/sources/{source_key}",
    response_model=SourcePreferencesResponse,
    summary="Update a single source preference",
)
def patch_source_preference(
    source_key: str,
    payload: SourcePreferencePatchRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SourcePreferencesResponse:
    service = PreferenceService(db)
    try:
        preferences = service.update_single_preference(str(current_user.id), source_key, payload.enabled)
        db.commit()
    except UnknownSourceError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _serialize_preferences(preferences)
