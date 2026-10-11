from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read from PHI_* environment variables, e.g. PHI_SCORE_THRESHOLD=0.6."""

    model_config = SettingsConfigDict(env_prefix="PHI_", extra="ignore")

    # Server. Listens on this machine only by default.
    host: str = "127.0.0.1"
    port: int = Field(default=8765, gt=0, lt=65536)
    # Where connectors (the Claude Code hook) reach the service; empty means the local server.
    service_url: str = ""
    # "warn": a helper that flags likely PHI and lets the user proceed (default for now).
    # "block": enforcement; PHI and anything that cannot be checked is blocked (fail closed).
    mode: Literal["warn", "block"] = "warn"

    # NER model, pinned to a fixed revision
    ner_model: str = "StanfordAIMI/stanford-deidentifier-base"
    ner_model_revision: str = "661b9c1c717d3165512d440abc3700c386aefab6"
    # Minimum confidence for detector findings; domain rules always apply.
    score_threshold: float = Field(default=0.5, ge=0, le=1)
    max_concurrent_scans: int = Field(default=1, gt=0)

    # Files
    max_file_bytes: int = Field(default=25 * 1024 * 1024, gt=0)
    # The NER model reads about 3,500 characters per second on CPU: 50,000 is roughly 15 seconds.
    max_file_text_chars: int = Field(default=50_000, gt=0)
    max_pdf_pages: int = Field(default=50, gt=0)

    @property
    def client_url(self) -> str:
        return self.service_url or f"http://{self.host}:{self.port}"


def create_settings() -> Settings:
    return Settings()
