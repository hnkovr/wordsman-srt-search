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


# Rows as the live search table renders them: popularity and how many languages exist.
SEARCH_TABLE = (
    "<table>\n"
    '<tr><td><a href="subs/1397/Rich.html">Rich</a> (translated from English)</td>'
    "<td>31 downloads</td><td>31 languages</td></tr>\n"
    '<tr><td><a href="subs/1459/Poor.html">Poor</a></td>'
    "<td>10 downloads</td><td>10 languages</td></tr>\n"
    "</table>"
)
NO_RU_HTML = '<a id="download_en" href="/subs/1459/Poor-en.srt">Download</a>'
HAS_RU_HTML = '<a id="download_ru" href="/subs/1397/Rich-ru.srt">Download</a>'


@respx.mock
def test_search_parses_downloads_from_the_table():
    """Ranking is by downloads — parsing 0 for everything made the order arbitrary."""
    respx.get(f"{BASE}/index.php").mock(return_value=Response(200, text=SEARCH_TABLE))
    candidates = asyncio.run(make_provider().search("X"))
    assert [c.downloads for c in candidates] == [31, 10]


@respx.mock
def test_english_search_does_not_open_detail_pages():
    """English is the source language of every entry — verifying it would be wasted GETs."""
    search = respx.get(f"{BASE}/index.php").mock(return_value=Response(200, text=SEARCH_TABLE))
    detail = respx.get(url__regex=rf"{BASE}/subs/.*").mock(return_value=Response(200, text=""))
    asyncio.run(make_provider(language="en").search("X"))
    assert search.called and not detail.called


@respx.mock
def test_russian_search_drops_candidates_without_a_russian_track():
    """A listed candidate whose download would fail is worse than a shorter list."""
    respx.get(f"{BASE}/index.php").mock(return_value=Response(200, text=SEARCH_TABLE))
    respx.get(f"{BASE}/subs/1397/Rich.html").mock(return_value=Response(200, text=HAS_RU_HTML))
    respx.get(f"{BASE}/subs/1459/Poor.html").mock(return_value=Response(200, text=NO_RU_HTML))
    candidates = asyncio.run(make_provider(language="ru").search("X"))
    assert [c.candidate_id for c in candidates] == ["subs/1397/Rich"]


@respx.mock
def test_unreachable_detail_page_keeps_the_candidate():
    """A transient fault must not silently shrink the list — let the download report it."""
    respx.get(f"{BASE}/index.php").mock(return_value=Response(200, text=SEARCH_TABLE))
    respx.get(f"{BASE}/subs/1397/Rich.html").mock(return_value=Response(200, text=HAS_RU_HTML))
    respx.get(f"{BASE}/subs/1459/Poor.html").mock(return_value=Response(503))
    candidates = asyncio.run(make_provider(language="ru").search("X"))
    assert {c.candidate_id for c in candidates} == {"subs/1397/Rich", "subs/1459/Poor"}


@respx.mock
def test_verification_is_capped():
    respx.get(f"{BASE}/index.php").mock(return_value=Response(200, text=SEARCH_TABLE))
    detail = respx.get(url__regex=rf"{BASE}/subs/.*").mock(
        return_value=Response(200, text=HAS_RU_HTML)
    )
    provider = make_provider(language="ru", subtitlecat_verify_max=1)
    candidates = asyncio.run(provider.search("X"))
    assert detail.call_count == 1
    assert [c.candidate_id for c in candidates] == ["subs/1397/Rich"]  # most languages first


@respx.mock
def test_verification_can_be_switched_off():
    respx.get(f"{BASE}/index.php").mock(return_value=Response(200, text=SEARCH_TABLE))
    detail = respx.get(url__regex=rf"{BASE}/subs/.*").mock(return_value=Response(200, text=""))
    provider = make_provider(language="ru", subtitlecat_verify_language=False)
    assert len(asyncio.run(provider.search("X"))) == 2
    assert not detail.called
