"""Kinopoisk URL → movie identification (kp_id, localized title, original title, year).

Parses the public film page: JSON-LD (`application/ld+json`) first, `og:title` as a
fallback. Kinopoisk serves a captcha to suspicious clients — that surfaces as a
fail-loud ProviderError, never a silent empty result.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from srt_search.config import Settings, get_settings
from srt_search.logger import log
from srt_search.models import KinopoiskMovie
from srt_search.providers.base import ProviderError

_KP_ID_RE = re.compile(r"kinopoisk\.ru/(?:film|series)/(\d+)")
_JSONLD_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S | re.I)
_OG_TITLE_RE = re.compile(r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"')
_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


def parse_kinopoisk_id(url: str) -> str:
    """Extract the numeric film/series id from a kinopoisk URL.

    >>> parse_kinopoisk_id("https://www.kinopoisk.ru/film/10355286/?socialAlias=x")
    '10355286'
    >>> parse_kinopoisk_id("https://kinopoisk.ru/series/123/")
    '123'
    """
    match = _KP_ID_RE.search(url)
    if not match:
        raise ValueError(f"not a kinopoisk film/series URL: {url!r}")
    return match.group(1)


def _parse_year(*values: object) -> int | None:
    for value in values:
        match = _YEAR_RE.search(str(value or ""))
        if match:
            return int(match.group(1))
    return None


def _movie_from_jsonld(kp_id: str, html: str) -> KinopoiskMovie | None:
    for raw in _JSONLD_RE.findall(html):
        try:
            payload: Any = json.loads(raw.strip())
        except ValueError:
            continue
        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("@type") not in ("Movie", "TVSeries"):
                continue
            title = node.get("name") or None
            original = node.get("alternateName") or node.get("alternativeHeadline") or None
            year = _parse_year(node.get("datePublished"), node.get("name"))
            if title or original:
                return KinopoiskMovie(kp_id=kp_id, title=title, original_title=original, year=year)
    return None


def _movie_from_og_title(kp_id: str, html: str) -> KinopoiskMovie | None:
    match = _OG_TITLE_RE.search(html)
    if not match:
        return None
    raw = match.group(1)
    year = _parse_year(raw)
    # typical shapes: "Название (2026)" / "Название (сериал, 2026) — Кинопоиск"
    title = re.split(r"\s*[(—–]", raw, maxsplit=1)[0].strip() or None
    if not title:
        return None
    return KinopoiskMovie(kp_id=kp_id, title=title, original_title=None, year=year)


def parse_movie_html(kp_id: str, html: str) -> KinopoiskMovie:
    """Pure parser: JSON-LD first, og:title fallback; fail-loud when neither works."""
    movie = _movie_from_jsonld(kp_id, html) or _movie_from_og_title(kp_id, html)
    if movie is None or not movie.search_title:
        raise ProviderError(
            f"kinopoisk page for id {kp_id} has no parsable JSON-LD/og:title movie data"
        )
    return movie


def resolve_kinopoisk_url(url: str, settings: Settings | None = None) -> KinopoiskMovie:
    settings = settings or get_settings()
    kp_id = parse_kinopoisk_id(url)
    page_url = f"{settings.kinopoisk_base_url}/film/{kp_id}/"
    try:
        with httpx.Client(
            headers={
                "User-Agent": settings.browser_user_agent,
                "Accept-Language": "ru,en;q=0.8",
            },
            timeout=settings.request_timeout,
            follow_redirects=True,
        ) as client:
            resp = client.get(page_url)
            if "kinopoisk.ru" not in resp.url.host:
                # first hit lands on the Yandex SSO interstitial; the hop sets cookies
                # that unlock the real page on a second request in the same session
                resp = client.get(page_url)
    except httpx.HTTPError as exc:
        raise ProviderError(f"kinopoisk transport error: {exc}") from exc
    final_url = str(resp.url)
    if "captcha" in final_url or "showcaptcha" in resp.text[:2000]:
        raise ProviderError(
            f"kinopoisk served a captcha for {page_url} — open it in a browser once "
            "or resolve the title manually"
        )
    if resp.status_code != httpx.codes.OK:
        raise ProviderError(f"kinopoisk page failed: HTTP {resp.status_code} for {page_url}")
    movie = parse_movie_html(kp_id, resp.text)
    log.debug("kinopoisk {} -> {!r}", kp_id, movie)
    return movie
