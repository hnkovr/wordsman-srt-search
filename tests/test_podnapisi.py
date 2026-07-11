from __future__ import annotations

import asyncio

import pytest
import respx
from httpx import Response

from srt_search.providers import PodnapisiProvider, ProviderError
from tests.conftest import SRT_BODY, make_settings, make_zip

BASE = "https://www.podnapisi.net"

SEARCH_PAYLOAD = {
    "data": [
        {
            "pid": "aaa1",
            "language": "en",
            "movie": {"title": "Dune", "year": 2021},
            "custom_releases": ["Dune.2021.1080p"],
            "stats": {"downloads": 5},
        },
        {
            "pid": "bbb2",
            "language": "en",
            "movie": {"title": "Dune", "year": 2021},
            "custom_releases": [],
            "stats": {"downloads": 99},
        },
        {"language": "en", "movie": {"title": "no pid, skipped"}},
    ]
}


def make_provider() -> PodnapisiProvider:
    return PodnapisiProvider(make_settings())


@respx.mock
def test_search_maps_sorts_and_skips_pidless():
    route = respx.get(f"{BASE}/subtitles/search/").mock(
        return_value=Response(200, json=SEARCH_PAYLOAD)
    )
    candidates = asyncio.run(make_provider().search("Dune", year=2021))
    assert route.called
    params = route.calls[0].request.url.params
    assert params["keywords"] == "Dune"
    assert params["year"] == "2021"
    assert params["language"] == "en"
    assert [c.candidate_id for c in candidates] == ["bbb2", "aaa1"]
    assert candidates[0].downloads == 99
    assert candidates[1].release == "Dune.2021.1080p"


@respx.mock
def test_search_respects_limit():
    respx.get(f"{BASE}/subtitles/search/").mock(return_value=Response(200, json=SEARCH_PAYLOAD))
    assert len(asyncio.run(make_provider().search("Dune", limit=1))) == 1


@respx.mock
def test_search_http_error_raises():
    respx.get(f"{BASE}/subtitles/search/").mock(return_value=Response(500))
    with pytest.raises(ProviderError, match="500"):
        asyncio.run(make_provider().search("Dune"))


@respx.mock
def test_search_non_json_raises():
    respx.get(f"{BASE}/subtitles/search/").mock(return_value=Response(200, text="<html>"))
    with pytest.raises(ProviderError, match="non-JSON"):
        asyncio.run(make_provider().search("Dune"))


@respx.mock
def test_download_extracts_srt_from_zip():
    payload = make_zip({"info.nfo": b"x", "Dune.2021.srt": SRT_BODY})
    respx.get(f"{BASE}/subtitles/aaa1/download").mock(return_value=Response(200, content=payload))
    file_name, content = asyncio.run(make_provider().download("aaa1"))
    assert file_name == "Dune.2021.srt"
    assert content == SRT_BODY


@respx.mock
def test_download_zip_without_srt_raises():
    respx.get(f"{BASE}/subtitles/aaa1/download").mock(
        return_value=Response(200, content=make_zip({"readme.txt": b"x"}))
    )
    with pytest.raises(ProviderError, match="no .srt"):
        asyncio.run(make_provider().download("aaa1"))


@respx.mock
def test_download_plain_srt_passthrough():
    respx.get(f"{BASE}/subtitles/ccc3/download").mock(return_value=Response(200, content=SRT_BODY))
    file_name, content = asyncio.run(make_provider().download("ccc3"))
    assert file_name == "ccc3.srt"
    assert content == SRT_BODY


@respx.mock
def test_download_http_error_raises():
    respx.get(f"{BASE}/subtitles/aaa1/download").mock(return_value=Response(404))
    with pytest.raises(ProviderError, match="404"):
        asyncio.run(make_provider().download("aaa1"))
