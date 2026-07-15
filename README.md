# wordsman-srt-search

Multi-provider **search library + CLI** for English SRT subtitles of a selected movie.
Autonomous subproduct of [wordsman](https://github.com/hnkovr/wordsman) (consumed there as the
`subproducts/srt-search` git submodule) with no dependency on the parent repo; also consumed by
[wordsman-srt-api](https://github.com/hnkovr/wordsman-srt-api) as its multi-provider search engine.

## Providers ("known resources")

| Provider | Status | Auth | Notes |
| --- | --- | --- | --- |
| `podnapisi` | **implemented** | keyless | JSON search on podnapisi.net; downloads unpacked from ZIP |
| `yify` | **implemented** | keyless | IMDb suggest → yifysubtitles movie page → ZIP; movies only |
| `gestdown` | stub | keyless | TODO — tracked as "srt-search: implement Gestdown provider" (WordsMan) |

### Dual / bilingual subtitle sources

Beyond single-language providers, `config/config.yml` catalogs dual-subtitle sources
(`dual_subtitle_sources`):

| Source | Access | Free | How |
| --- | --- | --- | --- |
| `doublesubs` | browser | no | `srt-search open-doublesubs [--query TITLE]` opens the app for interactive authorize + build (Stripe-gated; no public API) |
| `subtitlecat` | keyless | yes | auto-translates subs to many languages — candidate for a real provider |
| `downsub` | keyless | yes | downloads + translates subs (YouTube/Viki/…) |
| `subtitle_edit_online` | browser | yes | free in-browser tool to merge two tracks by hand |

For a fully local EN+RU merge use the parent repo's `python3 main.py bilingual`.

All providers implement one `SearchProvider` interface
([`src/srt_search/providers/base.py`](src/srt_search/providers/base.py)); the aggregator
([`src/srt_search/aggregator.py`](src/srt_search/aggregator.py)) fans out concurrently, collects
per-provider failures without hiding partial results, and raises only when every provider fails.

## Quickstart

```bash
make install                 # uv sync --group dev
just providers               # podnapisi  implemented / yify  implemented / gestdown  stub
just find "Dune" 2021        # merged candidates as JSON
just get "Dune" 2021 subs/   # download best English SRT, prints saved path

# identify a movie from a kinopoisk URL (title/original_title/year as JSON):
uv run srt-search resolve-kp "https://www.kinopoisk.ru/film/10355286/"
```

Language: set `SRT_SEARCH_LANGUAGE=ru` (or any code a provider knows) to search
non-English tracks.

Provider endpoint shapes are not contractually stable — `just probe-live` checks
`podnapisi` against the real site (network; never run in CI).

## Configuration

Precedence: env (`SRT_SEARCH_*`) > `.env` > [`config/config.yml`](config/config.yml) > defaults.
Key settings: `SRT_SEARCH_PROVIDERS` (comma-separated, default `podnapisi`),
`SRT_SEARCH_LANGUAGE` (default `en`), `SRT_SEARCH_DOWNLOAD_DIR` (default `./downloads`).
No secrets: current providers are keyless.

## Library use (how srt-api consumes it)

```python
from srt_search.aggregator import search_all, download_candidate

result = await search_all("Dune", year=2021, limit=10)   # SearchResult(candidates, failures)
file_name, content = await download_candidate(result.candidates[0])
```

## Development

```bash
make test    # offline pytest suite (respx-mocked HTTP), coverage gate >=85%
make lint    # ruff check + format check
```

Adding a provider: subclass `SearchProvider` in `src/srt_search/providers/<name>.py`,
register it in `providers/__init__.py:REGISTRY`, add respx tests. Stubs raise
`ProviderNotImplementedError` with a pointer to their tracker task.
