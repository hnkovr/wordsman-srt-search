"""Internal helpers: filename hygiene and candidate ranking."""

from __future__ import annotations

import re
from pathlib import Path

from srt_search.models import SearchCandidate

_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._ -]+")


def sanitize_filename(name: str) -> str:
    """Reduce any provider-supplied name to a flat, filesystem-safe .srt file name.

    >>> sanitize_filename("../../etc/passwd")
    'passwd.srt'
    >>> sanitize_filename("Dune (2021).srt")
    'Dune _2021_.srt'
    >>> sanitize_filename("...")
    'subtitle.srt'
    """
    name = Path(name.replace("\\", "/")).name.strip()
    name = _FILENAME_SAFE.sub("_", name).strip("._ ") or "subtitle"
    if not name.lower().endswith(".srt"):
        name += ".srt"
    return name


def safe_download_path(download_dir: Path, file_name: str) -> Path:
    """Resolve file_name inside download_dir, refusing anything that escapes it."""
    download_dir.mkdir(parents=True, exist_ok=True)
    target = (download_dir / sanitize_filename(file_name)).resolve()
    if target.parent != download_dir.resolve():
        raise ValueError(f"unsafe file name: {file_name!r}")
    return target


def best_candidate(candidates: list[SearchCandidate]) -> SearchCandidate | None:
    """Pick the most-downloaded candidate."""
    return max(candidates, key=lambda c: c.downloads, default=None)
