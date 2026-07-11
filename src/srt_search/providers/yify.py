"""YIFY Subtitles backend — keyless, movies only.

Flow: IMDb suggestion API resolves the title to a tt-id, the yifysubtitles
movie page lists per-language subtitle rows (rating + slug), and the download
is a ZIP at /subtitle/<slug>.zip. HTML shapes pinned via .tmp/probe_yify.sh;
`just probe-live-yify` re-checks them against the real site.
"""

from __future__ import annotations

import json
import re

import httpx

from srt_search.config import Settings, get_settings
from srt_search.logger import log
from srt_search.models import SearchCandidate
from srt_search.providers.base import ProviderError, SearchProvider, SubtitleNotFoundError
from srt_search.utils import extract_srt_from_archive

_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_RATING_RE = re.compile(r'<span class="label[^"]*">(-?\d+)</span>')
_LANG_RE = re.compile(r'<span class="sub-lang">([^<]+)</span>')
_SLUG_RE = re.compile(r'href="/subtitles/([^"]+)"')

# ISO 639-1 code -> language name as printed by yifysubtitles rows
_LANG_NAMES = {"en": "english", "ru": "russian", "de": "german", "fr": "french", "es": "spanish"}


class YifyProvider(SearchProvider):
    name = "yify"
    implemented = True

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _client(self, base_url: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=base_url,
            headers={"User-Agent": self.settings.user_agent},
            timeout=self.settings.request_timeout,
            follow_redirects=True,
        )

    async def _resolve_imdb(self, movie: str, year: int | None) -> tuple[str, str, int | None]:
        """Resolve a title to (imdb_id, canonical_title, year) via the IMDb suggest API."""
        query = movie.strip().lower().replace(" ", "_")
        try:
            async with self._client(self.settings.imdb_suggest_url) as client:
                resp = await client.get(f"/{query}.json")
        except httpx.HTTPError as exc:
            raise ProviderError(f"imdb suggest transport error: {exc}") from exc
        if resp.status_code != httpx.codes.OK:
            raise ProviderError(f"imdb suggest failed: HTTP {resp.status_code}")
        try:
            entries = resp.json().get("d") or []
        except (ValueError, json.JSONDecodeError) as exc:
            raise ProviderError("imdb suggest returned non-JSON payload") from exc
        movies = [e for e in entries if e.get("qid") == "movie" and e.get("id")]
        if year:
            exact = [e for e in movies if e.get("y") == year]
            movies = exact or movies
        if not movies:
            raise SubtitleNotFoundError(f"imdb suggest found no movie for {movie!r} (year={year})")
        top = movies[0]
        return top["id"], top.get("l") or movie, top.get("y")

    async def search(
        self, movie: str, year: int | None = None, limit: int = 10
    ) -> list[SearchCandidate]:
        imdb_id, title, resolved_year = await self._resolve_imdb(movie, year)
        try:
            async with self._client(self.settings.yify_base_url) as client:
                resp = await client.get(f"/movie-imdb/{imdb_id}")
        except httpx.HTTPError as exc:
            raise ProviderError(f"yify transport error: {exc}") from exc
        if resp.status_code != httpx.codes.OK:
            raise ProviderError(f"yify movie page failed: HTTP {resp.status_code}")
        wanted = _LANG_NAMES.get(self.settings.language, self.settings.language).lower()
        candidates: list[SearchCandidate] = []
        for row in _ROW_RE.findall(resp.text):
            lang = _LANG_RE.search(row)
            slug = _SLUG_RE.search(row)
            if not lang or not slug or lang.group(1).strip().lower() != wanted:
                continue
            rating = _RATING_RE.search(row)
            candidates.append(
                SearchCandidate(
                    provider=self.name,
                    candidate_id=slug.group(1),
                    title=title,
                    year=resolved_year,
                    release=slug.group(1),
                    language=self.settings.language,
                    downloads=int(rating.group(1)) if rating else 0,
                )
            )
        candidates.sort(key=lambda c: c.downloads, reverse=True)
        log.debug("yify: {!r} ({}) -> {} candidates", movie, imdb_id, len(candidates))
        return candidates[:limit]

    async def download(self, candidate_id: str) -> tuple[str, bytes]:
        # the zip endpoint 403s without a browser UA + a same-site Referer
        headers = {
            "User-Agent": self.settings.browser_user_agent,
            "Referer": f"{self.settings.yify_base_url}/subtitles/{candidate_id}",
        }
        try:
            async with self._client(self.settings.yify_base_url) as client:
                resp = await client.get(f"/subtitle/{candidate_id}.zip", headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderError(f"yify download transport error: {exc}") from exc
        if resp.status_code != httpx.codes.OK:
            raise ProviderError(f"yify download failed: HTTP {resp.status_code}")
        try:
            return extract_srt_from_archive(resp.content, candidate_id)
        except ValueError as exc:
            raise ProviderError(f"yify archive for {candidate_id}: {exc}") from exc
