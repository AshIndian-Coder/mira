"""Vector database connection (Milvus) with a graceful in-memory fallback.

The Milvus collection ``material_embeddings`` stores the 1536-dim output
vectors of Qwen-1B-Embedding (dimension is locked so fine-tuned, baseline
and INT8 checkpoints stay compatible).

When Milvus is not reachable (dev box, demo, unit tests) the store
transparently falls back to an in-memory cosine store so the matching
pipeline keeps working end-to-end.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from app.config import settings

logger = logging.getLogger("mira.vector_db")



class InMemoryVectorStore:
    """Cosine-similarity store backed by numpy (vectors are L2-normalized)."""

    def __init__(self) -> None:
        self._records: Dict[int, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def upsert(self, items: Sequence[Dict[str, Any]]) -> int:
        """items: [{"id": int, "embedding": np.ndarray, "cpse_id": int, "category": str}]"""
        count = 0
        with self._lock:
            for item in items:
                vector = np.asarray(item["embedding"], dtype=np.float32)
                norm = float(np.linalg.norm(vector))
                if norm > 0:
                    vector = vector / norm
                self._records[int(item["id"])] = {
                    "id": int(item["id"]),
                    "embedding": vector,
                    "cpse_id": item.get("cpse_id"),
                    "category": item.get("category") or "",
                }
                count += 1
        return count

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 100,
        exclude_ids: Optional[Sequence[int]] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        query = np.asarray(query_embedding, dtype=np.float32)
        norm = float(np.linalg.norm(query))
        if norm > 0:
            query = query / norm

        exclude = set(exclude_ids or [])
        filters = filters or {}

        scored: List[tuple] = []
        with self._lock:
            for record in self._records.values():
                if record["id"] in exclude:
                    continue
                if "cpse_id" in filters and filters["cpse_id"] is not None:
                    if record.get("cpse_id") == filters["cpse_id"]:
                        continue  # "ne" semantics used by the facade
                if "category" in filters and filters["category"]:
                    if not record.get("category"):
                        continue
                score = float(np.dot(query, record["embedding"]))
                scored.append((score, record["id"]))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            {"id": material_id, "score": round(max(0.0, min(1.0, score)), 4)}
            for score, material_id in scored[:top_k]
        ]

    def delete(self, ids: Sequence[int]) -> None:
        with self._lock:
            for material_id in ids:
                self._records.pop(int(material_id), None)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {"backend": "in_memory", "count": len(self._records)}

    def health(self) -> Dict[str, Any]:
        return {"backend": "in_memory", "status": "healthy"}




class MilvusVectorStore:
    """Thin wrapper over pymilvus for the ``material_embeddings`` collection."""

    def __init__(self, uri: str, collection: str, dim: int) -> None:
        self._uri = uri
        self._collection_name = collection
        self._dim = dim
        self._client = None
        self._available = False

    def connect(self) -> bool:
        try:
            from pymilvus import (
                Collection,
                CollectionSchema,
                DataType,
                FieldSchema,
                MilvusClient,
            )

            client = MilvusClient(uri=self._uri, timeout=5)
            client.health()
            self._client = client
            self._pymilvus = (
                Collection,
                CollectionSchema,
                DataType,
                FieldSchema,
            )
            self._ensure_collection(client)
            self._available = True
            logger.info("Connected to Milvus at %s", self._uri)
            return True
        except Exception as exc:
            logger.warning("Milvus unavailable (%s); using in-memory fallback", exc)
            self._available = False
            return False

    def _ensure_collection(self, client) -> None:
        if client.has_collection(self._collection_name):
            client.load_collection(self._collection_name)
            return
        from pymilvus import CollectionSchema, DataType, FieldSchema

        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True),
            FieldSchema(
                name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self._dim
            ),
            FieldSchema(name="cpse_id", dtype=DataType.INT64),
            FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=100),
        ]
        schema = CollectionSchema(fields=fields, description="Material embeddings")
        client.create_collection(
            self._collection_name, schema=schema, dimension=self._dim
        )
        client.create_index(
            self._collection_name,
            field_name="embedding",
            index_params={
                "index_type": "IVF_FLAT",
                "metric_type": "COSINE",
                "params": {"nlist": 128},
            },
        )
        logger.info("Created Milvus collection %s (dim=%d)", self._collection_name, self._dim)

    def upsert(self, items: Sequence[Dict[str, Any]]) -> int:
        if not self._available or self._client is None:
            return 0
        rows = [
            {
                "id": int(item["id"]),
                "embedding": [float(v) for v in np.asarray(item["embedding"], dtype=np.float64).ravel()],
                "cpse_id": int(item.get("cpse_id") or 0),
                "category": str(item.get("category") or "")[:100],
            }
            for item in items
        ]
        if not rows:
            return 0
        try:
            self._client.upsert(self._collection_name, rows)
            return len(rows)
        except Exception as exc:
            logger.warning("Milvus upsert failed: %s", exc)
            return 0

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 100,
        exclude_ids: Optional[Sequence[int]] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        if not self._available or self._client is None:
            return []
        expr = None
        if exclude_ids:
            expr = f"id not in [{', '.join(str(int(i)) for i in exclude_ids)}]"
        try:
            results = self._client.search(
                collection_name=self._collection_name,
                data=[query_embedding.astype(np.float32).tolist()],
                limit=top_k + len(exclude_ids or []),
                filter=expr,
                output_fields=["id", "cpse_id", "category"],
            )
            out: List[Dict[str, Any]] = []
            for hit in results[0]:
                entity_id = int(hit["id"])
                if entity_id in set(exclude_ids or []):
                    continue
                out.append(
                    {
                        "id": entity_id,
                        "score": round(float(hit["distance"]), 4),
                        "cpse_id": hit.get("entity", {}).get("cpse_id"),
                        "category": hit.get("entity", {}).get("category"),
                    }
                )
            return out[:top_k]
        except Exception as exc:
            logger.warning("Milvus search failed: %s", exc)
            return []

    def delete(self, ids: Sequence[int]) -> None:
        if not self._available or self._client is None or not ids:
            return
        try:
            self._client.delete(
                self._collection_name,
                filter=f"id in [{', '.join(str(int(i)) for i in ids)}]",
            )
        except Exception as exc:
            logger.warning("Milvus delete failed: %s", exc)

    def stats(self) -> Dict[str, Any]:
        if not self._available or self._client is None:
            return {"backend": "milvus", "count": 0, "available": False}
        try:
            count = self._client.get_collection_stats(self._collection_name).get(
                "row_count", 0
            )
            return {"backend": "milvus", "count": int(count), "available": True}
        except Exception:
            return {"backend": "milvus", "count": -1, "available": True}

    def health(self) -> Dict[str, Any]:
        return {"backend": "milvus", "status": "healthy" if self._available else "unavailable"}




class VectorSearch:
    """Facade: try Milvus, fall back to the in-memory store.

    Public API (used by matching_engine and the ingestion pipeline):
        upsert(items)
        search(embedding, top_k, exclude_ids, filters)
        delete(ids)
        stats() / health()
    """

    def __init__(self) -> None:
        self._mem = InMemoryVectorStore()
        self._milvus = MilvusVectorStore(
            uri=settings.MILVUS_URI,
            collection=settings.MILVUS_COLLECTION,
            dim=settings.EMBEDDING_DIM,
        )
        self._milvus_ready = False

    def ensure_connected(self) -> None:
        if not self._milvus_ready:
            self._milvus.connect()
            self._milvus_ready = True

    @property
    def backend_name(self) -> str:
        self.ensure_connected()
        return "milvus" if self._milvus_available else "in_memory"

    @property
    def _milvus_available(self) -> bool:
        return self._milvus._available

    def upsert(self, items: Sequence[Dict[str, Any]]) -> int:
        self.ensure_connected()
        count = self._milvus.upsert(items) if self._milvus_available else 0
        if not count:
            count = self._mem.upsert(items)
        return count

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 100,
        exclude_ids: Optional[Sequence[int]] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        self.ensure_connected()
        if self._milvus_available:
            return self._milvus.search(query_embedding, top_k, exclude_ids, filters)
        return self._mem.search(query_embedding, top_k, exclude_ids, filters)

    def delete(self, ids: Sequence[int]) -> None:
        self.ensure_connected()
        self._milvus.delete(ids)
        self._mem.delete(ids)

    def stats(self) -> Dict[str, Any]:
        self.ensure_connected()
        if self._milvus_available:
            return self._milvus.stats()
        return self._mem.stats()

    def health(self) -> Dict[str, Any]:
        self.ensure_connected()
        return self._milvus.health() if self._milvus_available else self._mem.health()


_vector_store: Optional[VectorSearch] = None
_vector_lock = threading.Lock()


def get_vector_store() -> VectorSearch:
    """Process-wide singleton vector store."""
    global _vector_store
    if _vector_store is None:
        with _vector_lock:
            if _vector_store is None:
                _vector_store = VectorSearch()
    return _vector_store
