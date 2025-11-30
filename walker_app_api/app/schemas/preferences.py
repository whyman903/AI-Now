from __future__ import annotations

from typing import Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field


class SourcePreferenceState(BaseModel):
    source_key: str = Field(alias="sourceKey")
    enabled: bool

    model_config = ConfigDict(populate_by_name=True)


class SourcePreferencesResponse(BaseModel):
    preferences: List[SourcePreferenceState]


class SourcePreferencesUpsertRequest(BaseModel):
    preferences: Dict[str, bool]


class SourcePreferencePatchRequest(BaseModel):
    enabled: bool


# Valid color palette options
TileColorPalette = Literal[
    "default",        # Current blue/green/purple scheme
    "ocean",          # Teal/cyan/deep blue tones
    "sunset",         # Warm orange/coral/magenta tones
    "forest",         # Deep green/moss/olive tones
    "monochrome",     # Grayscale/neutral tones
    "earth",          # Brown/tan/terracotta tones
    "colorblindSafe", # Blue/orange optimized for color vision deficiency
    "highContrast",   # Maximum luminance contrast for visual accessibility
]

VALID_PALETTES: List[str] = [
    "default",
    "ocean",
    "sunset",
    "forest",
    "monochrome",
    "earth",
    "colorblindSafe",
    "highContrast",
]


class DisplayPreferencesResponse(BaseModel):
    tile_color_palette: str = Field(alias="tileColorPalette", default="default")

    model_config = ConfigDict(populate_by_name=True)


class DisplayPreferencesUpdateRequest(BaseModel):
    tile_color_palette: str = Field(alias="tileColorPalette")

    model_config = ConfigDict(populate_by_name=True)
