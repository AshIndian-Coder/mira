"""
Application configuration settings.

This module loads configuration from environment variables using Pydantic Settings.
All configuration should be accessed through the `settings` singleton.

Environment variables can be set in a `.env` file or in the system environment.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    secret_key: str = "change-me-to-a-long-random-string"
    access_token_expire_minutes: int = 1440
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/material_master"

    milvus_uri: str = "http://localhost:19530"
    milvus_collection: str = "material_embeddings"
    embedding_dim: int = 1536

    embedding_backend: str = "auto"
    qwen_model_path: str = "models/qwen_quantized"
    qwen_batch_size: int = 32

    high_confidence_threshold: float = 0.85
    different_threshold: float = 0.45
    vector_top_k: int = 100
    weight_text: float = 0.20
    weight_semantic: float = 0.20
    weight_specification: float = 0.35
    weight_material_grade: float = 0.15
    weight_other_attributes: float = 0.10

    bulk_discount_rate: float = 0.08
    carrying_cost_rate: float = 0.20
    safety_stock_days: int = 30

    sap_simulate: bool = True

    seed_admin_email: str = "admin@mira.gov.in"
    seed_admin_password: str = "Admin@123"

    log_level: str = "INFO"
    log_file: str = "logs/app.log"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
