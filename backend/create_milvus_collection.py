"""
One-time setup: creates the material_embeddings Milvus collection.

Run from the backend directory:

    python create_milvus_collection.py

The script is safe to run repeatedly. If the collection already exists,
it is preserved unless --recreate is provided.
"""

from __future__ import annotations

import argparse

from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)


COLLECTION_NAME = "material_embeddings"

# This collection stores MIRA.ai final embeddings.
# MiniLM 384-dimensional embeddings are used only for fast in-memory
# candidate retrieval and must not be written to this collection.
EMBEDDING_DIM = 1024

MILVUS_HOST = "localhost"
MILVUS_PORT = "19530"


def create_collection(recreate: bool = False) -> None:
    """Create the Milvus collection if it does not already exist."""
    connections.connect(
        host=MILVUS_HOST,
        port=MILVUS_PORT,
    )

    if utility.has_collection(COLLECTION_NAME):
        if not recreate:
            print(
                f"Collection '{COLLECTION_NAME}' already exists. "
                "Skipping creation."
            )
            return

        print(
            f"Dropping existing collection '{COLLECTION_NAME}' "
            "because --recreate was supplied."
        )
        utility.drop_collection(COLLECTION_NAME)

    fields = [
        FieldSchema(
            name="id",
            dtype=DataType.INT64,
            is_primary=True,
        ),
        FieldSchema(
            name="embedding",
            dtype=DataType.FLOAT_VECTOR,
            dim=EMBEDDING_DIM,
        ),
        FieldSchema(
            name="cpse",
            dtype=DataType.VARCHAR,
            max_length=100,
        ),
        FieldSchema(
            name="category",
            dtype=DataType.VARCHAR,
            max_length=100,
        ),
    ]

    schema = CollectionSchema(
        fields,
        description=(
            "MIRA.ai 1024-dimensional material description embeddings"
        ),
    )

    collection = Collection(
        name=COLLECTION_NAME,
        schema=schema,
    )

    index_params = {
        "index_type": "IVF_FLAT",
        "metric_type": "COSINE",
        "params": {
            "nlist": 128,
        },
    }

    collection.create_index(
        field_name="embedding",
        index_params=index_params,
    )

    print(
        f"Created collection '{COLLECTION_NAME}' "
        f"with dimension={EMBEDDING_DIM}."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Create the MIRA.ai material_embeddings Milvus collection."
        )
    )

    parser.add_argument(
        "--recreate",
        action="store_true",
        help=(
            "Drop the existing collection and recreate it with "
            "the 1024-dimensional schema."
        ),
    )

    args = parser.parse_args()
    create_collection(recreate=args.recreate)