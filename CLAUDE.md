# Claude Notes

See [README.md](README.md) for usage and [AGENTS.md](AGENTS.md) for guardrails.

- Provider interface + errors: `src/srt_search/providers/base.py`; registry in
  `providers/__init__.py:REGISTRY` (implemented: podnapisi; stubs: yify, gestdown).
- Fan-out/merge logic: `src/srt_search/aggregator.py` (`search_all`, `download_candidate`).
- Settings: `src/srt_search/config.py` (`SRT_SEARCH_*` env prefix, comma-list `providers`).
- Podnapisi downloads are ZIP archives — unpacking lives in `providers/podnapisi.py:_extract_srt`.
