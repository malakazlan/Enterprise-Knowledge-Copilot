"""Application configuration.

Settings are loaded from environment variables (and an optional ``.env`` file)
via ``pydantic-settings``. Real process environment variables always take
precedence over ``.env`` so container/orchestrator config wins in production.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["local", "dev", "staging", "production"]

_INSECURE_SECRET = "change-me-in-production-use-a-long-random-secret"  # noqa: S105


class Settings(BaseSettings):
    """Strongly-typed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "Enterprise Knowledge Copilot"
    environment: Environment = "local"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    host: str = "0.0.0.0"  # noqa: S104 - binding all interfaces is intended inside containers
    port: int = 8000

    # --- Logging ---
    log_level: str = "INFO"
    log_json: bool = True

    # --- Security ---
    secret_key: SecretStr = SecretStr(_INSECURE_SECRET)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # --- CORS ---
    # NoDecode: accept a plain comma-separated string from .env (the validator
    # splits it) instead of pydantic-settings' default JSON decoding.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    # --- Datastores ---
    database_url: str = "postgresql+asyncpg://ekc:ekc@localhost:5432/ekc"
    redis_url: str = "redis://localhost:6379/0"
    # Apply Alembic migrations on startup. The right default for self-hosted
    # single-node deployments; set false when migrations are run externally
    # (e.g. a deploy job in multi-replica setups).
    auto_migrate: bool = True
    # Directory of the built web app (Next.js static export). When unset, the
    # repo-relative frontend/out is used if present; the console is the fallback.
    frontend_dist: str | None = None

    # --- Storage ---
    storage_dir: str = "./storage"
    max_upload_bytes: int = 50 * 1024 * 1024  # 50 MiB

    # --- Ingestion & retrieval ---
    # Provider selection; local/hashing/memory keep the pipeline runnable with
    # zero external services. Real providers plug in behind the same ports.
    parser_provider: str = "local"
    embedder_provider: str = "hashing"
    vector_store_provider: str = "memory"
    sparse_provider: str = "local-bm25"
    reranker_provider: str = "lexical"
    # CPU-tier OCR for scanned pages/images ("rapidocr" | "none"). A GPU-tier
    # VLM OCR adapter (served via vLLM) plugs into the same port later.
    ocr_provider: str = "rapidocr"
    ocr_render_scale: float = 3.0  # ~216 dpi page rasterization
    ocr_min_line_confidence: float = 0.5
    # "extractive" answers by quoting the most relevant retrieved sentences —
    # fully offline. LLM providers (anthropic/openai/ollama) swap in via config.
    llm_provider: str = "extractive"

    # --- Qdrant (when vector_store_provider=qdrant) ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "ekc_chunks"

    # --- LLM providers (when llm_provider is anthropic/openai/ollama) ---
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-opus-4-8"
    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o-mini"
    # Used when embedder_provider=openai; output is truncated to
    # embedding_dimension via the API's `dimensions` parameter.
    openai_embedding_model: str = "text-embedding-3-small"
    # Ollama/vLLM/LM Studio expose an OpenAI-compatible endpoint.
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "llama3.1"
    embedding_dimension: int = 384
    chunk_size: int = 1200
    chunk_overlap: int = 150
    # When true, ingestion runs inline in the request; when false it is enqueued
    # to Celery. Inline keeps local dev and tests broker-free.
    ingestion_eager: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, value: object) -> object:
        """Allow CORS origins to be provided as a comma-separated string."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: object) -> object:
        if isinstance(value, str):
            return value.upper()
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def sync_database_url(self) -> str:
        """Synchronous DSN (psycopg) for Alembic and other sync tooling."""
        return self.database_url.replace("postgresql+asyncpg", "postgresql+psycopg")

    @model_validator(mode="after")
    def _enforce_production_secret(self) -> Settings:
        """Refuse to boot in production with a weak or default secret."""
        if self.is_production:
            secret = self.secret_key.get_secret_value()
            if secret == _INSECURE_SECRET or len(secret) < 32:
                raise ValueError(
                    "SECRET_KEY must be a strong random value of at least 32 characters "
                    "in production."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance (safe as a FastAPI dependency)."""
    return Settings()


settings = get_settings()
