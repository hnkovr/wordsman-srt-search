from __future__ import annotations

import asyncio

import pytest
import respx
from httpx import Response

from srt_search.providers import ProviderError, SubtitlecatProvider, SubtitleNotFoundError
from tests.conftest import make_settings

BASE = "https://www.subtitlecat.com"

SEARCH_HTML = (
    "<table>\n"
    '<tr><td><a href="subs/1489/Obsession.2025.1080p.English.html">'
    "Obsession.2025.1080p.English</a></td></tr>\n"
    '<tr><td><a href="subs/1489/Obsession.2025.1080p.English.html">dup</a></td></tr>\n'
    '<tr><td><a href="subs/1547/Obsession 2025.html">Obsession 2025</a></td></tr>\n'
    "</table>"
)

DETAIL_HTML = (
    '<div class="sub-single"><span>English</span>'
    '<a id="download_en" href="/subs/1489/Obsession.2025.1080p.English-en.srt">Download</a></div>'
    '<div class="sub-single"><span>Russian</span>'
    '<a id="download_ru" onclick="log_download(1)" '
    'href="/subs/1573/Obsession.2025.1080p.English-ru.srt">Download</a></div>'
)

RU_SRT = b"1\n00:00:57,580 --> 00:01:04,280\n\xd0\xa2\xd1\x8b.\n"


def make_provider(**overrides) -> SubtitlecatProvider:
    return SubtitlecatProvider(make_settings(**overrides))


@respx.mock
def test_search_parses_and_dedupes():
    respx.get(f"{BASE}/index.php").mock(return_value=Response(200, text=SEARCH_HTML))
    candidates = asyncio.run(make_provider().search("Obsession", year=2025))
    assert [c.candidate_id for c in candidates] == [
        "subs/1489/Obsession.2025.1080p.English",
        "subs/1547/Obsession 2025",
    ]
    assert candidates[0].year == 2025
    assert respx.calls[0].request.url.params["search"] == "Obsession 2025"


@respx.mock
def test_search_http_error_raises():
    respx.get(f"{BASE}/index.php").mock(return_value=Response(503))
    with pytest.raises(ProviderError, match="503"):
        asyncio.run(make_provider().search("Obsession"))


@respx.mock
def test_download_picks_configured_language():
    respx.get(f"{BASE}/subs/1489/Obsession.2025.1080p.English.html").mock(
        return_value=Response(200, text=DETAIL_HTML)
    )
    respx.get(f"{BASE}/subs/1573/Obsession.2025.1080p.English-ru.srt").mock(
        return_value=Response(200, content=RU_SRT)
    )
    provider = make_provider(language="ru")
    name, content = asyncio.run(provider.download("subs/1489/Obsession.2025.1080p.English"))
    assert name == "Obsession.2025.1080p.English-ru.srt"
    assert content == RU_SRT


@respx.mock
def test_download_missing_language_raises():
    respx.get(f"{BASE}/subs/1489/x.html").mock(return_value=Response(200, text=DETAIL_HTML))
    provider = make_provider(language="ja")  # not present in DETAIL_HTML
    with pytest.raises(SubtitleNotFoundError, match="no ja track"):
        asyncio.run(provider.download("subs/1489/x"))


@respx.mock
def test_download_detail_http_error_raises():
    respx.get(f"{BASE}/subs/1489/x.html").mock(return_value=Response(404))
    with pytest.raises(ProviderError, match="404"):
        asyncio.run(make_provider().download("subs/1489/x"))


def test_registered_in_registry():
    from srt_search.providers import REGISTRY, make_provider

    assert REGISTRY["subtitlecat"] is SubtitlecatProvider
    assert isinstance(make_provider("subtitlecat", make_settings()), SubtitlecatProvider)
