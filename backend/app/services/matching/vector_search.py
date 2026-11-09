"""
Nearest-neighbour candidate generation over the Milvus material embeddings.

This is an ADDITIVE candidate source. The rule-based blocking in
app/services/blocking/service.py remains the primary generator; vector search
surfaces pairs that share no block key but are semantically close -- the
"written differently, same item" case that blocking by construction cannot
reach.

Returned ids are Postgres/store material ids: the Milvus primary key mirrors
materials.id (see milvus_client.insert_material_embeddings), which is what
lets a hit be joined straight back to the real material record.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.services.matching.embeddings import (
    MiraRemoteEmbeddingError,
    generate_embedding,
)
from app.services.matching.milvus_client import (
    MilvusUnavailable,
    ensure_loaded,
    milvus_available,
)

logger = logging.getLogger(__name__)

SEARCH_PARAMS = {"metric_type": "COSINE", "params": {"nprobe": 16}}


def _escape_expr_literal(value: str) -> str:
    """Escapes a value for use inside a Milvus boolean expression string literal."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def search_similar_materials(
    description: str,
    category: str | None = None,
    top_k: int | None = None,
    exclude_cpse: str | None = None,
    embedding_cache: Any = None,
) -> list[int]:
    """
    Returns material ids ordered most-similar-first, or [] if unavailable.

    category      -- when given, restricts the search to the same category,
                     which is both cheaper and more precise than searching
                     the whole collection.
    exclude_cpse  -- when given, filters out same-CPSE hits inside Milvus
                     rather than in Python, so the top_k budget is spent
                     entirely on cross-CPSE candidates (batch harmonization
                     is cross-CPSE only).

    Never raises: a Milvus outage degrades this to "no extra candidates",
    leaving rule-based matching results unaffected.
    """
    if not settings.milvus_enabled or not milvus_available():
        return []

    description = (description or "").strip()
    if not description:
        return []

    if embedding_cache is not None:
        emb = embedding_cache.get_or_encode(description)
        if emb is None:
            return []
        query_embedding = emb.tolist() if hasattr(emb, "tolist") else emb
    else:
        query_embedding = generate_embedding(description)
    if not query_embedding:
        return []

    clauses: list[str] = []
    if category:
        clauses.append(f'category == "{_escape_expr_literal(category)}"')
    if exclude_cpse:
        clauses.append(f'cpse != "{_escape_expr_literal(exclude_cpse)}"')
    expr = " and ".join(clauses) if clauses else None

    try:
        collection = ensure_loaded()
        results = collection.search(
            data=[query_embedding],
            anns_field="embedding",
            param=SEARCH_PARAMS,
            limit=top_k or settings.milvus_top_k,
            expr=expr,
            output_fields=["id"],
        )
    except MilvusUnavailable as exc:
        logger.debug("Vector search skipped: %s", exc)
        return []
    except Exception as exc:
        logger.warning("Vector search failed: %s", exc)
        return []

    if not results:
        return []

    return [int(hit.id) for hit in results[0]]


def search_similar_materials_batch(
    items: list[tuple[int, str, str | None]],
    top_k: int | None = None,
    embedding_cache: Any = None,
    batch_size: int = 64,
    exclude_cpse_by_material: dict[int, str] | None = None,
) -> dict[int, list[int]]:
    """Search multiple material descriptions in bounded, filter-compatible batches.

    Queries share a Milvus request only when both their category and excluded
    source CPSE are identical. This keeps the top-k budget focused on eligible
    cross-CPSE hits instead of allowing same-CPSE materials to consume it.
    """
    output: dict[int, list[int]] = {
        int(material_id): [] for material_id, _, _ in items
    }
    if not items or not settings.milvus_enabled or not milvus_available():
        return output
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")

    exclusions = exclude_cpse_by_material or {}
    grouped: dict[
        tuple[str | None, str | None],
        list[tuple[int, str, list[float]]],
    ] = {}

    for material_id, raw_description, category in items:
        material_id = int(material_id)
        description = (raw_description or "").strip()
        if not description:
            continue

        excluded_cpse = exclusions.get(material_id)
        excluded_cpse = str(excluded_cpse).strip() if excluded_cpse else None
        category_key = str(category).strip() if category else None

        try:
            if embedding_cache is not None:
                embedding = embedding_cache.get_or_encode(description)
                if embedding is None:
                    continue
                query_embedding = (
                    embedding.tolist()
                    if hasattr(embedding, "tolist")
                    else embedding
                )
            else:
                query_embedding = generate_embedding(description)
        except MiraRemoteEmbeddingError:
            raise
        except Exception as exc:
            logger.warning(
                "Embedding for vector search skipped for material %s: %s",
                material_id,
                exc,
                exc_info=True,
            )
            continue

        if query_embedding is None or len(query_embedding) == 0:
            continue

        grouped.setdefault((category_key, excluded_cpse), []).append(
            (material_id, description, query_embedding)
        )

    if not grouped:
        return output

    try:
        collection = ensure_loaded()
    except Exception as exc:
        logger.warning("Batched vector search could not load Milvus: %s", exc)
        for (category, excluded_cpse), entries in grouped.items():
            for material_id, description, _ in entries:
                try:
                    output[material_id] = search_similar_materials(
                        description=description,
                        category=category,
                        top_k=top_k,
                        exclude_cpse=excluded_cpse,
                        embedding_cache=embedding_cache,
                    )
                except MiraRemoteEmbeddingError:
                    raise
                except Exception:
                    logger.warning(
                        "Scalar Milvus fallback failed for material %s",
                        material_id,
                        exc_info=True,
                    )
                    output[material_id] = []
        return output

    limit = top_k if top_k is not None else settings.milvus_top_k
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("top_k must be a positive integer")

    for (category, excluded_cpse), entries in grouped.items():
        clauses: list[str] = []
        if category:
            clauses.append(f'category == "{_escape_expr_literal(category)}"')
        if excluded_cpse:
            clauses.append(f'cpse != "{_escape_expr_literal(excluded_cpse)}"')
        expr = " and ".join(clauses) if clauses else None

        for offset in range(0, len(entries), batch_size):
            chunk = entries[offset:offset + batch_size]
            try:
                results = collection.search(
                    data=[entry[2] for entry in chunk],
                    anns_field="embedding",
                    param=SEARCH_PARAMS,
                    limit=limit,
                    expr=expr,
                    output_fields=["id"],
                )
                if len(results) != len(chunk):
                    raise ValueError(
                        f"Milvus returned {len(results)} result groups for "
                        f"{len(chunk)} queries"
                    )

                for (material_id, _, _), hits in zip(chunk, results):
                    resolved_ids: list[int] = []
                    for hit in hits:
                        hit_id = getattr(hit, "id", None)
                        if hit_id is None and isinstance(hit, dict):
                            hit_id = hit.get("id")
                        if hit_id is not None:
                            resolved_ids.append(int(hit_id))
                    output[material_id] = resolved_ids
            except Exception as exc:
                logger.warning(
                    "Batched Milvus search failed for category %r excluding CPSE %r; "
                    "falling back to scalar queries: %s",
                    category,
                    excluded_cpse,
                    exc,
                    exc_info=True,
                )
                for material_id, description, _ in chunk:
                    try:
                        output[material_id] = search_similar_materials(
                            description=description,
                            category=category,
                            top_k=limit,
                            exclude_cpse=excluded_cpse,
                            embedding_cache=embedding_cache,
                        )
                    except MiraRemoteEmbeddingError:
                        raise
                    except Exception:
                        logger.warning(
                            "Scalar Milvus fallback failed for material %s",
                            material_id,
                            exc_info=True,
                        )
                        output[material_id] = []

    return output
