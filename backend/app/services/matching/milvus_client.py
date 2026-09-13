"""
Shared Milvus connection + insert helper, used by the material-upload
hook (writes embeddings in) and vector_search.py (reads them back out).
"""

from pymilvus import connections, Collection

from app.services.matching.embeddings import generate_embedding

COLLECTION_NAME = "material_embeddings"
MILVUS_HOST = "localhost"
MILVUS_PORT = "19530"

_connected = False


def _ensure_connected() -> None:
    global _connected
    if not _connected:
        connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)
        _connected = True


def get_collection() -> Collection:
    _ensure_connected()
    return Collection(COLLECTION_NAME)


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
    collection.insert(
        [
            [material_id],
            [embedding],
            [cpse or ""],
            [category or ""],
        ]
    )


def flush_embeddings() -> None:
    """Seals pending inserts so they are durable + indexed. Call once
    after a batch of insert_material_embedding() calls."""
    get_collection().flush()