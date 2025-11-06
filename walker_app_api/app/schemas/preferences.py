from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel, Field


class SourcePreferenceState(BaseModel):
    source_key: str = Field(alias="sourceKey")
    enabled: bool

    class Config:
        populate_by_name = True


class SourcePreferencesResponse(BaseModel):
    preferences: List[SourcePreferenceState]


class SourcePreferencesUpsertRequest(BaseModel):
    preferences: Dict[str, bool]


class SourcePreferencePatchRequest(BaseModel):
    enabled: bool
