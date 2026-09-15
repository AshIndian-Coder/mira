"""Attribute comparison: specification, material-grade and other similarity.

These three components carry the 0.35 / 0.15 / 0.10 weights in the frozen
MIRA hybrid score. Comparisons are field-wise and conservative:

  * both fields present and equal      -> 1.0   (match)
  * both present and conflicting       -> 0.0   (hard conflict)
  * one side missing                   -> 0.5   (neutral - cannot verify)
  * both missing                       -> 1.0   (no conflicting information;
                                                absent on both sides, so it
                                                neither supports nor breaks
                                                the match - the critical gates
                                                still route such pairs to REVIEW)

Material-grade additionally understands metallurgical families
(Carbon Steel vs Mild Steel -> compatible, Carbon Steel vs Stainless -> 0).
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from app.services.ner_extraction.attribute_extractor import grade_family

# Field weights inside the specification similarity component.
_SPEC_FIELD_WEIGHTS: Dict[str, float] = {
    "dimensions": 0.45,
    "subtype": 0.15,
    "pressure_rating": 0.15,
    "voltage_class": 0.10,
    "standard": 0.10,
    "seal": 0.05,
}

# Fields that fall under "other attributes" (type-level + residuals).
_OTHER_FIELDS: Tuple[str, ...] = (
    "type",
    "size",
    "bore",
    "length",
    "thread",
)


def _normalize_value(value: Any) -> Optional[str]:
    """Normalize a field value for comparison (case/punctuation safe)."""
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    # "DN150" == "150 DN" == "150" for pipe-like dimensions
    text = text.replace(" ", "")
    return text


def compare_field(value_1: Any, value_2: Any) -> Tuple[float, str]:
    """Compare two field values -> (score, status)."""
    v1, v2 = _normalize_value(value_1), _normalize_value(value_2)
    if v1 is None and v2 is None:
        return 1.0, "no_info"
    if (v1 is None) != (v2 is None):
        return 0.5, "unknown"
    if v1 == v2:
        return 1.0, "match"
    # Near-equal tolerances for numeric-ish values ("150MM" vs "150.0MM")
    try:
        n1 = float("".join(ch for ch in v1 if ch.isdigit() or ch == ".") or "nan")
        n2 = float("".join(ch for ch in v2 if ch.isdigit() or ch == ".") or "nan")
        if n1 == n1 and n2 == n2 and n1 > 0 and n2 > 0:
            if abs(n1 - n2) / max(n1, n2) < 0.001:
                return 1.0, "match"
    except ValueError:
        pass
    return 0.0, "conflict"


def _weighted_average(detail: Dict[str, Dict[str, Any]]) -> float:
    """Weighted mean over spec fields (weights renormalized to present set)."""
    total_weight = 0.0
    weighted = 0.0
    for field, entry in detail.items():
        weight = _SPEC_FIELD_WEIGHTS.get(field, 1.0 / max(len(detail), 1))
        weighted += weight * float(entry.get("score", 1.0))
        total_weight += weight
    if total_weight == 0:
        return 1.0
    return weighted / total_weight


def compare_material_grades(grade_1: Any, grade_2: Any) -> Tuple[float, str]:
    """Grade similarity with metallurgical-family awareness."""
    g1 = str(grade_1).strip().upper() if grade_1 is not None else None
    g2 = str(grade_2).strip().upper() if grade_2 is not None else None
    if g1 is None and g2 is None:
        return 1.0, "no_info"
    if (g1 is None) != (g2 is None):
        return 0.5, "unknown"
    # compact form for equality ("CARBONSTEEL"), spaced form for family lookup
    c1, c2 = g1.replace(" ", ""), g2.replace(" ", "")
    if c1 == c2:
        return 1.0, "match"
    family_1 = grade_family(g1.title()) or grade_family(g1)
    family_2 = grade_family(g2.title()) or grade_family(g2)
    if family_1 and family_1 == family_2:
        return 0.7, "compatible"
    return 0.0, "conflict"


def compute_attribute_scores(attrs_1: Dict[str, Any], attrs_2: Dict[str, Any]) -> Dict[str, Any]:
    """Compute the three attribute-based MIRA components.

    Returns:
        {
          "specification_similarity": 0.0-1.0,
          "material_grade_similarity": 0.0-1.0,
          "other_attributes_similarity": 0.0-1.0,
          "detail": {field: {"v1":..., "v2":..., "score":..., "status":...}},
        }
    """
    attrs_1 = attrs_1 or {}
    attrs_2 = attrs_2 or {}

    # --- specification similarity ---
    spec_detail: Dict[str, Dict[str, Any]] = {}
    for field in _SPEC_FIELD_WEIGHTS:
        v1 = attrs_1.get(field)
        v2 = attrs_2.get(field)
        score, status = compare_field(v1, v2)
        spec_detail[field] = {"v1": v1, "v2": v2, "score": score, "status": status}
    specification_similarity = _weighted_average(spec_detail)

    # --- material grade similarity ---
    grade_score, grade_status = compare_material_grades(
        attrs_1.get("material_grade"), attrs_2.get("material_grade")
    )

    # --- other attributes similarity ---
    other_detail: Dict[str, Dict[str, Any]] = {}
    other_pairs: Dict[str, Tuple[float, str]] = {}
    for field in _OTHER_FIELDS:
        v1 = attrs_1.get(field)
        v2 = attrs_2.get(field)
        score, status = compare_field(v1, v2)
        other_detail[field] = {"v1": v1, "v2": v2, "score": score, "status": status}
        other_pairs[field] = (score, status)
    if other_pairs:
        n = len(other_pairs)
        other_score = sum(score for score, _ in other_pairs.values()) / n
    else:
        other_score = 0.5

    return {
        "specification_similarity": round(specification_similarity, 4),
        "material_grade_similarity": round(grade_score, 4),
        "other_attributes_similarity": round(other_score, 4),
        "detail": {
            "specification": spec_detail,
            "material_grade": {
                "v1": attrs_1.get("material_grade"),
                "v2": attrs_2.get("material_grade"),
                "score": grade_score,
                "status": grade_status,
            },
            "other_attributes": other_detail,
        },
    }

