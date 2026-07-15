from __future__ import annotations

from srt_search.doublesubs import _gui_open, build_doublesubs_url, open_doublesubs
from tests.conftest import make_settings


def test_build_url_no_query():
    assert build_doublesubs_url(settings=make_settings()) == "https://app.doublesubs.com"


def test_build_url_with_query_encoded():
    url = build_doublesubs_url("A Beautiful Mind", settings=make_settings())
    assert url == "https://app.doublesubs.com/?q=A+Beautiful+Mind"


def test_build_url_strips_trailing_slash():
    settings = make_settings(doublesubs_app_url="https://app.doublesubs.com/")
    assert build_doublesubs_url(settings=settings) == "https://app.doublesubs.com"


def test_open_uses_injected_opener():
    opened = []
    url = open_doublesubs("Dune", settings=make_settings(), opener=opened.append)
    assert url == "https://app.doublesubs.com/?q=Dune"
    assert opened == ["https://app.doublesubs.com/?q=Dune"]


def test_gui_open_argv_per_platform(monkeypatch):
    monkeypatch.setattr("srt_search.doublesubs.sys.platform", "darwin")
    assert _gui_open("http://x")[0] == "open"
    monkeypatch.setattr("srt_search.doublesubs.sys.platform", "linux")
    assert _gui_open("http://x")[0] == "xdg-open"
