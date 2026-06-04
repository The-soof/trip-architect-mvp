from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

import json

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Resolve .env by absolute path so it loads no matter what directory uvicorn is
# launched from. The repo root is the canonical home (where .env.example lives);
# a backend/.env, if present, overrides it.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "Trip Architect"
    app_env: Literal["development", "test", "production"] = "development"
    api_prefix: str = "/api"
    database_url: str = "sqlite:///./trip_architect.db"
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    # NoDecode: hand the raw env string to parse_cors_origins instead of JSON-decoding it,
    # so a plain comma-separated CORS_ORIGINS in .env is accepted.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    enable_real_agent: bool = True
    # Temporary safeguard: Tavily usage is running hot, so keep the MVP in a low-search mode
    # until we intentionally raise the cap again.
    fast_mvp_mode: bool = True
    fast_mvp_search_limit: int = 3
    gemini_model: str = "gemini-2.5-flash"
    gemini_api_key: str | None = None
    google_places_api_key: str | None = None
    tavily_api_key: str | None = None
    default_trip_strategy: Literal["balance", "cheapest", "experience"] = "balance"

    # Travel-journey data layer.
    # SerpApi (Google Flights engine) supplies accurate flight times/stops/price.
    # Travelpayouts supplies affiliate deep links. Both are optional — when a key is
    # absent the journey builder transparently falls back to the deterministic
    # generator, so the feature always works with no keys configured.
    serpapi_api_key: str | None = None
    travelpayouts_token: str | None = None
    travelpayouts_marker: str | None = None
    # Hard safety cap so the SerpApi free tier (100 searches/mo) is never blown
    # during development. When the in-process counter reaches the cap the builder
    # stops calling SerpApi and falls back to the generator for the rest of the month.
    serpapi_monthly_cap: int = 90

    @computed_field  # type: ignore[prop-decorator]
    @property
    def serpapi_enabled(self) -> bool:
        return bool(self.serpapi_api_key)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def travelpayouts_enabled(self) -> bool:
        return bool(self.travelpayouts_token and self.travelpayouts_marker)

    model_config = SettingsConfigDict(
        env_file=(str(_REPO_ROOT / ".env"), str(_BACKEND_ROOT / ".env")),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: list[str] | str) -> list[str]:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return json.loads(stripped)
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
