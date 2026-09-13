"""
Given a material, finds its top-N nearest neighbours in Milvus --
optionally restricted to the same category first (cheaper + more
relevant than searching everything).

Returns Postgres material ids (via Milvus's "id" field, which is kept
in sync with materials.id -- see milvus_client.insert_material_embedding).
"""

from app.services.matching.embeddings import generate_embedding
from app.services.matching.milvus_client import get_collection


def search_similar_materials(
    description: str,
    category: str | None = None,
    top_k: int = 100,
) -> list[int]:
    """Returns a list of material ids, most similar first."""
    query_embedding = generate_embedding(description)
    if not query_embedding:
        return []

    collection = get_collection()
    collection.load()

    search_params = {"metric_type": "COSINE", "params": {"nprobe": 16}}

    # Strip quotes/backslashes: category comes from CSV data and is
    # interpolated into the Milvus boolean expression -- a stray quote
    # would break the query.
    expr = None
    if category:
        safe_category = str(category).replace('"', '').replace('\\', '')
        expr = f'category == "{safe_category}"'

    results = collection.search(
        data=[query_embedding],
        anns_field="embedding",
        param=search_params,
        limit=top_k,
        expr=expr,
        output_fields=["id"],
    )

    return [hit.id for hit in results[0]]