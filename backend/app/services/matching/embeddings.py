import os
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"
TRAINED_MODEL_PATH = Path(__file__).resolve().parents[4] / "models" / "trained" / "minilm_cpse_v1"
QWEN_MODEL_PATH = Path("/home/shikhar/mira-model-test/Mira.ai")


def resolve_model_name(name_or_alias: str | None = None) -> str:
    """
    Resolve model alias or environment variable into a valid model path or identifier.

    Supported aliases:
      - 'qwen': fine-tuned Qwen INT8 checkpoint
      - 'minilm': fine-tuned MiniLM checkpoint if available, else all-MiniLM-L6-v2
      - 'base-minilm' / 'base_minilm': all-MiniLM-L6-v2
    """
    target = name_or_alias if name_or_alias is not None else os.getenv("MIRA_EMBEDDING_MODEL", "")
    target = target.strip()
    if not target:
        if TRAINED_MODEL_PATH.exists() and (TRAINED_MODEL_PATH / "model.safetensors").exists():
            return str(TRAINED_MODEL_PATH)
        return DEFAULT_MODEL_NAME

    target_lower = target.lower()
    if target_lower == "qwen":
        if QWEN_MODEL_PATH.exists():
            return str(QWEN_MODEL_PATH)
        return "qwen"
    elif target_lower == "minilm":
        if TRAINED_MODEL_PATH.exists() and (TRAINED_MODEL_PATH / "model.safetensors").exists():
            return str(TRAINED_MODEL_PATH)
        return DEFAULT_MODEL_NAME
    elif target_lower in ("base-minilm", "base_minilm"):
        return DEFAULT_MODEL_NAME

    return target


def get_embedding_model_name() -> str:
    return resolve_model_name()


@lru_cache(maxsize=4)
def _load_model(target: str) -> SentenceTransformer:
    return SentenceTransformer(target, device="cpu")


def get_embedding_model(model_name: str | None = None) -> SentenceTransformer:
    resolved = resolve_model_name(model_name)
    return _load_model(resolved)


class EmbeddingCache:
    """
    Scoped in-memory embedding cache for a matching batch or request.

    Precomputes or lazily caches normalized embeddings for unique texts
    so that repeated material descriptions are encoded at most once.
    Distinguishes models in the cache key to prevent cross-model cache contamination.
    """

    def __init__(
        self,
        initial_embeddings: dict[str, np.ndarray] | None = None,
        model_name: str | None = None,
    ):
        self.model_name = resolve_model_name(model_name)
        self._cache: dict[tuple[str, str], np.ndarray] = {}
        if initial_embeddings:
            for text, emb in initial_embeddings.items():
                self._cache[(self.model_name, text)] = emb

    def _resolve_model(self, model_name: str | None = None) -> str:
        return resolve_model_name(model_name) if model_name is not None else self.model_name

    def get(self, text: str, model_name: str | None = None) -> np.ndarray | None:
        m = self._resolve_model(model_name)
        return self._cache.get((m, text))

    def set(self, text: str, embedding: np.ndarray, model_name: str | None = None) -> None:
        m = self._resolve_model(model_name)
        self._cache[(m, text)] = embedding

    def precompute(
        self,
        texts: Iterable[str],
        batch_size: int = 64,
        model_name: str | None = None,
    ) -> None:
        m = self._resolve_model(model_name)
        missing = [t for t in set(texts) if t and (m, t) not in self._cache]
        if missing:
            model = get_embedding_model(m)
            embeddings = model.encode(
                missing,
                batch_size=batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            for text, emb in zip(missing, embeddings):
                self._cache[(m, text)] = emb

    def get_or_encode(self, text: str, model_name: str | None = None) -> np.ndarray | None:
        if not text:
            return None
        m = self._resolve_model(model_name)
        key = (m, text)
        if key not in self._cache:
            model = get_embedding_model(m)
            self._cache[key] = model.encode(
                text,
                normalize_embeddings=True,
            )
        return self._cache[key]

    def similarity(self, left: str, right: str, model_name: str | None = None) -> float:
        if not left or not right:
            return 0.0

        vec_a = self.get_or_encode(left, model_name=model_name)
        vec_b = self.get_or_encode(right, model_name=model_name)

        if vec_a is None or vec_b is None:
            return 0.0

        sim = float(vec_a @ vec_b)
        return max(0.0, min(1.0, sim))

    def clear(self) -> None:
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, text: str) -> bool:
        return (self.model_name, text) in self._cache


def precompute_embeddings(
    texts: Iterable[str],
    batch_size: int = 64,
    model_name: str | None = None,
) -> EmbeddingCache:
    """Convenience factory to precompute embeddings for a collection of texts into a new scoped cache."""
    cache = EmbeddingCache(model_name=model_name)
    cache.precompute(texts, batch_size=batch_size, model_name=model_name)
    return cache


def generate_embedding(text: str, model_name: str | None = None) -> list[float]:
    if not text:
        return []

    model = get_embedding_model(model_name)

    embedding = model.encode(
        text,
        normalize_embeddings=True,
    )

    return embedding.tolist()


def semantic_similarity(
    left: str,
    right: str,
    embedding_cache: EmbeddingCache | None = None,
    model_name: str | None = None,
) -> float:
    if not left or not right:
        return 0.0

    if embedding_cache is not None:
        return embedding_cache.similarity(left, right, model_name=model_name)

    model = get_embedding_model(model_name)

    embeddings = model.encode(
        [left, right],
        normalize_embeddings=True,
    )

    similarity = float(embeddings[0] @ embeddings[1])

    return max(0.0, min(1.0, similarity))
