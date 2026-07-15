# Claude Notes

See [README.md](README.md) for usage and [AGENTS.md](AGENTS.md) for guardrails.

- Provider interface + errors: `src/srt_search/providers/base.py`; registry in
  `providers/__init__.py:REGISTRY` (implemented: podnapisi, yify; stub: gestdown).
- yify flow: IMDb suggest (`imdb_suggest_url`) → `/movie-imdb/<tt>` rows → `/subtitle/<slug>.zip`;
  HTML regexes pinned via `.tmp/probe_yify.sh`.
- kinopoisk resolver: `src/srt_search/kinopoisk.py` (`resolve_kinopoisk_url`, CLI `resolve-kp`) —
  JSON-LD first, og:title fallback; first hit may land on the Yandex SSO interstitial, a second
  GET in the same cookie session unlocks the page; captcha → fail-loud ProviderError.
- subtitlecat: `src/srt_search/providers/subtitlecat.py` — keyless, language-aware (honours
  `SRT_SEARCH_LANGUAGE`): search page → detail page → `id="download_<lang>"` .srt link. This is
  the source for non-English (RU) tracks feeding the parent's `main.py bilingual` 2-in-1.
- doublesubs: `src/srt_search/doublesubs.py` (CLI `open-doublesubs`) — browser-assisted source
  (paid, account-gated, no public API); pure URL builder + injectable GUI opener. Free dual-sub
  sources are cataloged in `config.yml:dual_subtitle_sources` (subtitlecat/downsub keyless).
- Fan-out/merge logic: `src/srt_search/aggregator.py` (`search_all`, `download_candidate`).
- Settings: `src/srt_search/config.py` (`SRT_SEARCH_*` env prefix, comma-list `providers`).
- Podnapisi downloads are ZIP archives — unpacking lives in `providers/podnapisi.py:_extract_srt`.
