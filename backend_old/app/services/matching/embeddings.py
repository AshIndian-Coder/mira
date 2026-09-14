from functools import lru_cache

from sentence_transformers import SentenceTransformer


MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME, device="cpu")


def generate_embedding(text: str) -> list[float]:
    if not text:
        return []

    model = get_embedding_model()

    embedding = model.encode(
        text,
        normalize_embeddings=True,
    )

    return embedding.tolist()


def semantic_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0

    model = get_embedding_model()

    embeddings = model.encode(
        [left, right],
        normalize_embeddings=True,
    )

    similarity = float(embeddings[0] @ embeddings[1])

    return max(0.0, min(1.0, similarity))
