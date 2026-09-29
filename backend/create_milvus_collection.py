"""
One-time setup: creates the `material_embeddings` Milvus collection.

Run once before using vector search:
    cd backend
    python create_milvus_collection.py

Safe to re-run -- skips creation if the collection already exists.
"""

import argparse
import sys
from pathlib import Path

# Add backend directory to sys.path if invoked directly
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

try:
    from app.services.matching.embeddings import get_embedding_dimension
    EMBEDDING_DIM = get_embedding_dimension()
except Exception:
    EMBEDDING_DIM = 1024

COLLECTION_NAME = "material_embeddings"
MILVUS_HOST = "localhost"
MILVUS_PORT = "19530"


def create_collection(recreate: bool = False) -> None:
    try:
        from pymilvus import (
            connections,
            utility,
            FieldSchema,
            CollectionSchema,
            DataType,
            Collection,
        )
    except ImportError as exc:
        print(f"Cannot create Milvus collection: pymilvus is not installed ({exc}).")
        return

    connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)

    if utility.has_collection(COLLECTION_NAME):
        if recreate:
            print(f"Dropping existing collection '{COLLECTION_NAME}' (recreate requested)...")
            utility.drop_collection(COLLECTION_NAME)
        else:
            print(f"Collection '{COLLECTION_NAME}' already exists -- skipping (use --recreate to drop and rebuild).")
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

    print(f"Created collection '{COLLECTION_NAME}' with dynamic dim={EMBEDDING_DIM}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create or recreate Milvus material_embeddings collection")
    parser.add_argument("--recreate", action="store_true", help="Drop existing collection and recreate with new vector dimension")
    args = parser.parse_args()
    create_collection(recreate=args.recreate)