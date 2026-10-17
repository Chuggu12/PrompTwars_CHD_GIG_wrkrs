"""Runtime settings, read once from the environment (see .env.example)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    """Immutable application settings. Secrets are SecretStr so they never print."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    env: Literal["development", "production", "test"] = "development"
    gemini_api_key: SecretStr | None = None
    model_chain: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    allowed_hosts: str = "localhost,127.0.0.1,testserver,*.run.app"
    trust_proxy: bool = True
    report_quorum: int = 3
    auto_apply: Literal["on", "off"] = "off"
    github_repo: str | None = None
    github_token: SecretStr | None = None

    @property
    def models(self) -> list[str]:
        """Ordered model fallback chain from MODEL_CHAIN."""
        return _split_csv(self.model_chain)

    @property
    def hosts(self) -> list[str]:
        return _split_csv(self.allowed_hosts) or ["localhost"]

    @property
    def api_key(self) -> str | None:
        return self.gemini_api_key.get_secret_value() if self.gemini_api_key else None

    @property
    def github_enabled(self) -> bool:
        return bool(self.github_repo and self.github_token)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return Settings()
