"""Gestdown (Addic7ed proxy) backend — keyless, TV-series-focused.

Movie-oriented providers (yify, subtitlecat) can't reliably target a specific TV
episode. Gestdown (api.gestdown.info) is an Addic7ed proxy built around
show/season/episode, so it fills that gap. A query must carry a season/episode
marker (``S01E01``, ``1x01``, or ``season 1 episode 1``); without one there is no
episode to resolve and ``search`` returns no candidates (movies belong to the
other providers).

Flow:
  1. ``GET /shows/search/{title}``                        → show id
  2. ``GET /subtitles/get/{showId}/{season}/{ep}/{lang}`` → matching subtitles
  3. ``GET /subtitles/download/{subtitleId}``             → raw SRT bytes
"""

from __future__ import annotations

import re

import httpx

from srt_search.config import Settings, get_settings
from srt_search.logger import log
from srt_search.models import SearchCandidate
from srt_search.providers.base import ProviderError, SearchProvider

# Season/episode markers, most explicit first. The word form tolerates common
# spellings/abbreviations: "episode", "episod" (typo), and "ep".
_EPISODE_RES = (
    re.compile(r"s(\d{1,2})[\s._-]*e(\d{1,3})", re.I),
    re.compile(r"(?<!\d)(\d{1,2})x(\d{1,3})(?!\d)", re.I),
    re.compile(r"season\s*(\d{1,2}).*?\bep(?:isode|isod)?\b\.?\s*(\d{1,3})", re.I),
)

# ISO 639-1 → the language name Gestdown expects in the path.
_LANG_NAMES = {
    "en": "English",
    "ru": "Russian",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
}


def parse_episode(query: str) -> tuple[str, int, int] | None:
    """Split a query into (show_title, season, episode), or None if no marker.

    >>> parse_episode("Scenes from a Marriage S01E01")
    ('Scenes from a Marriage', 1, 1)
    >>> parse_episode("The Wire 1x03")
    ('The Wire', 1, 3)
    >>> parse_episode("Severance season 2 episode 5")
    ('Severance', 2, 5)
    >>> parse_episode("Scenes from a Marriage, 2021, season 1, episod 1")
    ('Scenes from a Marriage', 1, 1)
    >>> parse_episode("Inception") is None
    True
    """
    for pattern in _EPISODE_RES:
        match = pattern.search(query)
        if match:
            season, episode = int(match.group(1)), int(match.group(2))
            title = _clean_title(query[: match.start()])
            if title:
                return title, season, episode
    return None


def _clean_title(raw: str) -> str:
    """Trim a show title from the text before a season/episode marker.

    Drops a trailing release year and surrounding punctuation so the show search
    gets a clean name.

    >>> _clean_title("Scenes from a Marriage, 2021, ")
    'Scenes from a Marriage'
    >>> _clean_title("The Wire ")
    'The Wire'
    """
    title = re.sub(r"[,\s]*(?:19|20)\d{2}[,\s]*$", "", raw)
    return title.strip(" -._·,")


_DISPOSITION_RE = re.compile(r'filename="?([^";]+)"?')


def _filename_from_disposition(header: str | None) -> str | None:
    """Pull the plain filename from a Content-Disposition header.

    >>> _filename_from_disposition('attachment; filename=Show.S01E01.en.srt')
    'Show.S01E01.en.srt'
    >>> _filename_from_disposition(None) is None
    True
    """
    if not header:
        return None
    match = _DISPOSITION_RE.search(header)
    return match.group(1).strip() if match else None


class GestdownProvider(SearchProvider):
    name = "gestdown"
    implemented = True

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.settings.gestdown_base_url,
            headers={"User-Agent": self.settings.user_agent, "Accept": "application/json"},
            timeout=self.settings.request_timeout,
            follow_redirects=True,
        )

    def _language_name(self) -> str:
        code = (self.settings.language or "en").lower()
        return _LANG_NAMES.get(code, "English")

    async def _resolve_show_id(self, client: httpx.AsyncClient, title: str) -> str | None:
        resp = await client.get(f"/shows/search/{title}")
        if resp.status_code == httpx.codes.NOT_FOUND:
            return None
        if resp.status_code != httpx.codes.OK:
            raise ProviderError(f"gestdown show search failed: HTTP {resp.status_code}")
        shows = resp.json().get("shows") or []
        return shows[0]["id"] if shows else None

    async def search(
        self, movie: str, year: int | None = None, limit: int = 10
    ) -> list[SearchCandidate]:
        parsed = parse_episode(movie)
        if parsed is None:
            # No episode marker: Gestdown is episode-based, so nothing to resolve.
            return []
        title, season, episode = parsed
        language = self._language_name()
        try:
            async with self._client() as client:
                show_id = await self._resolve_show_id(client, title)
                if show_id is None:
                    return []
                resp = await client.get(f"/subtitles/get/{show_id}/{season}/{episode}/{language}")
        except httpx.HTTPError as exc:
            raise ProviderError(f"gestdown transport error: {exc}") from exc
        if resp.status_code == httpx.codes.NOT_FOUND:
            return []
        if resp.status_code != httpx.codes.OK:
            raise ProviderError(f"gestdown subtitles lookup failed: HTTP {resp.status_code}")

        payload = resp.json()
        subtitles = payload.get("matchingSubtitles") or []
        ep_info = payload.get("episode") or {}
        show_name = ep_info.get("show") or title
        # Prefer higher download counts, and non-hearing-impaired versions.
        subtitles.sort(
            key=lambda s: (not s.get("hearingImpaired", False), s.get("downloadCount", 0)),
            reverse=True,
        )
        candidates: list[SearchCandidate] = []
        for sub in subtitles[:limit]:
            candidates.append(
                SearchCandidate(
                    provider=self.name,
                    candidate_id=sub["subtitleId"],
                    title=f"{show_name} S{season:02d}E{episode:02d}",
                    year=year,
                    release=sub.get("version"),
                    language=self.settings.language,
                    downloads=int(sub.get("downloadCount", 0)),
                )
            )
        log.info(
            "gestdown: %d candidate(s) for %s S%02dE%02d", len(candidates), title, season, episode
        )
        return candidates

    async def download(self, candidate_id: str) -> tuple[str, bytes]:
        try:
            async with self._client() as client:
                resp = await client.get(f"/subtitles/download/{candidate_id}")
        except httpx.HTTPError as exc:
            raise ProviderError(f"gestdown download transport error: {exc}") from exc
        if resp.status_code != httpx.codes.OK:
            raise ProviderError(f"gestdown download failed: HTTP {resp.status_code}")
        file_name = _filename_from_disposition(resp.headers.get("content-disposition"))
        return file_name or f"{candidate_id}.srt", resp.content
