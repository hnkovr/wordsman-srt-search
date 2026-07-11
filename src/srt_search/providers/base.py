"""Provider interface and error taxonomy."""

from __future__ import annotations

from abc import ABC, abstractmethod

from srt_search.models import SearchCandidate


class ProviderError(RuntimeError):
    """Upstream subtitle resource failed or returned an unexpected payload."""


class ProviderNotImplementedError(ProviderError):
    """Provider is a declared stub — implementation tracked in the backlog."""


class SubtitleNotFoundError(ProviderError):
    """No subtitle matched the query."""


class SearchProvider(ABC):
    name: str = "base"
    implemented: bool = True

    @abstractmethod
    async def search(
        self, movie: str, year: int | None = None, limit: int = 10
    ) -> list[SearchCandidate]:
        """Return candidates for a movie title, most-downloaded first."""

    @abstractmethod
    async def download(self, candidate_id: str) -> tuple[str, bytes]:
        """Return (file_name, srt_bytes) for a provider candidate id."""
