"""Gestdown (Addic7ed proxy) backend — STUB.

TODO(srt-search-gestdown): implement REST search + download against
api.gestdown.info (keyless, TV-series-focused; limited movie coverage).
Tracked as a Linear/Todoist task "srt-search: implement Gestdown provider"
in project WordsMan.
"""

from __future__ import annotations

from srt_search.config import Settings, get_settings
from srt_search.models import SearchCandidate
from srt_search.providers.base import ProviderNotImplementedError, SearchProvider

_STUB_MSG = (
    "gestdown provider is a stub — implementation is tracked as "
    "'srt-search: implement Gestdown provider' (project WordsMan)"
)


class GestdownProvider(SearchProvider):
    name = "gestdown"
    implemented = False

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def search(
        self, movie: str, year: int | None = None, limit: int = 10
    ) -> list[SearchCandidate]:
        raise ProviderNotImplementedError(_STUB_MSG)

    async def download(self, candidate_id: str) -> tuple[str, bytes]:
        raise ProviderNotImplementedError(_STUB_MSG)
