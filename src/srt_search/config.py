"""Runtime settings; precedence: init kwargs > env > .env > config/config.yml > defaults."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import (
    BaseSettings,
    NoDecode,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

CONFIG_YML = Path(__file__).resolve().parents[2] / "config" / "config.yml"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SRT_SEARCH_",
        env_file=".env",
        yaml_file=CONFIG_YML,
        extra="ignore",
    )

    log_level: str = "INFO"
    language: str = "en"
    providers: Annotated[list[str], NoDecode] = ["podnapisi"]
    download_dir: Path = Path("downloads")
    request_timeout: float = 30.0
    user_agent: str = "wordsman-srt-search/0.6.0"
    # some resources (yify zip endpoint) 403 non-browser agents without a referer
    browser_user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )

    podnapisi_base_url: str = "https://www.podnapisi.net"
    yify_base_url: str = "https://yifysubtitles.ch"
    gestdown_base_url: str = "https://api.gestdown.info"
    imdb_suggest_url: str = "https://v3.sg.media-imdb.com/suggestion/x"
    kinopoisk_base_url: str = "https://www.kinopoisk.ru"
    # LLM-CLI fallback when every deterministic provider returns nothing
    llm_fallback_chain: Annotated[list[str], NoDecode] = ["claude", "codex", "gemini"]
    llm_model: str | None = None
    # dual / bilingual subtitle sources (see config.yml `dual_subtitle_sources` for the
    # annotated catalog: which are free/keyless vs. account-gated browser-assisted)
    doublesubs_app_url: str = "https://app.doublesubs.com"
    subtitlecat_base_url: str = "https://www.subtitlecat.com"
    # Subtitlecat hosts ONE entry per release and generates each language on demand, so a
    # title that matches the search may still have no track in `language`. Verifying costs
    # one detail-page GET per candidate but keeps unusable results out of the list — see
    # SubtitlecatProvider.search. English is the source language and never verified.
    subtitlecat_verify_language: bool = True
    subtitlecat_verify_max: int = 12  # ceiling on those extra GETs per search
    downsub_base_url: str = "https://downsub.com"
    subtitle_edit_online_url: str = "https://www.nikse.dk/subtitleedit/online"

    @field_validator("providers", "llm_fallback_chain", mode="before")
    @classmethod
    def split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
