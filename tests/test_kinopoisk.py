from __future__ import annotations

import pytest
import respx
from httpx import Response

from srt_search.kinopoisk import (
    parse_kinopoisk_id,
    parse_movie_html,
    resolve_kinopoisk_url,
)
from srt_search.providers.base import ProviderError
from tests.conftest import make_settings

KP = "https://www.kinopoisk.ru"

JSONLD_PAGE = """<html><head>
<script type="application/ld+json">
{"@context":"http://schema.org","@type":"Movie","name":"Одержимость",
 "alternateName":"Obsession","datePublished":"2026-02-12","url":"/film/10355286/"}
</script>
<meta property="og:title" content="Одержимость (2026) — Кинопоиск"/>
</head><body>ok</body></html>"""

OG_ONLY_PAGE = """<html><head>
<meta property="og:title" content="Одержимость (2026) — Кинопоиск"/>
</head><body>no jsonld</body></html>"""

CAPTCHA_PAGE = '<html><head></head><body><div class="showcaptcha">robot?</div></body></html>'


def test_parse_kinopoisk_id_variants():
    assert parse_kinopoisk_id("https://www.kinopoisk.ru/film/10355286/?x=1") == "10355286"
    assert parse_kinopoisk_id("https://kinopoisk.ru/series/123/") == "123"
    with pytest.raises(ValueError, match="not a kinopoisk"):
        parse_kinopoisk_id("https://imdb.com/title/tt1")


def test_parse_movie_html_jsonld_wins():
    movie = parse_movie_html("10355286", JSONLD_PAGE)
    assert movie.title == "Одержимость"
    assert movie.original_title == "Obsession"
    assert movie.year == 2026
    assert movie.search_title == "Obsession"


def test_parse_movie_html_og_title_fallback():
    movie = parse_movie_html("10355286", OG_ONLY_PAGE)
    assert movie.title == "Одержимость"
    assert movie.original_title is None
    assert movie.year == 2026
    assert movie.search_title == "Одержимость"


def test_parse_movie_html_no_data_raises():
    with pytest.raises(ProviderError, match="no parsable"):
        parse_movie_html("1", "<html><body>nothing here</body></html>")


@respx.mock
def test_resolve_happy_path():
    respx.get(f"{KP}/film/10355286/").mock(return_value=Response(200, text=JSONLD_PAGE))
    movie = resolve_kinopoisk_url(
        "https://www.kinopoisk.ru/film/10355286/?socialAlias=x", make_settings()
    )
    assert (movie.kp_id, movie.search_title, movie.year) == ("10355286", "Obsession", 2026)


@respx.mock
def test_resolve_retries_after_sso_interstitial():
    sso = "https://sso.passport.yandex.ru/push?retpath=x"
    respx.get(sso).mock(return_value=Response(200, text="<html>sso</html>"))
    respx.get(f"{KP}/film/10355286/").mock(
        side_effect=[
            Response(302, headers={"location": sso}),
            Response(200, text=JSONLD_PAGE),
        ]
    )
    movie = resolve_kinopoisk_url("https://www.kinopoisk.ru/film/10355286/", make_settings())
    assert movie.search_title == "Obsession"


@respx.mock
def test_resolve_captcha_raises():
    respx.get(f"{KP}/film/10355286/").mock(return_value=Response(200, text=CAPTCHA_PAGE))
    with pytest.raises(ProviderError, match="captcha"):
        resolve_kinopoisk_url("https://www.kinopoisk.ru/film/10355286/", make_settings())


@respx.mock
def test_resolve_http_error_raises():
    respx.get(f"{KP}/film/10355286/").mock(return_value=Response(503))
    with pytest.raises(ProviderError, match="503"):
        resolve_kinopoisk_url("https://www.kinopoisk.ru/film/10355286/", make_settings())
