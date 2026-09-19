"""
Shared Milvus connection + insert helper, used by the material-upload
hook (writes embeddings in) and vector_search.py (reads them back out).

Every public call here is wrapped so a DOWN Milvus fails fast and stays
failed for a short cooldown: a live gRPC server that died (as opposed to
a port that never opened) otherwise burns ~210s of grpc retries *per
call*, which turned a run-batch with Milvus stopped into a multi-hour
grind. The breaker makes the degraded path take seconds, not hours.
"""

import time

from pymilvus import Collection, connections, utility

from app.services.matching.embeddings import generate_embedding

COLLECTION_NAME = "material_embeddings"
MILVUS_HOST = "localhost"
MILVUS_PORT = "19530"

RPC_TIMEOUT_SECONDS = 5     # per-call budget so grpc deadline fires quickly
DOWN_COOLDOWN_SECONDS = 30  # after any failure, skip Milvus entirely for this long

_connected = False
_down_until = 0.0


def _reset_connection() -> None:
    """Force a fresh connections.connect() once the cooldown expires."""
    global _connected
    _connected = False
    try:
        connections.disconnect("default")
    except Exception:
        pass


def mark_milvus_down() -> None:
    """Open the circuit breaker (also callable from this module's callers)."""
    global _down_until
    _down_until = time.monotonic() + DOWN_COOLDOWN_SECONDS
    _reset_connection()


def _ensure_connected() -> None:
    global _connected
    if not _connected:
        connections.connect(
            host=MILVUS_HOST,
            port=MILVUS_PORT,
            timeout=RPC_TIMEOUT_SECONDS,
        )
        _connected = True


def get_collection() -> Collection:
    if time.monotonic() < _down_until:
        raise ConnectionError(
            f"Milvus unreachable -- in {DOWN_COOLDOWN_SECONDS}s cooldown, "
            "skipping this call."
        )
    try:
        _ensure_connected()
        if not utility.has_collection(COLLECTION_NAME, timeout=RPC_TIMEOUT_SECONDS):
            raise ConnectionError(
                f"Collection '{COLLECTION_NAME}' does not exist yet -- "
                "run create_milvus_collection.py once."
            )
        return Collection(COLLECTION_NAME)
    except Exception:
        mark_milvus_down()
        raise


def insert_material_embedding(material_id: int, description: str, cpse: str, category: str) -> None:
    """Embeds a material's description and stores it in Milvus.

    NOTE: no flush here on purpose -- call flush_embeddings() once after
    a batch of inserts instead. Flushing per record makes large uploads
    extremely slow (one seal round-trip per row).
    """
    embedding = generate_embedding(description)
    if not embedding:
        return  # empty description -- nothing to embed

    collection = get_collection()
    try:
        collection.insert(
            [
                [material_id],
                [embedding],
                [cpse or ""],
                [category or ""],
            ]
        )
    except Exception:
        mark_milvus_down()
        raise


def flush_embeddings() -> None:
    """Seals pending inserts so they are durable + indexed. Call once
    after a batch of insert_material_embedding() calls."""
    collection = get_collection()
    try:
        collection.flush()
    except Exception:
        mark_milvus_down()
        raise