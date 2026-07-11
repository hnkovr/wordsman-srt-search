"""Fan-out search across configured providers, merge and rank the results."""

from __future__ import annotations

import asyncio

from srt_search.config import Settings, get_settings
from srt_search.logger import log
from srt_search.models import ProviderFailure, SearchCandidate, SearchResult
from srt_search.providers import make_provider
from srt_search.providers.base import ProviderError, SearchProvider


def resolve_providers(
    names: list[str] | None = None, settings: Settings | None = None
) -> list[SearchProvider]:
    settings = settings or get_settings()
    return [make_provider(name, settings) for name in (names or settings.providers)]


async def search_all(
    movie: str,
    year: int | None = None,
    limit: int = 10,
    providers: list[SearchProvider] | None = None,
    settings: Settings | None = None,
) -> SearchResult:
    """Query every provider concurrently; a provider failure never hides the others.

    Raises ProviderError only when ALL providers fail (nothing usable came back).
    """
    providers = providers if providers is not None else resolve_providers(settings=settings)
    if not providers:
        raise ValueError("no providers configured")
    outcomes = await asyncio.gather(
        *(p.search(movie, year=year, limit=limit) for p in providers),
        return_exceptions=True,
    )
    candidates: list[SearchCandidate] = []
    failures: list[ProviderFailure] = []
    for provider, outcome in zip(providers, outcomes, strict=True):
        if isinstance(outcome, BaseException):
            if not isinstance(outcome, ProviderError):
                raise outcome
            log.warning("provider {} failed: {}", provider.name, outcome)
            failures.append(ProviderFailure(provider=provider.name, error=str(outcome)))
        else:
            candidates.extend(outcome)
    if failures and not candidates and len(failures) == len(providers):
        details = "; ".join(f"{f.provider}: {f.error}" for f in failures)
        raise ProviderError(f"all providers failed for {movie!r}: {details}")
    candidates.sort(key=lambda c: c.downloads, reverse=True)
    return SearchResult(movie=movie, candidates=candidates[:limit], failures=failures)


async def download_candidate(
    candidate: SearchCandidate, settings: Settings | None = None
) -> tuple[str, bytes]:
    provider = make_provider(candidate.provider, settings)
    return await provider.download(candidate.candidate_id)
