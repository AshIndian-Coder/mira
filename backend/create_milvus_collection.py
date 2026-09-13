"""
One-time setup: creates the `material_embeddings` Milvus collection.

Run once before using vector search:
    cd backend
    python create_milvus_collection.py

Safe to re-run -- skips creation if the collection already exists.
"""

from pymilvus import (
    connections,
    utility,
    FieldSchema,
    CollectionSchema,
    DataType,
    Collection,
)

COLLECTION_NAME = "material_embeddings"
EMBEDDING_DIM = 1024  # must match embeddings.py's EMBEDDING_DIM (Qwen3-Embedding-0.6B)

MILVUS_HOST = "localhost"
MILVUS_PORT = "19530"


def create_collection() -> None:
    connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)

    if utility.has_collection(COLLECTION_NAME):
        print(f"Collection '{COLLECTION_NAME}' already exists -- skipping.")
        return

    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True),
        # ^ same value as Postgres materials.id -- this is how a Milvus
        # search result gets joined back to the real material row.
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM),
        # NOTE: using "cpse" (VARCHAR) not "cpse_id" (INT) here -- the PDF's
        # design assumes a cpses table with integer ids, but the actual live
        # materials table only has a plain "cpse" string column (e.g. "NTPC").
        # Matching real data, not the aspirational schema.
        FieldSchema(name="cpse", dtype=DataType.VARCHAR, max_length=100),
        FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=100),
    ]

    schema = CollectionSchema(fields, description="Material description embeddings")
    collection = Collection(name=COLLECTION_NAME, schema=schema)

    # Index the vector field so search is fast (approximate nearest neighbor).
    index_params = {
        "index_type": "IVF_FLAT",
        "metric_type": "COSINE",
        "params": {"nlist": 128},
    }
    collection.create_index(field_name="embedding", index_params=index_params)

    print(f"Created collection '{COLLECTION_NAME}' with dim={EMBEDDING_DIM}.")


if __name__ == "__main__":
    create_collection()