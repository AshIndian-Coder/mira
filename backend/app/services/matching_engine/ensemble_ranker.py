"""
Ensemble ranking + final decision logic for the MIRA matching pipeline.
Implements the frozen weighted formula:
    final_score = 0.20 * text
                + 0.20 * semantic
                + 0.35 * specification
                + 0.15 * material_grade
                + 0.10 * other_attributes

Decision thresholds (MIRA spec):
  * final_score >= 0.85 AND gates PASS  -> HIGH_CONFIDENCE
  * final_score >= 0.45                 -> REVIEW
  * otherwise                           -> DIFFERENT

The AI never approves equivalence; it only proposes a confidence score.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.utils.constants import (
    DECISION_DIFFERENT,
    DECISION_HIGH_CONFIDENCE,
    DECISION_REVIEW,
    GATE_CATEGORY_MISMATCH,
    GATE_CONFLICT,
    GATE_PASS,
    GATE_UNKNOWN,
    WEIGHT_OTHER_ATTRIBUTES,
    WEIGHT_SPECIFICATION,
    WEIGHT_SEMANTIC,
    WEIGHT_TEXT,
)


@dataclass
class MatchDecision:
    text_similarity: float
    semantic_similarity: float
    specification_similarity: float
    material_grade_similarity: float
    other_attributes_similarity: float
    final_confidence: float
    decision: str
    gate_status: str
    gate_reasons: List[str]


class EnsembleRanker:
    """Ranks candidate matches using the MIRA hybrid formula."""

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        high_confidence_threshold: float = 0.85,
        different_threshold: float = 0.45,
    ) -> None:
        self.weights = weights or {
            "text": WEIGHT_TEXT,
            "semantic": WEIGHT_SEMANTIC,
            "specification": WEIGHT_SPECIFICATION,
            "material_grade": 0.15,
            "other_attributes": WEIGHT_OTHER_ATTRIBUTES,
        }
        self.high_confidence_threshold = high_confidence_threshold
        self.different_threshold = different_threshold

    def rank(
        self,
        text_similarity: float,
        semantic_similarity: float,
        specification_similarity: float,
        material_grade_similarity: float,
        other_attributes_similarity: float,
        attributes_1: Optional[Dict[str, Any]] = None,
        attributes_2: Optional[Dict[str, Any]] = None,
        category_1: Optional[str] = None,
        category_2: Optional[str] = None,
    ) -> MatchDecision:
        """Compute the MIRA decision for one candidate pair."""
        score = self._weighted_score(
            text_similarity=text_similarity,
            semantic_similarity=semantic_similarity,
            specification_similarity=specification_similarity,
            material_grade_similarity=material_grade_similarity,
            other_attributes_similarity=other_attributes_similarity,
        )

        gates_pass, gate_reasons = self._evaluate_gates(
            attributes_1=attributes_1,
            attributes_2=attributes_2,
            category_1=category_1,
            category_2=category_2,
        )

        if not gates_pass:
            decision = DECISION_REVIEW
            gate_status = GATE_CONFLICT if gate_reasons else GATE_UNKNOWN
        elif score >= self.high_confidence_threshold:
            decision = DECISION_HIGH_CONFIDENCE
            gate_status = GATE_PASS
        elif score >= self.different_threshold:
            decision = DECISION_REVIEW
            gate_status = GATE_PASS
        else:
            decision = DECISION_DIFFERENT
            gate_status = GATE_PASS

        return MatchDecision(
            text_similarity=text_similarity,
            semantic_similarity=semantic_similarity,
            specification_similarity=specification_similarity,
            material_grade_similarity=material_grade_similarity,
            other_attributes_similarity=other_attributes_similarity,
            final_confidence=score,
            decision=decision,
            gate_status=gate_status,
            gate_reasons=gate_reasons,
        )

    def _weighted_score(
        self,
        text_similarity: float,
        semantic_similarity: float,
        specification_similarity: float,
        material_grade_similarity: float,
        other_attributes_similarity: float,
    ) -> float:
        return (
            self.weights.get("text", WEIGHT_TEXT) * text_similarity
            + self.weights.get("semantic", WEIGHT_SEMANTIC) * semantic_similarity
            + self.weights.get("specification", WEIGHT_SPECIFICATION) * specification_similarity
            + self.weights.get("material_grade", 0.15) * material_grade_similarity
            + self.weights.get("other_attributes", WEIGHT_OTHER_ATTRIBUTES) * other_attributes_similarity
        )

    def _evaluate_gates(
        self,
        attributes_1: Optional[Dict[str, Any]],
        attributes_2: Optional[Dict[str, Any]],
        category_1: Optional[str],
        category_2: Optional[str],
    ) -> Tuple[bool, List[str]]:
        from app.services.matching_engine.attribute_matcher import apply_critical_gates

        attrs1 = attributes_1 or {}
        attrs2 = attributes_2 or {}
        gates_pass, reasons = apply_critical_gates(attrs1, attrs2, category_1, category_2)
        return gates_pass, reasons


def rank_match(
    text_similarity: float,
    semantic_similarity: float,
    specification_similarity: float,
    material_grade_similarity: float,
    other_attributes_similarity: float,
    weights: Optional[Dict[str, float]] = None,
    high_confidence_threshold: float = 0.85,
    different_threshold: float = 0.45,
) -> MatchDecision:
    """Convenience function: rank a single match without constructing an object."""
    ranker = EnsembleRanker(
        weights=weights,
        high_confidence_threshold=high_confidence_threshold,
        different_threshold=different_threshold,
    )
    return ranker.rank(
        text_similarity=text_similarity,
        semantic_similarity=semantic_similarity,
        specification_similarity=specification_similarity,
        material_grade_similarity=material_grade_similarity,
        other_attributes_similarity=other_attributes_similarity,
    )
