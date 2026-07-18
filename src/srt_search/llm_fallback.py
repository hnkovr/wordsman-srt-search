"""LLM-CLI fallback for subtitle search: when every deterministic provider returns
nothing, ask a local LLM CLI (claude -p → codex exec → gemini -p) to disambiguate the
title — correct spelling/year, canonical + alternate titles, IMDb id, and whether the
film is likely subtitled yet — then the aggregator retries the search with that hint.

The subprocess is the only side effect and is injectable (``runner=``) so tests never
spawn a real CLI. Mirrors the translation llm_cli provider in the wordsman parent.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess  # nosec B404 - fixed argv, no shell
import sys
from dataclasses import dataclass, field

from srt_search.config import Settings, get_settings
from srt_search.logger import log

_CLI_COMMANDS = {
    "claude": lambda prompt, model: [
        "claude",
        *(["--model", model] if model else []),
        "-p",
        prompt,
    ],
    "codex": lambda prompt, model: ["codex", "exec", prompt],
    "gemini": lambda prompt, model: ["gemini", "-p", prompt],
}
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def _extract_json_object(raw: str) -> dict | None:
    fenced = _JSON_FENCE_RE.search(raw)
    if fenced:
        raw = fenced.group(1)
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        payload = json.loads(raw[start : end + 1])
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


@dataclass
class QuerySuggestion:
    title: str | None = None
    year: int | None = None
    imdb_id: str | None = None
    alternate_titles: list[str] = field(default_factory=list)
    likely_subtitled: bool = True
    note: str = ""

    def queries(self, original: str) -> list[str]:
        """Distinct retry titles, best first, always including the original."""
        seen: list[str] = []
        for candidate in [self.title, *self.alternate_titles, original]:
            c = (candidate or "").strip()
            if c and c.lower() not in {s.lower() for s in seen}:
                seen.append(c)
        return seen


def _build_prompt(movie: str, year: int | None) -> str:
    return (
        "You are a film-metadata resolver for a subtitle search tool.\n"
        f"The query {movie!r}{f' ({year})' if year else ''} returned no subtitles.\n"
        "Identify the intended film and reply with ONLY a JSON object:\n"
        '{"title": "canonical English title", "year": <int or null>, '
        '"imdb_id": "tt... or null", "alternate_titles": ["..."], '
        '"likely_subtitled": <true|false>, "note": "one short sentence"}\n'
        "Set likely_subtitled=false for films too new/obscure to have subtitles yet. "
        "No prose, no code fences."
    )


def _run_cli(cli: str, prompt: str, model: str | None, timeout: float) -> str | None:
    try:
        proc = subprocess.run(  # nosec B603 - fixed argv, no shell
            _CLI_COMMANDS[cli](prompt, model),
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"llm_fallback: {cli} failed: {exc}", file=sys.stderr)
        return None
    return proc.stdout if proc.returncode == 0 else None


def suggest_query(
    movie: str,
    year: int | None = None,
    *,
    settings: Settings | None = None,
    runner=None,
) -> QuerySuggestion | None:
    """Ask the LLM CLI chain to disambiguate a movie title; None if none available."""
    settings = settings or get_settings()
    chain = (
        list(settings.llm_fallback_chain)
        if runner
        else [c for c in settings.llm_fallback_chain if shutil.which(c)]
    )
    if not chain:
        log.warning("llm_fallback: no LLM CLI on PATH ({})", ", ".join(settings.llm_fallback_chain))
        return None
    call = runner or (
        lambda cli, prompt: _run_cli(
            cli, prompt, settings.llm_model or None, settings.request_timeout
        )
    )
    prompt = _build_prompt(movie, year)
    for cli in chain:
        payload = _extract_json_object(call(cli, prompt) or "")
        if payload is None:
            continue
        return QuerySuggestion(
            title=payload.get("title") or None,
            year=payload.get("year") if isinstance(payload.get("year"), int) else None,
            imdb_id=payload.get("imdb_id") or None,
            alternate_titles=[
                t for t in (payload.get("alternate_titles") or []) if isinstance(t, str)
            ],
            likely_subtitled=bool(payload.get("likely_subtitled", True)),
            note=str(payload.get("note") or ""),
        )
    return None
