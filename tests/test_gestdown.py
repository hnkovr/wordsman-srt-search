from __future__ import annotations

import asyncio

import pytest
import respx
from httpx import Response

from srt_search.providers import GestdownProvider, ProviderError
from srt_search.providers.gestdown import parse_episode
from tests.conftest import make_settings

BASE = "https://api.gestdown.info"
SHOW_ID = "262d3039-32f0-4af5-b367-45e42f989a75"

SHOW_SEARCH = {"shows": [{"id": SHOW_ID, "name": "Scenes from a Marriage", "seasons": [1]}]}
SUBTITLES = {
    "matchingSubtitles": [
        {
            "subtitleId": "sub-hi",
            "version": "WEB-HI",
            "hearingImpaired": True,
            "downloadCount": 500,
        },
        {
            "subtitleId": "sub-a",
            "version": "WEB.H264-GGWP",
            "hearingImpaired": False,
            "downloadCount": 121,
        },
        {
            "subtitleId": "sub-b",
            "version": "WEB.other",
            "hearingImpaired": False,
            "downloadCount": 55,
        },
    ],
    "episode": {
        "season": 1,
        "number": 1,
        "title": "Innocence and Panic",
        "show": "Scenes from a Marriage",
    },
}
SRT_BYTES = b"1\n00:00:13,004 --> 00:00:15,404\n- Jess, it's this way.\n"


def make_provider(**overrides) -> GestdownProvider:
    return GestdownProvider(make_settings(**overrides))


def test_parse_episode_variants():
    assert parse_episode("Scenes from a Marriage S01E01") == ("Scenes from a Marriage", 1, 1)
    assert parse_episode("The Wire 1x03") == ("The Wire", 1, 3)
    assert parse_episode("Severance season 2 episode 5") == ("Severance", 2, 5)
    # tolerant of the "episod" typo and the "ep" abbreviation
    assert parse_episode("Scenes from a Marriage, 2021, season 1, episod 1") == (
        "Scenes from a Marriage, 2021",
        1,
        1,
    )
    assert parse_episode("Show season 3 ep 7") == ("Show", 3, 7)
    assert parse_episode("Inception") is None
    assert parse_episode("S01E01") is None  # no title before the marker


def test_search_without_episode_marker_returns_empty():
    # No network call needed: a movie query has no episode to resolve.
    assert asyncio.run(make_provider().search("Inception")) == []


@respx.mock
def test_search_resolves_episode_and_ranks_non_hi_first():
    respx.get(f"{BASE}/shows/search/Scenes from a Marriage").mock(
        return_value=Response(200, json=SHOW_SEARCH)
    )
    respx.get(f"{BASE}/subtitles/get/{SHOW_ID}/1/1/English").mock(
        return_value=Response(200, json=SUBTITLES)
    )
    candidates = asyncio.run(make_provider().search("Scenes from a Marriage S01E01"))
    # non-hearing-impaired first (despite lower downloads), then by download count
    assert [c.candidate_id for c in candidates] == ["sub-a", "sub-b", "sub-hi"]
    assert candidates[0].title == "Scenes from a Marriage S01E01"
    assert candidates[0].release == "WEB.H264-GGWP"


@respx.mock
def test_search_unknown_show_returns_empty():
    respx.get(f"{BASE}/shows/search/Nope").mock(return_value=Response(200, json={"shows": []}))
    assert asyncio.run(make_provider().search("Nope S01E01")) == []


@respx.mock
def test_search_episode_not_found_returns_empty():
    respx.get(f"{BASE}/shows/search/Scenes from a Marriage").mock(
        return_value=Response(200, json=SHOW_SEARCH)
    )
    respx.get(f"{BASE}/subtitles/get/{SHOW_ID}/9/9/English").mock(return_value=Response(404))
    assert asyncio.run(make_provider().search("Scenes from a Marriage S09E09")) == []


@respx.mock
def test_search_http_error_raises():
    respx.get(f"{BASE}/shows/search/Scenes from a Marriage").mock(return_value=Response(503))
    with pytest.raises(ProviderError, match="503"):
        asyncio.run(make_provider().search("Scenes from a Marriage S01E01"))


@respx.mock
def test_download_uses_content_disposition_filename():
    respx.get(f"{BASE}/subtitles/download/sub-a").mock(
        return_value=Response(
            200,
            content=SRT_BYTES,
            headers={"content-disposition": "attachment; filename=Scenes.S01E01.en.srt"},
        )
    )
    name, data = asyncio.run(make_provider().download("sub-a"))
    assert name == "Scenes.S01E01.en.srt"
    assert data == SRT_BYTES


@respx.mock
def test_download_falls_back_to_candidate_id_name():
    respx.get(f"{BASE}/subtitles/download/sub-a").mock(
        return_value=Response(200, content=SRT_BYTES)
    )
    name, _ = asyncio.run(make_provider().download("sub-a"))
    assert name == "sub-a.srt"


@respx.mock
def test_download_http_error_raises():
    respx.get(f"{BASE}/subtitles/download/sub-a").mock(return_value=Response(500))
    with pytest.raises(ProviderError, match="500"):
        asyncio.run(make_provider().download("sub-a"))
