from __future__ import annotations

import asyncio

import pytest
import respx
from httpx import Response

from srt_search.providers import ProviderError, SubtitleNotFoundError, YifyProvider
from tests.conftest import SRT_BODY, make_settings, make_zip

SUGGEST = "https://v3.sg.media-imdb.com/suggestion/x"
YIFY = "https://yifysubtitles.ch"

SUGGEST_PAYLOAD = {
    "d": [
        {"id": "tt5764360", "l": "Beautiful Mind", "qid": "tvSeries", "y": 2016},
        {"id": "tt0268978", "l": "A Beautiful Mind", "qid": "movie", "y": 2001},
        {"id": "tt9999999", "l": "Beautiful Mind Again", "qid": "movie", "y": 2019},
    ]
}


def movie_row(rating: int, lang: str, slug: str) -> str:
    return (
        f'<tr data-id="1"><td class="rating-cell"><span class="label">{rating}</span></td>'
        f'<td class="flag-cell"><span class="flag"></span><span class="sub-lang">{lang}</span></td>'
        f'<td class="download-cell"><a href="/subtitles/{slug}">download</a></td></tr>'
    )


MOVIE_PAGE = (
    "<table><tbody>"
    + movie_row(0, "English", "a-beautiful-mind-2001-english-yify-114605")
    + movie_row(5, "Arabic", "a-beautiful-mind-2001-arabic-yify-114580")
    + movie_row(3, "English", "a-beautiful-mind-2001-english-yify-114610")
    + "<tr><td>malformed row without spans</td></tr>"
    + "</tbody></table>"
)


def make_provider() -> YifyProvider:
    return YifyProvider(make_settings())


def mock_happy_path():
    respx.get(f"{SUGGEST}/beautiful_mind.json").mock(
        return_value=Response(200, json=SUGGEST_PAYLOAD)
    )
    respx.get(f"{YIFY}/movie-imdb/tt0268978").mock(return_value=Response(200, text=MOVIE_PAGE))


@respx.mock
def test_search_filters_language_sorts_by_rating():
    mock_happy_path()
    candidates = asyncio.run(make_provider().search("Beautiful Mind", year=2001))
    assert [c.candidate_id for c in candidates] == [
        "a-beautiful-mind-2001-english-yify-114610",
        "a-beautiful-mind-2001-english-yify-114605",
    ]
    assert candidates[0].downloads == 3
    assert candidates[0].title == "A Beautiful Mind"
    assert candidates[0].year == 2001
    assert all(c.language == "en" for c in candidates)


@respx.mock
def test_search_year_filter_prefers_exact_match():
    mock_happy_path()
    respx.get(f"{YIFY}/movie-imdb/tt9999999").mock(return_value=Response(200, text=MOVIE_PAGE))
    candidates = asyncio.run(make_provider().search("Beautiful Mind", year=2019))
    assert candidates  # resolved tt9999999 (exact year), page still parses
    assert candidates[0].year == 2019


@respx.mock
def test_search_no_movie_raises_not_found():
    respx.get(f"{SUGGEST}/unknown_thing.json").mock(
        return_value=Response(200, json={"d": [{"id": "tt1", "qid": "tvSeries"}]})
    )
    with pytest.raises(SubtitleNotFoundError, match="no movie"):
        asyncio.run(make_provider().search("Unknown Thing"))


@respx.mock
def test_suggest_http_error_raises():
    respx.get(f"{SUGGEST}/beautiful_mind.json").mock(return_value=Response(503))
    with pytest.raises(ProviderError, match="503"):
        asyncio.run(make_provider().search("Beautiful Mind"))


@respx.mock
def test_movie_page_http_error_raises():
    respx.get(f"{SUGGEST}/beautiful_mind.json").mock(
        return_value=Response(200, json=SUGGEST_PAYLOAD)
    )
    respx.get(f"{YIFY}/movie-imdb/tt0268978").mock(return_value=Response(500))
    with pytest.raises(ProviderError, match="500"):
        asyncio.run(make_provider().search("Beautiful Mind", year=2001))


@respx.mock
def test_download_unzips_srt_with_referer():
    slug = "a-beautiful-mind-2001-english-yify-114605"
    route = respx.get(f"{YIFY}/subtitle/{slug}.zip").mock(
        return_value=Response(200, content=make_zip({"A.Beautiful.Mind.srt": SRT_BODY}))
    )
    file_name, content = asyncio.run(make_provider().download(slug))
    assert file_name == "A.Beautiful.Mind.srt"
    assert content == SRT_BODY
    request = route.calls[0].request
    assert request.headers["referer"] == f"{YIFY}/subtitles/{slug}"
    assert "Mozilla" in request.headers["user-agent"]


@respx.mock
def test_download_http_error_raises():
    respx.get(f"{YIFY}/subtitle/x.zip").mock(return_value=Response(404))
    with pytest.raises(ProviderError, match="404"):
        asyncio.run(make_provider().download("x"))
