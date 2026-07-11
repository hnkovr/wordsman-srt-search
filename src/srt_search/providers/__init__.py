"""Provider registry: known resources behind a common SearchProvider interface."""

from __future__ import annotations

from srt_search.config import Settings
from srt_search.providers.base import (
    ProviderError,
    ProviderNotImplementedError,
    SearchProvider,
    SubtitleNotFoundError,
)
from srt_search.providers.gestdown import GestdownProvider
from srt_search.providers.podnapisi import PodnapisiProvider
from srt_search.providers.yify import YifyProvider

REGISTRY: dict[str, type[SearchProvider]] = {
    PodnapisiProvider.name: PodnapisiProvider,
    YifyProvider.name: YifyProvider,
    GestdownProvider.name: GestdownProvider,
}


def make_provider(name: str, settings: Settings | None = None) -> SearchProvider:
    """Instantiate a registered provider; unknown names fail loud."""
    try:
        provider_cls = REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(REGISTRY))
        raise ValueError(f"unknown provider {name!r}; known providers: {known}") from None
    return provider_cls(settings)


__all__ = [
    "REGISTRY",
    "GestdownProvider",
    "PodnapisiProvider",
    "ProviderError",
    "ProviderNotImplementedError",
    "SearchProvider",
    "SubtitleNotFoundError",
    "YifyProvider",
    "make_provider",
]
