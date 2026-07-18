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


async def _query_providers(
    providers: list[SearchProvider], movie: str, year: int | None, limit: int
) -> tuple[list[SearchCandidate], list[ProviderFailure]]:
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
    return candidates, failures


async def search_all(
    movie: str,
    year: int | None = None,
    limit: int = 10,
    providers: list[SearchProvider] | None = None,
    settings: Settings | None = None,
    llm_fallback: bool = False,
) -> SearchResult:
    """Query every provider concurrently; a provider failure never hides the others.

    When ``llm_fallback`` is set and nothing is found, an LLM CLI is asked to
    disambiguate the title and the search is retried with its suggested titles.
    Raises ProviderError only when ALL providers fail (nothing usable came back).
    """
    providers = providers if providers is not None else resolve_providers(settings=settings)
    if not providers:
        raise ValueError("no providers configured")
    candidates, failures = await _query_providers(providers, movie, year, limit)

    if not candidates and llm_fallback:
        from srt_search.llm_fallback import suggest_query  # lazy: optional subprocess path

        suggestion = suggest_query(movie, year, settings=settings)
        if suggestion is not None:
            log.info("llm_fallback: {} -> {}", movie, suggestion.note or suggestion.title)
            for alt in suggestion.queries(movie):
                if alt.lower() == movie.lower():
                    continue
                alt_year = suggestion.year or year
                candidates, alt_failures = await _query_providers(providers, alt, alt_year, limit)
                if candidates:
                    log.info("llm_fallback: found via {!r} ({})", alt, alt_year)
                    break
                failures.extend(alt_failures)

    if failures and not candidates and len(failures) >= len(providers):
        details = "; ".join(f"{f.provider}: {f.error}" for f in failures)
        raise ProviderError(f"all providers failed for {movie!r}: {details}")
    candidates.sort(key=lambda c: c.downloads, reverse=True)
    return SearchResult(movie=movie, candidates=candidates[:limit], failures=failures)


async def download_candidate(
    candidate: SearchCandidate, settings: Settings | None = None
) -> tuple[str, bytes]:
    provider = make_provider(candidate.provider, settings)
    return await provider.download(candidate.candidate_id)
