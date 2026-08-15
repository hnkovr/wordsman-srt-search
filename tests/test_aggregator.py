from __future__ import annotations

import asyncio

import pytest

from srt_search.aggregator import download_candidate, resolve_providers, search_all
from srt_search.providers import (
    GestdownProvider,
    PodnapisiProvider,
    ProviderError,
    ProviderNotImplementedError,
    YifyProvider,
    make_provider,
)
from srt_search.providers.base import SearchProvider
from tests.conftest import SRT_BODY, make_candidate, make_settings


class FakeProvider(SearchProvider):
    name = "fake"

    def __init__(self, candidates=None, error=None, name=None):
        self.candidates = candidates or []
        self.error = error
        if name:
            self.name = name

    async def search(self, movie, year=None, limit=10):
        if self.error:
            raise self.error
        return self.candidates[:limit]

    async def download(self, candidate_id):
        return "fake.srt", SRT_BODY


def test_make_provider_resolves_registry():
    settings = make_settings()
    assert isinstance(make_provider("podnapisi", settings), PodnapisiProvider)
    assert isinstance(make_provider("yify", settings), YifyProvider)
    assert isinstance(make_provider("gestdown", settings), GestdownProvider)


def test_make_provider_unknown_fails_loud():
    with pytest.raises(ValueError, match="unknown provider 'nope'"):
        make_provider("nope", make_settings())


def test_resolve_providers_uses_settings_list():
    providers = resolve_providers(settings=make_settings(providers=["podnapisi", "yify"]))
    assert [p.name for p in providers] == ["podnapisi", "yify"]


def test_search_all_merges_and_ranks():
    a = FakeProvider(candidates=[make_candidate(candidate_id="1", downloads=5)], name="a")
    b = FakeProvider(candidates=[make_candidate(candidate_id="2", downloads=50)], name="b")
    result = asyncio.run(search_all("Dune", providers=[a, b]))
    assert [c.candidate_id for c in result.candidates] == ["2", "1"]
    assert result.failures == []


def test_search_all_collects_partial_failures():
    ok = FakeProvider(candidates=[make_candidate(candidate_id="1")], name="ok")
    broken = FakeProvider(error=ProviderError("boom"), name="broken")
    result = asyncio.run(search_all("Dune", providers=[ok, broken]))
    assert len(result.candidates) == 1
    assert [f.provider for f in result.failures] == ["broken"]


def test_search_all_raises_when_all_fail():
    broken = FakeProvider(error=ProviderError("boom"), name="broken")
    stub = FakeProvider(error=ProviderNotImplementedError("stub"), name="stub")
    with pytest.raises(ProviderError, match="all providers failed"):
        asyncio.run(search_all("Dune", providers=[broken, stub]))


def test_search_all_no_providers_fails_loud():
    with pytest.raises(ValueError, match="no providers"):
        asyncio.run(search_all("Dune", providers=[]))


def test_no_stub_providers_remain_in_registry():
    from srt_search.providers import REGISTRY

    settings = make_settings()
    for name in REGISTRY:
        provider = make_provider(name, settings)
        assert provider.implemented, name


def test_download_candidate_routes_by_provider(monkeypatch):
    import srt_search.aggregator as aggregator

    fake = FakeProvider(name="podnapisi")
    monkeypatch.setattr(aggregator, "make_provider", lambda name, settings=None: fake)
    file_name, content = asyncio.run(download_candidate(make_candidate()))
    assert file_name == "fake.srt"
    assert content == SRT_BODY
