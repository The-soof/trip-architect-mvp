from functools import lru_cache
from typing import Literal

import json

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Trip Architect"
    app_env: Literal["development", "test", "production"] = "development"
    api_prefix: str = "/api"
    database_url: str = "sqlite:///./trip_architect.db"
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])
    enable_real_agent: bool = True
    llm_model: str | None = "google_genai:gemini-3.5-flash"
    google_api_key: str | None = "AIzaSyDWeyMHHWzwz8yVnnw9-p4fIO5EYG3tNnY"
    tavily_api_key: str | None = "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"
    default_trip_strategy: Literal["balance", "cheapest", "experience"] = "balance"

    model_config = SettingsConfigDict(
        env_file=".env",
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
