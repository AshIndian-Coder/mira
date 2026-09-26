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
# all-MiniLM-L6-v2 (this repo's DEFAULT_MODEL_NAME in embeddings.py) emits
# 384-dim vectors. If you ever switch the model, this MUST be updated to
# match, and the collection must be dropped and recreated -- Milvus cannot
# resize an existing vector field.
EMBEDDING_DIM = 384

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
        FieldSchema(name="cpse", dtype=DataType.VARCHAR, max_length=100),
        FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=100),
    ]

    schema = CollectionSchema(fields, description="Material description embeddings")
    collection = Collection(name=COLLECTION_NAME, schema=schema)

    index_params = {
        "index_type": "IVF_FLAT",
        "metric_type": "COSINE",
        "params": {"nlist": 128},
    }
    collection.create_index(field_name="embedding", index_params=index_params)

    print(f"Created collection '{COLLECTION_NAME}' with dim={EMBEDDING_DIM}.")


if __name__ == "__main__":
    create_collection()