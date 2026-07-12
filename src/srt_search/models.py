"""Domain models shared by providers, the aggregator, and the CLI."""

from __future__ import annotations

from pydantic import BaseModel


class SearchCandidate(BaseModel):
    provider: str
    candidate_id: str
    title: str | None = None
    year: int | None = None
    release: str | None = None
    language: str = "en"
    downloads: int = 0
    file_name: str | None = None


class ProviderFailure(BaseModel):
    provider: str
    error: str


class SearchResult(BaseModel):
    movie: str
    candidates: list[SearchCandidate]
    failures: list[ProviderFailure]


class KinopoiskMovie(BaseModel):
    kp_id: str
    title: str | None = None  # localized (usually Russian) name
    original_title: str | None = None  # alternateName (usually the English original)
    year: int | None = None

    @property
    def search_title(self) -> str | None:
        """Best title for querying English-subtitle providers."""
        return self.original_title or self.title
