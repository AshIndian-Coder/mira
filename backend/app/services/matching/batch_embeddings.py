"""
Batch embedding utilities for MIRA.

Encodes multiple material descriptions in batch using the authoritative
SentenceTransformer embedding model (defaulting to the 1024D Qwen INT8 model).
Duplicate descriptions are deduplicated so each unique string is encoded only once.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np

from app.services.matching.embeddings import (
    get_embedding_model,
    resolve_model_name,
)

DEFAULT_BATCH_SIZE = 64


def generate_embeddings(
    texts: Iterable[str],
    batch_size: int = DEFAULT_BATCH_SIZE,
    model_name: str | None = None,
) -> dict[str, list[float]]:
    """
    Generate normalized embeddings for unique non-empty descriptions in batch.

    Returns a mapping of {description: embedding_vector_as_list}.
    """
    unique_texts = list(
        dict.fromkeys(
            str(text).strip()
            for text in texts
            if text and str(text).strip()
        )
    )

    if not unique_texts:
        return {}

    resolved_model = resolve_model_name(model_name)
    model = get_embedding_model(resolved_model)

    embeddings = model.encode(
        unique_texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    vectors = (
        embeddings
        if isinstance(embeddings, np.ndarray)
        else np.asarray(embeddings)
    )

    return {
        text: vector.astype(float).tolist()
        for text, vector in zip(unique_texts, vectors)
    }
