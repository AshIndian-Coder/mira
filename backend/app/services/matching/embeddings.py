from collections.abc import Iterable
from functools import lru_cache
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer


MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME, device="cpu")


class EmbeddingCache:
    """
    Scoped in-memory embedding cache for a matching batch or request.

    Precomputes or lazily caches normalized MiniLM embeddings for unique texts
    so that repeated material descriptions are encoded at most once.
    """

    def __init__(self, initial_embeddings: dict[str, np.ndarray] | None = None):
        self._cache: dict[str, np.ndarray] = dict(initial_embeddings) if initial_embeddings else {}

    def get(self, text: str) -> np.ndarray | None:
        return self._cache.get(text)

    def set(self, text: str, embedding: np.ndarray) -> None:
        self._cache[text] = embedding

    def precompute(self, texts: Iterable[str], batch_size: int = 64) -> None:
        missing = [t for t in set(texts) if t and t not in self._cache]
        if missing:
            model = get_embedding_model()
            embeddings = model.encode(
                missing,
                batch_size=batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            for text, emb in zip(missing, embeddings):
                self._cache[text] = emb

    def get_or_encode(self, text: str) -> np.ndarray | None:
        if not text:
            return None
        if text not in self._cache:
            model = get_embedding_model()
            self._cache[text] = model.encode(
                text,
                normalize_embeddings=True,
            )
        return self._cache[text]

    def similarity(self, left: str, right: str) -> float:
        if not left or not right:
            return 0.0

        vec_a = self.get_or_encode(left)
        vec_b = self.get_or_encode(right)

        if vec_a is None or vec_b is None:
            return 0.0

        sim = float(vec_a @ vec_b)
        return max(0.0, min(1.0, sim))

    def clear(self) -> None:
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, text: str) -> bool:
        return text in self._cache


def precompute_embeddings(
    texts: Iterable[str],
    batch_size: int = 64,
) -> EmbeddingCache:
    """Convenience factory to precompute embeddings for a collection of texts into a new scoped cache."""
    cache = EmbeddingCache()
    cache.precompute(texts, batch_size=batch_size)
    return cache


def generate_embedding(text: str) -> list[float]:
    if not text:
        return []

    model = get_embedding_model()

    embedding = model.encode(
        text,
        normalize_embeddings=True,
    )

    return embedding.tolist()


def semantic_similarity(
    left: str,
    right: str,
    embedding_cache: EmbeddingCache | None = None,
) -> float:
    if not left or not right:
        return 0.0

    if embedding_cache is not None:
        return embedding_cache.similarity(left, right)

    model = get_embedding_model()

    embeddings = model.encode(
        [left, right],
        normalize_embeddings=True,
    )

    similarity = float(embeddings[0] @ embeddings[1])

    return max(0.0, min(1.0, similarity))
