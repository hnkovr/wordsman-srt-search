"""Subtitlecat backend — keyless; serves many auto-translated languages per subtitle.

Unlike yify/podnapisi (English-only pull), subtitlecat hosts one subtitle entry with
per-language download links, so it honours ``settings.language`` (en, ru, …). Flow:
search page → subtitle detail page → ``<a id="download_<lang>" href="…-<lang>.srt">``.
HTML shapes pinned via .tmp/probe_subtitlecat.sh; `just probe-live-subtitlecat` re-checks.

Those per-language tracks are generated **on demand**, so a search hit is not a promise:
of four live "Interstellar" entries only one carried Russian (probed 2026-08-26). Listing
the other three would hand a caller three candidates whose download fails, so a non-English
search verifies each candidate's detail page first — see ``search``.
"""

from __future__ import annotations

import asyncio
import re

import httpx

from srt_search.config import Settings, get_settings
from srt_search.logger import log
from srt_search.models import SearchCandidate
from srt_search.providers.base import ProviderError, SearchProvider, SubtitleNotFoundError

_RESULT_RE = re.compile(r'href="(subs/\d+/[^"]+?)\.html"[^>]*>([^<]+)')
_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
#: The search table's own columns: real popularity, and how many languages exist already.
_DOWNLOADS_RE = re.compile(r"(\d[\d,]*)\s+downloads?")
_LANGUAGES_RE = re.compile(r"(\d+)\s+languages?")


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
        candidates = self._parse_results(resp.text)
        log.debug("subtitlecat: {!r} -> {} candidates", query, len(candidates))
        lang = self.settings.language
        if lang == "en" or not self.settings.subtitlecat_verify_language:
            # English is the source these entries are translated FROM: always present.
            return [candidate for candidate, _ in candidates][:limit]
        return await self._verified(candidates, limit)

    def _parse_results(self, html: str) -> list[tuple[SearchCandidate, int]]:
        """Candidates paired with their language count (how likely they carry ours)."""
        seen: set[str] = set()
        rows: list[tuple[SearchCandidate, int]] = []
        for match in _RESULT_RE.finditer(html):
            path, label = match.group(1), match.group(2)
            if path in seen:
                continue
            seen.add(path)
            end = html.find("</tr>", match.end())
            row = html[match.end() : end if end != -1 else match.end()]
            downloads = _DOWNLOADS_RE.search(row)
            languages = _LANGUAGES_RE.search(row)
            year_match = _YEAR_RE.search(label)
            rows.append(
                (
                    SearchCandidate(
                        provider=self.name,
                        candidate_id=path,  # "subs/<id>/<name>"
                        title=label.strip(),
                        year=int(year_match.group(1)) if year_match else None,
                        release=label.strip(),
                        language=self.settings.language,
                        downloads=int(downloads.group(1).replace(",", "")) if downloads else 0,
                    ),
                    int(languages.group(1)) if languages else 0,
                )
            )
        return rows

    async def _verified(
        self, rows: list[tuple[SearchCandidate, int]], limit: int
    ) -> list[SearchCandidate]:
        """Keep only candidates whose detail page really offers ``settings.language``.

        Probed in "most languages first" order and capped by ``subtitlecat_verify_max``,
        because each probe is a full detail-page GET. A probe that ERRORS keeps its
        candidate: a transient network fault must not silently shrink the result list —
        the download will then fail with the provider's own words instead.
        """
        rows.sort(key=lambda row: (row[1], row[0].downloads), reverse=True)
        head = rows[: self.settings.subtitlecat_verify_max]
        async with self._client() as client:
            checks = await asyncio.gather(
                *(self._offers_language(client, row[0].candidate_id) for row in head)
            )
        kept = [
            candidate for (candidate, _), ok in zip(head, checks, strict=True) if ok is not False
        ]
        dropped = len(head) - len(kept)
        if dropped:
            log.debug(
                "subtitlecat: dropped {} candidate(s) without a {} track",
                dropped,
                self.settings.language,
            )
        return kept[:limit]

    async def _offers_language(self, client: httpx.AsyncClient, candidate_id: str) -> bool | None:
        """True/False when the detail page answered, None when it could not be read."""
        try:
            page = await client.get(f"/{candidate_id}.html")
        except httpx.HTTPError as exc:
            log.debug("subtitlecat: cannot verify {}: {}", candidate_id, exc)
            return None
        if page.status_code != httpx.codes.OK:
            return None
        return self._find_lang_href(page.text, self.settings.language) is not None

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
