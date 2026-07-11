# Agent Guardrails

- Autonomous subproduct: never import from or reach into the parent `wordsman` checkout or
  `wordsman-srt-api`; the only contracts are the `SearchProvider` interface and the CLI.
- Tests must stay offline: mock all HTTP with `respx`; live endpoints only via `just probe-live`,
  never in CI.
- Stub providers (`gestdown`) must keep raising `ProviderNotImplementedError` with a
  tracker-task pointer until actually implemented — no silent empty results.
- Scraping providers (`yify`) pin HTML shapes with regexes: when they break, re-probe with
  `.tmp/probe_yify.sh` (temp scripts live in gitignored `.tmp/`) and update tests to match.
- All scalars (base URLs, timeouts, provider list) live in settings/config — never inline them.
- Keep `make test` (coverage >= 85%) and `make lint` green before committing.
- When bumping the version, update `src/srt_search/__init__.py` and `pyproject.toml` together.
