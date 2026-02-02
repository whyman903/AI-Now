from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import models
from app.db.base import get_db
from app.schemas.preferences import (
    DisplayPreferencesResponse,
    DisplayPreferencesUpdateRequest,
    SourcePreferencePatchRequest,
    SourcePreferencesResponse,
    SourcePreferencesUpsertRequest,
    SourcePreferenceState,
    VALID_PALETTES,
)
from app.services.preference_service import PreferenceService, UnknownSourceError
from app.services.aggregation.registry import list_sources

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


# ----------------------
# Display Preferences
# ----------------------

@router.get(
    "/me/preferences/display",
    response_model=DisplayPreferencesResponse,
    summary="Get the current user's display preferences (tile colors, etc.)",
)
def read_display_preferences(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DisplayPreferencesResponse:
    display_pref = (
        db.query(models.UserDisplayPreference)
        .filter(models.UserDisplayPreference.user_id == current_user.id)
        .one_or_none()
    )
    if display_pref:
        return DisplayPreferencesResponse(tileColorPalette=display_pref.tile_color_palette)
    return DisplayPreferencesResponse(tileColorPalette="default")


@router.put(
    "/me/preferences/display",
    response_model=DisplayPreferencesResponse,
    summary="Update the current user's display preferences",
)
def update_display_preferences(
    payload: DisplayPreferencesUpdateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DisplayPreferencesResponse:
    palette = payload.tile_color_palette
    if palette not in VALID_PALETTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid palette '{palette}'. Valid options: {', '.join(VALID_PALETTES)}",
        )

    display_pref = (
        db.query(models.UserDisplayPreference)
        .filter(models.UserDisplayPreference.user_id == current_user.id)
        .one_or_none()
    )

    if display_pref:
        display_pref.tile_color_palette = palette
        display_pref.updated_at = datetime.now(timezone.utc)
    else:
        display_pref = models.UserDisplayPreference(
            user_id=current_user.id,
            tile_color_palette=palette,
        )
        db.add(display_pref)

    try:
        db.commit()
        logger.info("Display preferences updated for user %s: palette=%s", current_user.id, palette)
    except Exception as exc:
        db.rollback()
        logger.error("Failed to save display preferences: %s", exc)
        raise

    return DisplayPreferencesResponse(tileColorPalette=display_pref.tile_color_palette)
