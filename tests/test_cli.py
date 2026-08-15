from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from srt_search import config
from srt_search.cli import main
from srt_search.providers import PodnapisiProvider
from tests.conftest import SRT_BODY, make_candidate


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("SRT_SEARCH_DOWNLOAD_DIR", str(tmp_path / "downloads"))
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def test_cli_providers_lists_status():
    result = CliRunner().invoke(main, ["providers"])
    assert result.exit_code == 0
    assert "podnapisi\timplemented" in result.output
    assert "yify\timplemented" in result.output
    assert "gestdown\timplemented" in result.output
    assert "subtitlecat\timplemented" in result.output


def test_cli_find_prints_json(monkeypatch):
    async def fake_search(self, movie, year=None, limit=10):
        return [make_candidate()]

    monkeypatch.setattr(PodnapisiProvider, "search", fake_search)
    result = CliRunner().invoke(main, ["find", "Dune", "--providers", "podnapisi"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["movie"] == "Dune"
    assert payload["candidates"][0]["candidate_id"] == "pid-1"


def test_cli_get_saves_file(monkeypatch, tmp_path):
    async def fake_search(self, movie, year=None, limit=10):
        return [make_candidate()]

    async def fake_download(self, candidate_id):
        return "Dune.2021.srt", SRT_BODY

    monkeypatch.setattr(PodnapisiProvider, "search", fake_search)
    monkeypatch.setattr(PodnapisiProvider, "download", fake_download)
    out_dir = tmp_path / "subs"
    result = CliRunner().invoke(
        main, ["get", "Dune", "--providers", "podnapisi", "--out", str(out_dir)]
    )
    assert result.exit_code == 0
    saved = out_dir / "Dune.2021.srt"
    assert saved.read_bytes() == SRT_BODY
    assert result.output.strip().endswith("Dune.2021.srt")


def test_cli_get_no_candidates_fails(monkeypatch):
    async def fake_search(self, movie, year=None, limit=10):
        return []

    monkeypatch.setattr(PodnapisiProvider, "search", fake_search)
    result = CliRunner().invoke(main, ["get", "Unknown", "--providers", "podnapisi"])
    assert result.exit_code != 0
    assert "no subtitles found" in result.output


def test_cli_version():
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "srt-search" in result.output
