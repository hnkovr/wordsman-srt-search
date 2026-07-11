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
    user_agent: str = "wordsman-srt-search/0.1.0"

    podnapisi_base_url: str = "https://www.podnapisi.net"
    yify_base_url: str = "https://yifysubtitles.ch"
    gestdown_base_url: str = "https://api.gestdown.info"

    @field_validator("providers", mode="before")
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
