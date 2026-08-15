"""Schema validation for the dual_subtitle_sources catalog in config/config.yml."""

from __future__ import annotations

import yaml

from srt_search.config import CONFIG_YML
from tests.conftest import make_settings

REQUIRED_KEYS = {"name", "url", "access", "free", "notes"}
ALLOWED_ACCESS = {"keyless", "browser", "torrent"}


def load_catalog() -> list[dict]:
    data = yaml.safe_load(CONFIG_YML.read_text(encoding="utf-8"))
    return data["dual_subtitle_sources"]


def test_catalog_entries_have_required_keys() -> None:
    for entry in load_catalog():
        missing = REQUIRED_KEYS - entry.keys()
        assert not missing, f"{entry.get('name', entry)}: missing {missing}"


def test_catalog_access_values_are_known() -> None:
    for entry in load_catalog():
        assert entry["access"] in ALLOWED_ACCESS, entry["name"]


def test_catalog_urls_are_https() -> None:
    for entry in load_catalog():
        assert entry["url"].startswith("https://"), entry["name"]
        search_url = entry.get("search_url")
        if search_url is not None:
            assert search_url.startswith("https://"), entry["name"]


def test_catalog_search_urls_carry_query_placeholder() -> None:
    for entry in load_catalog():
        search_url = entry.get("search_url")
        if search_url is not None:
            assert "{query}" in search_url, entry["name"]


def test_catalog_names_are_unique() -> None:
    names = [entry["name"] for entry in load_catalog()]
    assert len(names) == len(set(names))


def test_settings_still_construct_with_catalog_present() -> None:
    # The catalog is untyped on Settings (extra="ignore") — it must never
    # break settings construction.
    settings = make_settings()
    assert not hasattr(settings, "dual_subtitle_sources")
