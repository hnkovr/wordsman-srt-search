from __future__ import annotations

import asyncio
import json

from srt_search.aggregator import search_all
from srt_search.llm_fallback import QuerySuggestion, _extract_json_object, suggest_query
from srt_search.models import SearchCandidate
from srt_search.providers.base import SearchProvider
from tests.conftest import make_settings


class StubProvider(SearchProvider):
    name = "stub"

    def __init__(self, by_title):
        self.by_title = by_title  # {title_lower: [candidates]}
        self.queried: list[str] = []

    async def search(self, movie, year=None, limit=10):
        self.queried.append(movie)
        return list(self.by_title.get(movie.lower(), []))

    async def download(self, candidate_id):
        return "x.srt", b"x"


def cand(cid="1"):
    return SearchCandidate(provider="stub", candidate_id=cid, title="Found", downloads=5)


def test_extract_json_object_from_chatty_output():
    assert _extract_json_object('note\n{"title": "X"}\nend') == {"title": "X"}
    assert _extract_json_object("nope") is None


def test_suggestion_queries_dedupe_and_keep_original():
    s = QuerySuggestion(title="Canonical", alternate_titles=["Alt", "canonical"])
    assert s.queries("Original") == ["Canonical", "Alt", "Original"]


def test_suggest_query_parses_runner_json():
    def runner(cli, prompt):
        return json.dumps(
            {
                "title": "The Odyssey",
                "year": 1997,
                "alternate_titles": ["Odyssey"],
                "likely_subtitled": True,
                "note": "the 1997 miniseries",
            }
        )

    s = suggest_query("Odyssey", 2026, settings=make_settings(), runner=runner)
    assert s.title == "The Odyssey"
    assert s.year == 1997
    assert "Odyssey" in s.alternate_titles


def test_search_all_no_fallback_returns_empty():
    provider = StubProvider({})
    result = asyncio.run(search_all("Ghost", providers=[provider], llm_fallback=False))
    assert result.candidates == []
    assert provider.queried == ["Ghost"]


def test_search_all_fallback_retries_with_suggested_title(monkeypatch):
    provider = StubProvider({"the real title": [cand()]})

    def fake_suggest(movie, year=None, settings=None):
        return QuerySuggestion(title="The Real Title", year=2020, note="corrected")

    monkeypatch.setattr("srt_search.llm_fallback.suggest_query", fake_suggest)
    result = asyncio.run(search_all("Reel Titel", providers=[provider], llm_fallback=True))
    assert len(result.candidates) == 1
    assert "The Real Title" in provider.queried


def test_search_all_fallback_gives_up_cleanly(monkeypatch):
    provider = StubProvider({})
    monkeypatch.setattr(
        "srt_search.llm_fallback.suggest_query",
        lambda movie, year=None, settings=None: QuerySuggestion(title="Still Missing"),
    )
    result = asyncio.run(search_all("Nothing", providers=[provider], llm_fallback=True))
    assert result.candidates == []
