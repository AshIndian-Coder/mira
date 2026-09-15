"""
STAGE 3 - AI matching core.

Hybrid matching pipeline (frozen weighted formula, MIRA spec):
    final_score = 0.20 * text
                + 0.20 * semantic          (Qwen-1B-Embedding, 1536-dim)
                + 0.35 * specification
                + 0.15 * material_grade
                + 0.10 * other_attributes

Public API:
    MatchingEngine()            -> engine with default services
    engine.index_materials()    -> embed + store vectors
    engine.match_material()     -> ranked candidates for one material
    get_embedding_service()     -> Qwen embedding singleton
"""
from app.services.matching_engine.qwen_embedding import (
    QwenEmbeddingService,
    get_embedding_service,
)
from app.services.matching_engine.vector_search import (
    VectorSearchService,
    get_vector_search_service,
)
from app.services.matching_engine.fuzzy_matcher import calculate_fuzzy_score
from app.services.matching_engine.attribute_matcher import compute_attribute_scores
from app.services.matching_engine.ensemble_ranker import (
    EnsembleRanker,
    MatchDecision,
    rank_match,
)
from app.services.matching_engine.explainable_ai import generate_explanation

from typing import Any, Dict, List, Optional



class MatchingEngine:
    """Composes the matching stages into one deterministic pipeline."""

    def __init__(
        self,
        embedding_service: Optional[QwenEmbeddingService] = None,
        vector_service: Optional[VectorSearchService] = None,
        ranker: Optional[EnsembleRanker] = None,
    ) -> None:
        self.embeddings = embedding_service or get_embedding_service()
        self.vectors = vector_service or get_vector_search_service()
        self.ranker = ranker or EnsembleRanker()


    def index_materials(self, materials: List[Dict[str, Any]]) -> int:
        """Embed (in chunks) and upsert materials into the vector store.

        Each material dict must have: id, cpse_id, category,
        cleaned_description (or description). Delegates to the vector
        search service, which owns embedding + storage.
        """
        if not materials:
            return 0
        return self.vectors.index_materials(materials)


    def match_material(
        self,
        material: Dict[str, Any],
        top_k: int = 100,
        exclude_ids: Optional[List[int]] = None,
        exclude_cpse_id: Optional[int] = None,
        min_confidence: float = 0.45,
    ) -> List[Dict[str, Any]]:
        """Score one source material against all indexed candidates.

        Returns a list of candidate dicts sorted by final_confidence desc,
        each with component scores, gate outcome, decision and explanation.
        """
        text = material.get("cleaned_description") or material.get("description") or ""
        embedding = self.embeddings.embed_texts([text])[0]

        results: List[Dict[str, Any]] = []
        hits = self.vectors.search_similar(
            embedding,
            top_k=top_k,
            exclude_ids=[int(material["id"])] + list(exclude_ids or []),
            exclude_cpse_id=exclude_cpse_id,
        )
        for hit in hits:
            candidate = hit.get("_material")
            if candidate is None:
                continue
            scored = self.score_pair(material, candidate, float(hit["score"]))
            if scored["final_confidence"] >= min_confidence:
                results.append(scored)
        results.sort(key=lambda item: item["final_confidence"], reverse=True)
        return results

    def score_pair(
        self,
        material: Dict[str, Any],
        candidate: Dict[str, Any],
        semantic_similarity: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Compute the full MIRA hybrid score for a pair (no DB access)."""
        if semantic_similarity is None:
            text_1 = material.get("cleaned_description") or material.get("description") or ""
            text_2 = candidate.get("cleaned_description") or candidate.get("description") or ""
            vecs = self.embeddings.embed_texts([text_1, text_2])
            import numpy as np

            semantic_similarity = float(np.dot(vecs[0], vecs[1]))

        text_sim = calculate_fuzzy_score(
            material.get("cleaned_description") or material.get("description") or "",
            candidate.get("cleaned_description") or candidate.get("description") or "",
        )
        attr_scores = compute_attribute_scores(
            material.get("attributes") or {},
            candidate.get("attributes") or {},
        )
        decision = self.ranker.rank(
            text_similarity=text_sim,
            semantic_similarity=semantic_similarity,
            specification_similarity=attr_scores["specification_similarity"],
            material_grade_similarity=attr_scores["material_grade_similarity"],
            other_attributes_similarity=attr_scores["other_attributes_similarity"],
            attributes_1=material.get("attributes") or {},
            attributes_2=candidate.get("attributes") or {},
            category_1=material.get("category"),
            category_2=candidate.get("category"),
        )
        explanation = generate_explanation(
            decision,
            attr_scores.get("detail", {}),
            material.get("attributes") or {},
            candidate.get("attributes") or {},
            material_code_1=material.get("material_code"),
            material_code_2=candidate.get("material_code"),
        )
        return {
            "material_1_id": int(material["id"]),
            "material_2_id": int(candidate["id"]),
            "cpse_1_id": material.get("cpse_id"),
            "cpse_2_id": candidate.get("cpse_id"),
            "semantic_similarity": round(max(0.0, min(1.0, semantic_similarity)), 4),
            "fuzzy_similarity": round(text_sim, 4),
            "attribute_similarity": round(
                max(
                    attr_scores["specification_similarity"],
                    attr_scores["material_grade_similarity"],
                    attr_scores["other_attributes_similarity"],
                ),
                4,
            ),
            "specification_similarity": round(attr_scores["specification_similarity"], 4),
            "material_grade_similarity": round(attr_scores["material_grade_similarity"], 4),
            "other_attributes_similarity": round(attr_scores["other_attributes_similarity"], 4),
            "final_confidence": round(decision.final_confidence, 4),
            "decision": decision.decision,
            "gate_status": decision.gate_status,
            "explanation": explanation,
        }


def get_matching_engine() -> MatchingEngine:
    """Process-wide engine (cheap to construct; services are singletons)."""
    return MatchingEngine()


__all__ = [
    "MatchingEngine",
    "get_matching_engine",
    "QwenEmbeddingService",
    "get_embedding_service",
    "VectorSearchService",
    "get_vector_search_service",
    "calculate_fuzzy_score",
    "compute_attribute_scores",
    "EnsembleRanker",
    "MatchDecision",
    "rank_match",
    "generate_explanation",
]
