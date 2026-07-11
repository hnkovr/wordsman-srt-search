"""Podnapisi.net backend — keyless JSON search; downloads arrive as ZIP archives.

Endpoint shapes follow the public JSON search (Accept: application/json). They are
not contractually stable — `just probe-live` exercises them against the real site.
"""

from __future__ import annotations

from typing import Any

import httpx

from srt_search.config import Settings, get_settings
from srt_search.logger import log
from srt_search.models import SearchCandidate
from srt_search.providers.base import ProviderError, SearchProvider
from srt_search.utils import extract_srt_from_archive


class PodnapisiProvider(SearchProvider):
    name = "podnapisi"
    implemented = True

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.settings.podnapisi_base_url,
            headers={
                "Accept": "application/json",
                "User-Agent": self.settings.user_agent,
            },
            timeout=self.settings.request_timeout,
            follow_redirects=True,
        )

    async def search(
        self, movie: str, year: int | None = None, limit: int = 10
    ) -> list[SearchCandidate]:
        params: dict[str, str] = {
            "keywords": movie,
            "language": self.settings.language,
            "movie_type": "movie",
        }
        if year:
            params["year"] = str(year)
        try:
            async with self._client() as client:
                resp = await client.get("/subtitles/search/", params=params)
        except httpx.HTTPError as exc:
            raise ProviderError(f"podnapisi search transport error: {exc}") from exc
        if resp.status_code != httpx.codes.OK:
            raise ProviderError(f"podnapisi search failed: HTTP {resp.status_code}")
        try:
            items = resp.json().get("data") or []
        except ValueError as exc:
            raise ProviderError("podnapisi search returned non-JSON payload") from exc
        candidates = [c for c in (self._to_candidate(item) for item in items) if c is not None]
        candidates.sort(key=lambda c: c.downloads, reverse=True)
        log.debug("podnapisi: {!r} year={} -> {} candidates", movie, year, len(candidates))
        return candidates[:limit]

    async def download(self, candidate_id: str) -> tuple[str, bytes]:
        try:
            async with self._client() as client:
                resp = await client.get(f"/subtitles/{candidate_id}/download")
        except httpx.HTTPError as exc:
            raise ProviderError(f"podnapisi download transport error: {exc}") from exc
        if resp.status_code != httpx.codes.OK:
            raise ProviderError(f"podnapisi download failed: HTTP {resp.status_code}")
        try:
            return extract_srt_from_archive(resp.content, candidate_id)
        except ValueError as exc:
            raise ProviderError(f"podnapisi archive for {candidate_id}: {exc}") from exc

    def _to_candidate(self, item: dict[str, Any]) -> SearchCandidate | None:
        pid = item.get("pid") or item.get("id")
        if pid is None:
            return None
        movie_info = item.get("movie") or {}
        releases = item.get("custom_releases") or item.get("releases") or []
        stats = item.get("stats") or {}
        return SearchCandidate(
            provider=self.name,
            candidate_id=str(pid),
            title=movie_info.get("title"),
            year=movie_info.get("year"),
            release=releases[0] if releases else None,
            language=item.get("language") or self.settings.language,
            downloads=stats.get("downloads") or item.get("downloads") or 0,
        )
