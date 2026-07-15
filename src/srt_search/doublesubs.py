"""DoubleSubs (app.doublesubs.com) — a browser-assisted bilingual-subtitle source.

DoubleSubs is a paid, account-gated web app (Stripe + api-v2.doublesubs.com) with no
public keyless API, so it cannot be a headless provider like yify/podnapisi. Instead
it is exposed as a *browser-assisted* source: `open_doublesubs()` launches the app in
the user's default browser (macOS `open` / Linux `xdg-open`) so they authorize and
build the dual-sub interactively. The URL builder is pure and testable; the GUI launch
is the only side effect.
"""

from __future__ import annotations

import subprocess  # nosec B404 - fixed argv GUI opener, no shell
import sys
from urllib.parse import urlencode

from srt_search.config import Settings, get_settings
from srt_search.logger import log


def build_doublesubs_url(query: str | None = None, settings: Settings | None = None) -> str:
    """Build the DoubleSubs app URL, optionally carrying a movie title as a query.

    >>> build_doublesubs_url()
    'https://app.doublesubs.com'
    >>> build_doublesubs_url("A Beautiful Mind")
    'https://app.doublesubs.com/?q=A+Beautiful+Mind'
    """
    settings = settings or get_settings()
    base = settings.doublesubs_app_url.rstrip("/")
    if not query:
        return base
    return f"{base}/?{urlencode({'q': query})}"


def _gui_open(url: str) -> list[str]:
    """Platform GUI-open argv (macOS `open`, else `xdg-open`)."""
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    return [opener, url]


def open_doublesubs(
    query: str | None = None,
    *,
    settings: Settings | None = None,
    opener=None,
) -> str:
    """Open DoubleSubs in the default browser for interactive auth + dual-sub build.

    Returns the launched URL. ``opener`` (a callable taking the URL) is injectable so
    tests never spawn a real browser.
    """
    url = build_doublesubs_url(query, settings)
    launch = opener or _default_opener
    launch(url)
    log.info("opened DoubleSubs in browser: {}", url)
    return url


def _default_opener(url: str) -> None:  # pragma: no cover - launches a real GUI browser
    subprocess.run(_gui_open(url), check=True)  # nosec B603 - fixed argv, no shell
