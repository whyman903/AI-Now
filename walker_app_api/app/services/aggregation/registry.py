from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


@dataclass(frozen=True)
class PluginSource:
    key: str
    name: str
    category: str
    content_types: List[str]
    scrape_func: Callable
    requires_selenium: bool = False
    default_enabled: bool = True


_REGISTRY: Dict[str, PluginSource] = {}


def register(
    *,
    key: str,
    name: str,
    category: str,
    content_types: List[str],
    requires_selenium: bool = False,
):
    def decorator(func: Callable) -> Callable:
        _REGISTRY[key] = PluginSource(
            key=key,
            name=name,
            category=category,
            content_types=content_types,
            scrape_func=func,
            requires_selenium=requires_selenium,
        )
        return func

    return decorator


def get_all_plugins() -> List[PluginSource]:
    return list(_REGISTRY.values())


def get_plugin(key: str) -> Optional[PluginSource]:
    return _REGISTRY.get(key)


def get_selenium_plugins() -> List[PluginSource]:
    return [p for p in _REGISTRY.values() if p.requires_selenium]


def get_non_selenium_plugins() -> List[PluginSource]:
    return [p for p in _REGISTRY.values() if not p.requires_selenium]


# Aliases used by the preference service and content endpoints
SourceDefinition = PluginSource
SOURCES_BY_KEY: Dict[str, PluginSource] = _REGISTRY


def list_sources() -> List[PluginSource]:
    return get_all_plugins()
