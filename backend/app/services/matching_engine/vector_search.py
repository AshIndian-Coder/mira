"""
Vector search operations (top-K similar materials in milliseconds).
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from app.config import settings
from app.db.vector_db import get_vector_store
from app.services.matching_engine.qwen_embedding import get_embedding_service

logger = logging.getLogger("mira.vector_search")


class VectorSearchService:
    """Facade used by the matching engine and ingestion pipeline."""

    def __init__(self) -> None:
        self._store = get_vector_store()
        self._embeddings = get_embedding_service()

    @property
    def backend_name(self) -> str:
        """'milvus' when the vector DB is reachable, else 'in_memory'."""
        return self._store.backend_name


    def index_materials(self, materials: Sequence[Dict[str, Any]]) -> int:
        """Embed and store vectors for material dicts.

        Required keys per material: id, cpse_id, category.
        Text source: cleaned_description or description.
        """
        if not materials:
            return 0
        texts = [
            (m.get("cleaned_description") or m.get("description") or "")
            for m in materials
        ]
        vectors = self._embeddings.embed_texts(texts)
        rows = [
            {
                "id": int(m["id"]),
                "cpse_id": m.get("cpse_id"),
                "category": (m.get("category") or "")[:100],
                "embedding": vectors[i],
            }
            for i, m in enumerate(materials)
        ]
        return self._store.upsert(rows)

    def delete_materials(self, material_ids: Sequence[int]) -> None:
        self._store.delete(list(material_ids))


    def search_similar(
        self,
        query_embedding: np.ndarray,
        top_k: int = 100,
        exclude_ids: Optional[Sequence[int]] = None,
        exclude_cpse_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Top-K hits for a query vector.

        When the in-memory fallback is active, hits are resolved to full
        material rows from PostgreSQL (the memory store keeps only vectors).
        """
        filters: Dict[str, Any] = {}
        if exclude_cpse_id is not None:
            filters["cpse_id"] = exclude_cpse_id
        hits = self._store.search(
            np.asarray(query_embedding, dtype=np.float32),
            top_k=top_k,
            exclude_ids=list(exclude_ids or []),
            filters=filters or None,
        )
        return self._resolve_hits(hits)

    def _resolve_hits(self, hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Attach full material dicts to hits (needed by the ranker)."""
        if not hits:
            return []
        ids = [int(hit["id"]) for hit in hits]
        materials_by_id = self._load_materials(ids)
        resolved: List[Dict[str, Any]] = []
        for hit in hits:
            material = materials_by_id.get(int(hit["id"]))
            if material is None:
                continue
            entry = dict(hit)
            entry["_material"] = material
            resolved.append(entry)
        return resolved

    def _load_materials(self, material_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """Load material rows for the given ids (cache per-process)."""
        from app.db.postgres import SessionLocal
        from app.models.material import Material

        result: Dict[int, Dict[str, Any]] = {}
        if not material_ids:
            return result
        db = SessionLocal()
        try:
            rows = (
                db.query(Material).filter(Material.id.in_(material_ids)).all()
            )
            for row in rows:
                result[int(row.id)] = {
                    "id": int(row.id),
                    "cpse_id": row.cpse_id,
                    "material_code": row.material_code,
                    "description": row.description,
                    "cleaned_description": row.cleaned_description,
                    "attributes": dict(row.attributes or {}),
                    "category": row.category,
                    "uom_normalized": row.uom_normalized,
                }
        finally:
            db.close()
        return result


    def stats(self) -> Dict[str, Any]:
        return self._store.stats()

    def health(self) -> Dict[str, Any]:
        return {
            "vector_store": self._store.health(),
            "embedding": self._embeddings.model_info(),
            "top_k_default": settings.VECTOR_TOP_K,
            "dim": settings.EMBEDDING_DIM,
        }


_vector_search_service: Optional[VectorSearchService] = None
_vector_search_lock = threading.Lock()


def get_vector_search_service() -> VectorSearchService:
    global _vector_search_service
    if _vector_search_service is None:
        with _vector_search_lock:
            if _vector_search_service is None:
                _vector_search_service = VectorSearchService()
    return _vector_search_service
