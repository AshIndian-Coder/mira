"""Application configuration.

All runtime configuration is loaded from environment variables (optionally
from a local ``.env`` file). See ``.env.example`` for the full list.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings (12-factor style)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------ #
    # Application
    # ------------------------------------------------------------------ #
    PROJECT_NAME: str = "MIRA - National Unified Material Master Framework"
    APP_NAME: str = "MIRA Backend"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    BASE_DESCRIPTION: str = (
        "AI-powered material master harmonization for CPSEs: matching, "
        "standardization, CNMC generation, mapping, ROI, audit and SAP sync."
    )

    # ------------------------------------------------------------------ #
    # Security
    # ------------------------------------------------------------------ #
    SECRET_KEY: str = "change-me-to-a-long-random-string"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    # ------------------------------------------------------------------ #
    # PostgreSQL
    # ------------------------------------------------------------------ #
    DATABASE_URL: str = (
        "postgresql+psycopg2://postgres:postgres@localhost:5432/material_master"
    )

    # ------------------------------------------------------------------ #
    # Milvus vector database
    # ------------------------------------------------------------------ #
    MILVUS_URI: str = "http://localhost:19530"
    MILVUS_COLLECTION: str = "material_embeddings"
    EMBEDDING_DIM: int = 1536  # frozen: locked to Qwen-1B-Embedding output

    # ------------------------------------------------------------------ #
    # Qwen-1B-Embedding
    # ------------------------------------------------------------------ #
    # auto    -> use Qwen if available, else deterministic hashing embedder
    # qwen    -> force Qwen (raises if unavailable)
    # hashing -> force deterministic fallback (no torch/transformers needed)
    EMBEDDING_BACKEND: str = "auto"
    QWEN_MODEL_PATH: str = "models/qwen_quantized"
    QWEN_BASE_MODEL: str = "Qwen/Qwen-1B-Embedding"
    QWEN_BATCH_SIZE: int = 32

    # ------------------------------------------------------------------ #
    # MIRA matching parameters
    # The formula SHAPE is frozen: final = 0.20*text + 0.20*semantic +
    # 0.35*specification + 0.15*material_grade + 0.10*other_attributes.
    # Numeric weights may be tuned on DEV only.
    # ------------------------------------------------------------------ #
    HIGH_CONFIDENCE_THRESHOLD: float = 0.85
    DIFFERENT_THRESHOLD: float = 0.45
    VECTOR_TOP_K: int = 100

    WEIGHT_TEXT: float = 0.20
    WEIGHT_SEMANTIC: float = 0.20
    WEIGHT_SPECIFICATION: float = 0.35
    WEIGHT_MATERIAL_GRADE: float = 0.15
    WEIGHT_OTHER_ATTRIBUTES: float = 0.10

    # ------------------------------------------------------------------ #
    # ROI / savings calculator assumptions
    # ------------------------------------------------------------------ #
    BULK_DISCOUNT_RATE: float = 0.08      # savings from demand aggregation
    CARRYING_COST_RATE: float = 0.20      # annual inventory carrying cost
    SAFETY_STOCK_DAYS: int = 30           # assumed days of safety stock

    # ------------------------------------------------------------------ #
    # SAP integration
    # ------------------------------------------------------------------ #
    SAP_SIMULATE: bool = True             # demo mode: deterministic sample data
    SAP_ASYNC_MODE: str = "standard"

    # ------------------------------------------------------------------ #
    # Seed data (created idempotently on startup)
    # ------------------------------------------------------------------ #
    SEED_ADMIN_EMAIL: str = "admin@mira.gov.in"
    SEED_ADMIN_PASSWORD: str = "Admin@123"

    # ------------------------------------------------------------------ #
    # Logging
    # ------------------------------------------------------------------ #
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/app.log"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors(cls, value):
        """Allow 'a,b,c' style environment values for CORS_ORIGINS."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def cors_origins(self) -> List[str]:
        return list(self.CORS_ORIGINS)


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (importable as ``from app.config import settings``)."""
    return Settings()


settings = get_settings()

