from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer


MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"
EMBEDDING_DIM = 1024  # locked to this model output size -- Milvus collection must match

# Description -> vector memo. run-batch scores thousands of PAIRS but only
# touches a few hundred unique descriptions, so without this cache every
# shared text gets re-encoded once per pair it appears in (the old
# semantic_similarity([left, right]) encoding style). With it, each unique
# text costs the model exactly ONE encode, ever, for the life of the server
# process. Scores are bit-identical: sentence-transformers encodes each
# text independently regardless of batching.
_embedding_cache: dict[str, list[float]] = {}


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME, device="cpu")


def generate_embedding(text: str) -> list[float]:
    if not text:
        return []

    cached = _embedding_cache.get(text)
    if cached is not None:
        return cached

    model = get_embedding_model()

    embedding = model.encode(
        text,
        normalize_embeddings=True,
    )

    result = embedding.tolist()
    _embedding_cache[text] = result
    return result


def semantic_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0

    left_vec = generate_embedding(left)
    right_vec = generate_embedding(right)
    if not left_vec or not right_vec:
        return 0.0

    # Vectors are L2-normalized by generate_embedding, so cosine
    # similarity == plain dot product.
    similarity = float(np.dot(left_vec, right_vec))

    return max(0.0, min(1.0, similarity))