"""Ensemble ranker: frozen MIRA weighted score + deterministic critical gates.

    final_score = 0.20*text + 0.20*semantic + 0.35*specification
                + 0.15*material_grade + 0.10*other_attributes

Decision policy (frozen):
    final_score < DIFFERENT_THRESHOLD (0.45)      -> DIFFERENT
    gate = CONFLICT / CATEGORY_MISMATCH           -> REVIEW (always)
    gate = UNKNOWN (critical field missing)       -> REVIEW (always)
    final_score >= HIGH_CONFIDENCE_THRESHOLD      -> HIGH_CONFIDENCE
    (0.45 <= final_score < 0.85, gate PASS)       -> REVIEW

A high semantic score alone can never approve equivalence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.utils.constants import (
    CRITICAL_FIELDS,
    DEFAULT_CRITICAL_FIELDS,
    DECISION_DIFFERENT,
    DECISION_HIGH_CONFIDENCE,
    DECISION_REVIEW,
    DIFFERENT_THRESHOLD,
    GATE_CATEGORY_MISMATCH,
    GATE_CONFLICT,
    GATE_PASS,
    GATE_UNKNOWN,
    HIGH_CONFIDENCE_THRESHOLD,
    WEIGHT_MATERIAL_GRADE,
    WEIGHT_OTHER_ATTRIBUTES,
    WEIGHT_SEMANTIC,
    WEIGHT_SPECIFICATION,
    WEIGHT_TEXT,
)


@dataclass
class MatchDecision:
    """Outcome of the ensemble ranker for one material pair."""

    final_confidence: float
    decision: str
    gate_status: str
    gate_detail: Dict[str, Any] = field(default_factory=dict)
    components: Dict[str, float] = field(default_factory=dict)
    contributions: Dict[str, float] = field(default_factory=dict)


def _same_category(category_1: Optional[str], category_2: Optional[str]) -> bool:
    if not category_1 or not category_2:
        return True  # unknown category is not a conflict by itself
    c1 = str(category_1).strip().upper()
    c2 = str(category_2).strip().upper()
    return c1 == c2 or c1 in ("OTHER", "") or c2 in ("OTHER", "")


def evaluate_critical_gates(
    attrs_1: Dict[str, Any],
    attrs_2: Dict[str, Any],
    category: Optional[str],
) -> (str, Dict[str, Any]):
    """Apply the MIRA critical-field gates.

    Returns (status, detail) where status is one of PASS / UNKNOWN /
    CONFLICT / CATEGORY_MISMATCH.
    """
    checks: List[Dict[str, Any]] = []

    # 1) Category mismatch is a conflict for the gate system.
    if category and not _same_category(category, attrs_1.get("category") or category):
        return GATE_CATEGORY_MISMATCH, {
            "reason": "category_mismatch",
            "checks": checks,
        }

    category_key = (category or (attrs_1.get("category") or attrs_1.get("type") or "")).strip().upper()
    if not category_key or category_key == "OTHER":
        applicable = []
    elif category_key in CRITICAL_FIELDS:
        applicable = CRITICAL_FIELDS[category_key]
    else:
        applicable = list(DEFAULT_CRITICAL_FIELDS)

    for field_name in applicable:
        v1 = (attrs_1.get(field_name) or "").strip() if attrs_1.get(field_name) else None
        v2 = (attrs_2.get(field_name) or "").strip() if attrs_2.get(field_name) else None
        v1 = v1.upper() if v1 else None
        v2 = v2.upper() if v2 else None

        if v1 is None and v2 is None:
            # No information on an applicable critical field.
            if category_key in CRITICAL_FIELDS:
                checks.append({"field": field_name, "v1": None, "v2": None, "result": "unknown"})
                status = GATE_UNKNOWN
            else:
                checks.append({"field": field_name, "v1": None, "v2": None, "result": "skipped"})
                continue
            return status, {"reason": "missing_critical_field", "checks": checks, "field": field_name}
        if v1 is None or v2 is None:
            if category_key in CRITICAL_FIELDS:
                checks.append({"field": field_name, "v1": v1, "v2": v2, "result": "unknown"})
                return GATE_UNKNOWN, {
                    "reason": "missing_critical_field",
                    "checks": checks,
                    "field": field_name,
                }
            checks.append({"field": field_name, "v1": v1, "v2": v2, "result": "unknown"})
            continue
        if v1 == v2:
            checks.append({"field": field_name, "v1": v1, "v2": v2, "result": "match"})
            continue
        # Conflict: try numeric tolerance for dimension-like fields
        try:
            n1 = float("".join(ch for ch in v1 if ch.isdigit() or ch == ".") or "nan")
            n2 = float("".join(ch for ch in v2 if ch.isdigit() or ch == ".") or "nan")
            if n1 == n1 and n2 == n2 and n1 > 0 and n2 > 0 and abs(n1 - n2) / max(n1, n2) < 0.001:
                checks.append({"field": field_name, "v1": v1, "v2": v2, "result": "match"})
                continue
        except ValueError:
            pass
        checks.append({"field": field_name, "v1": v1, "v2": v2, "result": "conflict"})
        return GATE_CONFLICT, {
            "reason": "conflicting_critical_field",
            "checks": checks,
            "field": field_name,
        }

    return GATE_PASS, {"reason": "all_critical_fields_ok", "checks": checks}


class EnsembleRanker:
    """Frozen-weight hybrid scorer with critical gates."""

    def __init__(
        self,
        weight_text: float = WEIGHT_TEXT,
        weight_semantic: float = WEIGHT_SEMANTIC,
        weight_specification: float = WEIGHT_SPECIFICATION,
        weight_material_grade: float = WEIGHT_MATERIAL_GRADE,
        weight_other_attributes: float = WEIGHT_OTHER_ATTRIBUTES,
        high_confidence_threshold: float = HIGH_CONFIDENCE_THRESHOLD,
        different_threshold: float = DIFFERENT_THRESHOLD,
    ) -> None:
        self.weights = {
            "text": weight_text,
            "semantic": weight_semantic,
            "specification": weight_specification,
            "material_grade": weight_material_grade,
            "other_attributes": weight_other_attributes,
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
        attributes_1: Dict[str, Any],
        attributes_2: Dict[str, Any],
        category_1: Optional[str] = None,
        category_2: Optional[str] = None,
    ) -> MatchDecision:
        """Compute the final MIRA score + decision for one pair."""
        scores = {
            "text": text_similarity,
            "semantic": semantic_similarity,
            "specification": specification_similarity,
            "material_grade": material_grade_similarity,
            "other_attributes": other_attributes_similarity,
        }
        components = {key: round(max(0.0, min(1.0, value)), 4) for key, value in scores.items()}
        contributions = {
            key: round(self.weights[key] * components[key], 4) for key in components
        }
        final = sum(contributions.values())
        final = round(max(0.0, min(1.0, final)), 4)

        # Category gate
        if not _same_category(category_1, category_2):
            gate_status = GATE_CATEGORY_MISMATCH
            gate_detail = {
                "reason": "category_mismatch",
                "category_1": category_1,
                "category_2": category_2,
                "checks": [],
            }
        else:
            gate_status, gate_detail = evaluate_critical_gates(
                attributes_1, attributes_2, category_1 or category_2
            )

        # Decision policy
        if final < self.different_threshold:
            decision = DECISION_DIFFERENT
        elif gate_status not in (GATE_PASS,):
            decision = DECISION_REVIEW
        elif final >= self.high_confidence_threshold:
            decision = DECISION_HIGH_CONFIDENCE
        else:
            decision = DECISION_REVIEW

        return MatchDecision(
            final_confidence=final,
            decision=decision,
            gate_status=gate_status,
            gate_detail=gate_detail,
            components=components,
            contributions=contributions,
        )


def rank_match(
    text_similarity: float,
    semantic_similarity: float,
    specification_similarity: float,
    material_grade_similarity: float,
    other_attributes_similarity: float,
    attributes_1: Dict[str, Any],
    attributes_2: Dict[str, Any],
    category_1: Optional[str] = None,
    category_2: Optional[str] = None,
) -> MatchDecision:
    """Module-level convenience wrapper around EnsembleRanker().rank()."""
    return EnsembleRanker().rank(
        text_similarity=text_similarity,
        semantic_similarity=semantic_similarity,
        specification_similarity=specification_similarity,
        material_grade_similarity=material_grade_similarity,
        other_attributes_similarity=other_attributes_similarity,
        attributes_1=attributes_1,
        attributes_2=attributes_2,
        category_1=category_1,
        category_2=category_2,
    )

