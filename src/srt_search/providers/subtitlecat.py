"""Subtitlecat backend — keyless; serves many auto-translated languages per subtitle.

Unlike yify/podnapisi (English-only pull), subtitlecat hosts one subtitle entry with
per-language download links, so it honours ``settings.language`` (en, ru, …). Flow:
search page → subtitle detail page → ``<a id="download_<lang>" href="…-<lang>.srt">``.
HTML shapes pinned via .tmp/probe_subtitlecat.sh; `just probe-live-subtitlecat` re-checks.
"""

from __future__ import annotations

import re

import httpx

from srt_search.config import Settings, get_settings
from srt_search.logger import log
from srt_search.models import SearchCandidate
from srt_search.providers.base import ProviderError, SearchProvider, SubtitleNotFoundError

_RESULT_RE = re.compile(r'href="(subs/\d+/[^"]+?)\.html"[^>]*>([^<]+)')
_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


class SubtitlecatProvider(SearchProvider):
    name = "subtitlecat"
    implemented = True

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.settings.subtitlecat_base_url,
            headers={"User-Agent": self.settings.browser_user_agent},
            timeout=self.settings.request_timeout,
            follow_redirects=True,
        )

    async def search(
        self, movie: str, year: int | None = None, limit: int = 10
    ) -> list[SearchCandidate]:
        query = f"{movie} {year}" if year else movie
        try:
            async with self._client() as client:
                resp = await client.get("/index.php", params={"search": query})
        except httpx.HTTPError as exc:
            raise ProviderError(f"subtitlecat search transport error: {exc}") from exc
        if resp.status_code != httpx.codes.OK:
            raise ProviderError(f"subtitlecat search failed: HTTP {resp.status_code}")
        seen: set[str] = set()
        candidates: list[SearchCandidate] = []
        for path, label in _RESULT_RE.findall(resp.text):
            if path in seen:
                continue
            seen.add(path)
            year_match = _YEAR_RE.search(label)
            candidates.append(
                SearchCandidate(
                    provider=self.name,
                    candidate_id=path,  # "subs/<id>/<name>"
                    title=label.strip(),
                    year=int(year_match.group(1)) if year_match else None,
                    release=label.strip(),
                    language=self.settings.language,
                )
            )
        log.debug("subtitlecat: {!r} -> {} candidates", query, len(candidates))
        return candidates[:limit]

    async def download(self, candidate_id: str) -> tuple[str, bytes]:
        lang = self.settings.language
        detail_path = f"/{candidate_id}.html"
        try:
            async with self._client() as client:
                page = await client.get(detail_path)
                if page.status_code != httpx.codes.OK:
                    raise ProviderError(f"subtitlecat detail failed: HTTP {page.status_code}")
                srt_href = self._find_lang_href(page.text, lang)
                if not srt_href:
                    raise SubtitleNotFoundError(
                        f"subtitlecat has no {lang} track for {candidate_id}"
                    )
                srt = await client.get(srt_href, headers={"Referer": str(page.url)})
        except httpx.HTTPError as exc:
            raise ProviderError(f"subtitlecat download transport error: {exc}") from exc
        if srt.status_code != httpx.codes.OK:
            raise ProviderError(f"subtitlecat srt fetch failed: HTTP {srt.status_code}")
        file_name = srt_href.rsplit("/", 1)[-1]
        return file_name, srt.content

    @staticmethod
    def _find_lang_href(html: str, lang: str) -> str | None:
        """Return the download href for the given language code, or None."""
        pattern = re.compile(
            rf'id="download_{re.escape(lang)}"[^>]*href="([^"]+\.srt)"'
            rf'|href="([^"]+\.srt)"[^>]*id="download_{re.escape(lang)}"'
        )
        match = pattern.search(html)
        if not match:
            return None
        return match.group(1) or match.group(2)
