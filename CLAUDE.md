# Claude Notes

See [README.md](README.md) for usage and [AGENTS.md](AGENTS.md) for guardrails.

- Provider interface + errors: `src/srt_search/providers/base.py`; registry in
  `providers/__init__.py:REGISTRY` (implemented: podnapisi, yify; stub: gestdown).
- yify flow: IMDb suggest (`imdb_suggest_url`) → `/movie-imdb/<tt>` rows → `/subtitle/<slug>.zip`;
  HTML regexes pinned via `.tmp/probe_yify.sh`.
- kinopoisk resolver: `src/srt_search/kinopoisk.py` (`resolve_kinopoisk_url`, CLI `resolve-kp`) —
  JSON-LD first, og:title fallback; first hit may land on the Yandex SSO interstitial, a second
  GET in the same cookie session unlocks the page; captcha → fail-loud ProviderError.
- Fan-out/merge logic: `src/srt_search/aggregator.py` (`search_all`, `download_candidate`).
- Settings: `src/srt_search/config.py` (`SRT_SEARCH_*` env prefix, comma-list `providers`).
- Podnapisi downloads are ZIP archives — unpacking lives in `providers/podnapisi.py:_extract_srt`.
