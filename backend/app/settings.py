from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AgentCircle API"
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "agentcircle"
    use_mock_mongodb: bool = False
    frontend_origin: str = "http://localhost:5173"

    # Auth. jwt_secret has a dev default so the local prototype boots without setup;
    # any non-local deployment must override it.
    jwt_secret: SecretStr = SecretStr("dev-only-insecure-secret-change-me")
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60 * 24 * 14

    # Persona ingestion.
    max_upload_bytes: int = 8 * 1024 * 1024
    max_source_characters: int = 120_000
    chunk_characters: int = 1_200
    chunk_overlap_characters: int = 180
    url_fetch_timeout_seconds: float = 15.0

    # Embeddings. "local" is a deterministic no-network fallback for tests and
    # keyless development; it is not semantically meaningful.
    # "mongodb" serves the same Voyage models through ai.mongodb.com, billed to an Atlas
    # org — it shares a vector space with "voyage", so switching needs no re-embed.
    embedding_provider: Literal["voyage", "mongodb", "openai", "local"] = "local"
    embedding_model: str = "voyage-4"
    embedding_dimensions: int = 1024
    voyage_api_key: SecretStr | None = None
    mongodb_ai_api_key: SecretStr | None = None

    # Deep research (F7). Without it the surface reports itself off rather than
    # returning an empty brief that reads as "nothing found".
    exa_api_key: SecretStr | None = None
    research_daily_budget_usd: float = 2.0

    # Cross-encoder reranking over the fused candidate set. Reads the query and the
    # candidate text together, which is what rank-only fusion cannot do. Needs the
    # Voyage key; without one it is a no-op that reports itself as off.
    rerank_enabled: bool = True
    rerank_model: str = "rerank-2.5"
    rerank_candidates: int = 20

    llm_provider: Literal["openrouter", "openai", "fireworks"] = "openrouter"
    llm_model: str = "openai/gpt-5.6-luna"
    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    fireworks_api_key: SecretStr | None = None
    agent_fallback_enabled: bool = True
    agent_timeout_seconds: float = 45.0
    langsmith_project: str = "agentcircle"


@lru_cache
def get_settings() -> Settings:
    return Settings()
