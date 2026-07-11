from __future__ import annotations

import io
import zipfile

from srt_search.config import Settings
from srt_search.models import SearchCandidate

SRT_BODY = b"1\n00:00:01,000 --> 00:00:02,000\nArrakis awaits.\n"


def make_settings(**overrides) -> Settings:
    defaults = dict(_env_file=None)
    defaults.update(overrides)
    return Settings(**defaults)


def make_candidate(**overrides) -> SearchCandidate:
    defaults = dict(
        provider="podnapisi",
        candidate_id="pid-1",
        title="Dune",
        year=2021,
        release="Dune.2021.1080p",
        language="en",
        downloads=10,
    )
    defaults.update(overrides)
    return SearchCandidate(**defaults)


def make_zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()
