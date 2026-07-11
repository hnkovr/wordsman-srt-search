from __future__ import annotations

from srt_search.utils import best_candidate, safe_download_path, sanitize_filename
from tests.conftest import make_candidate


def test_sanitize_strips_traversal_and_adds_suffix():
    assert sanitize_filename("../../etc/passwd") == "passwd.srt"
    assert sanitize_filename("Dune.2021") == "Dune.2021.srt"
    assert sanitize_filename("...") == "subtitle.srt"


def test_safe_download_path_stays_inside_dir(tmp_path):
    target = safe_download_path(tmp_path / "dl", "../escape.srt")
    assert target.parent == (tmp_path / "dl").resolve()
    assert target.name == "escape.srt"


def test_best_candidate_picks_most_downloaded():
    low = make_candidate(candidate_id="1", downloads=1)
    high = make_candidate(candidate_id="2", downloads=50)
    assert best_candidate([low, high]).candidate_id == "2"
    assert best_candidate([]) is None
