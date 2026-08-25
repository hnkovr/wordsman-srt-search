"""Click CLI: list providers, search candidates, download the best or a chosen SRT."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click

from srt_search import __version__
from srt_search.aggregator import download_candidate, resolve_providers, search_all
from srt_search.config import get_settings
from srt_search.logger import log
from srt_search.models import SearchCandidate
from srt_search.providers import REGISTRY
from srt_search.providers.base import ProviderError
from srt_search.utils import best_candidate, safe_download_path


def _parse_providers(providers: str | None) -> list[str] | None:
    if not providers:
        return None
    return [name.strip() for name in providers.split(",") if name.strip()]


@click.group()
@click.version_option(version=__version__, prog_name="srt-search")
def main() -> None:
    """Find English SRT subtitles for a selected movie across known resources."""


@main.command()
def providers() -> None:
    """List registered providers and their implementation status."""
    for name, provider_cls in sorted(REGISTRY.items()):
        status = "implemented" if provider_cls.implemented else "stub"
        click.echo(f"{name}\t{status}")


@main.command(name="resolve-kp")
@click.argument("url")
def resolve_kp(url: str) -> None:
    """Resolve a kinopoisk film URL to movie identification JSON."""
    from srt_search.kinopoisk import resolve_kinopoisk_url  # lazy: keeps startup light

    movie = resolve_kinopoisk_url(url)
    payload = movie.model_dump()
    payload["search_title"] = movie.search_title
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@main.command(name="open-doublesubs")
@click.option("--query", default=None, help="Movie title to carry into the app")
@click.option("--print-url", is_flag=True, help="Print the URL instead of opening a browser")
def open_doublesubs_cmd(query: str | None, print_url: bool) -> None:
    """Open DoubleSubs (browser-assisted dual-sub source) for interactive authorize + build."""
    from srt_search.doublesubs import build_doublesubs_url, open_doublesubs  # lazy: GUI dep

    if print_url:
        click.echo(build_doublesubs_url(query))
        return
    click.echo(open_doublesubs(query))


@main.command()
@click.argument("movie")
@click.option("--year", type=int, default=None)
@click.option("--limit", type=int, default=10)
@click.option("--providers", "provider_names", default=None, help="Comma-separated provider names")
@click.option(
    "--llm-fallback", is_flag=True, help="Ask an LLM CLI to disambiguate if nothing found"
)
def find(
    movie: str, year: int | None, limit: int, provider_names: str | None, llm_fallback: bool
) -> None:
    """Print merged subtitle candidates for MOVIE as JSON."""
    selected = resolve_providers(_parse_providers(provider_names))
    result = asyncio.run(
        search_all(movie, year=year, limit=limit, providers=selected, llm_fallback=llm_fallback)
    )
    click.echo(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))


@main.command()
@click.argument("movie")
@click.option("--year", type=int, default=None)
@click.option("--out", type=click.Path(path_type=Path), default=None, help="Target directory")
@click.option("--providers", "provider_names", default=None, help="Comma-separated provider names")
@click.option(
    "--llm-fallback", is_flag=True, help="Ask an LLM CLI to disambiguate if nothing found"
)
def get(
    movie: str,
    year: int | None,
    out: Path | None,
    provider_names: str | None,
    llm_fallback: bool,
) -> None:
    """Download the best English SRT for MOVIE; print the saved path (last line)."""

    async def _get() -> Path:
        selected = resolve_providers(_parse_providers(provider_names))
        result = await search_all(
            movie, year=year, limit=10, providers=selected, llm_fallback=llm_fallback
        )
        candidate = best_candidate(result.candidates)
        if candidate is None:
            raise click.ClickException(f"no subtitles found for {movie!r}")
        file_name, content = await download_candidate(candidate)
        target = safe_download_path(out or get_settings().download_dir, file_name)
        target.write_bytes(content)
        log.info("saved {} from {} ({} bytes)", target, candidate.provider, len(content))
        return target

    click.echo(str(asyncio.run(_get())))


@main.command()
@click.argument("provider_name", metavar="PROVIDER")
@click.argument("candidate_id")
@click.option("--out", type=click.Path(path_type=Path), default=None, help="Target directory")
@click.option("--name", "file_name", default=None, help="Preferred file name for the saved SRT")
@click.option("--json", "as_json", is_flag=True, help="Print {path,file_name,bytes} as JSON")
def fetch(
    provider_name: str,
    candidate_id: str,
    out: Path | None,
    file_name: str | None,
    as_json: bool,
) -> None:
    """Download ONE candidate already chosen by the caller: PROVIDER and its CANDIDATE_ID.

    `get` searches and then picks the most-downloaded candidate itself. `fetch` skips the
    search: the pair identifying the candidate comes from a previous `find`, so the choice
    belongs to whoever ran it (a bot's inline button, a picker UI, a script). Language
    follows SRT_SEARCH_LANGUAGE exactly as `find` does — a candidate listed by a RU search
    may still have no RU track, and that fails loudly rather than saving an English file.
    """

    async def _fetch() -> tuple[Path, bytes]:
        candidate = SearchCandidate(provider=provider_name, candidate_id=candidate_id)
        try:
            name, content = await download_candidate(candidate)
        except (ProviderError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        target = safe_download_path(out or get_settings().download_dir, file_name or name)
        target.write_bytes(content)
        log.info("saved {} from {} ({} bytes)", target, provider_name, len(content))
        return target, content

    target, content = asyncio.run(_fetch())
    if as_json:
        payload = {"path": str(target), "file_name": target.name, "bytes": len(content)}
        click.echo(json.dumps(payload, ensure_ascii=False))
    else:
        click.echo(str(target))


if __name__ == "__main__":
    main()
