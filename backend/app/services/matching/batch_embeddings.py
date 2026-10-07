from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from app.services.matching.embeddings import EmbeddingCache, EMBED_BATCH_SIZE

DEFAULT_BATCH_SIZE = EMBED_BATCH_SIZE


def generate_embeddings(
    texts: Iterable[str],
    batch_size: int = DEFAULT_BATCH_SIZE,
    model_name: str | None = None,
) -> dict[str, list[float]]:
    unique_texts = list(
        dict.fromkeys(
            " ".join(text.split()).strip()
            for text in texts
            if isinstance(text, str) and text.strip()
        )
    )

    if not unique_texts:
        return {}

    cache = EmbeddingCache(model_name=model_name)
    effective_batch_size = max(1, min(int(batch_size), EMBED_BATCH_SIZE))
    cache.precompute(
        unique_texts,
        batch_size=effective_batch_size,
        model_name=model_name,
    )

    result: dict[str, list[float]] = {}
    for text in unique_texts:
        embedding = cache.get(text, model_name=model_name)
        if embedding is None:
            raise RuntimeError(f"Missing embedding for text: {text[:80]}")
        vector = np.asarray(embedding, dtype=np.float32)
        if vector.shape != (1024,):
            raise RuntimeError(
                f"Invalid embedding shape for text: {text[:80]}: {vector.shape}"
            )
        result[text] = vector.astype(float).tolist()

    return result
