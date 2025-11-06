from __future__ import annotations

from typing import Dict, Iterable
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db import models
from app.services.source_registry import SourceDefinition, SOURCES_BY_KEY, list_sources


class UnknownSourceError(ValueError):
    """Raised when an invalid source key is provided."""


class PreferenceService:
    """Manage per-user source preferences."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_preferences(self, user_id: str) -> Dict[str, bool]:
        defaults = {definition.key: definition.default_enabled for definition in list_sources()}
        rows = (
            self.db.query(models.UserSourcePreference)
            .filter(models.UserSourcePreference.user_id == user_id)
            .all()
        )
        for row in rows:
            defaults[row.source_key] = bool(row.enabled)
        return defaults

    def replace_preferences(self, user_id: str, desired: Dict[str, bool]) -> Dict[str, bool]:
        self._validate_keys(desired.keys())

        query = self.db.query(models.UserSourcePreference).filter(models.UserSourcePreference.user_id == user_id)
        if self._supports_for_update():
            query = query.with_for_update()

        existing_rows = {row.source_key: row for row in query.all()}

        now = datetime.now(timezone.utc)
        result: Dict[str, bool] = {}

        for definition in list_sources():
            target_state = desired.get(definition.key, definition.default_enabled)
            result[definition.key] = target_state

            existing = existing_rows.get(definition.key)
            if target_state == definition.default_enabled:
                if existing:
                    self.db.delete(existing)
                continue

            if existing:
                existing.enabled = target_state
                existing.updated_at = now
                self.db.add(existing)
            else:
                self.db.add(
                    models.UserSourcePreference(
                        user_id=user_id,
                        source_key=definition.key,
                        enabled=target_state,
                    )
                )

        # Remove preferences that refer to unknown sources (defensive cleanup)
        for key, row in existing_rows.items():
            if key not in result:
                self.db.delete(row)

        return result

    def update_single_preference(self, user_id: str, source_key: str, enabled: bool) -> Dict[str, bool]:
        if source_key not in SOURCES_BY_KEY:
            raise UnknownSourceError(f"Unknown source key '{source_key}'")

        definition: SourceDefinition = SOURCES_BY_KEY[source_key]
        target_state = bool(enabled)

        existing = (
            self.db.query(models.UserSourcePreference)
            .filter(
                models.UserSourcePreference.user_id == user_id,
                models.UserSourcePreference.source_key == source_key,
            )
            .one_or_none()
        )

        if target_state == definition.default_enabled:
            if existing:
                self.db.delete(existing)
        else:
            if existing:
                existing.enabled = target_state
                existing.updated_at = datetime.now(timezone.utc)
                self.db.add(existing)
            else:
                self.db.add(
                    models.UserSourcePreference(
                        user_id=user_id,
                        source_key=source_key,
                        enabled=target_state,
                    )
                )

        return self.list_preferences(user_id)

    def _validate_keys(self, keys: Iterable[str]) -> None:
        for key in keys:
            if key not in SOURCES_BY_KEY:
                raise UnknownSourceError(f"Unknown source key '{key}'")

    def _supports_for_update(self) -> bool:
        bind = self.db.get_bind()
        if not bind:
            return False
        return bind.dialect.name != "sqlite"
