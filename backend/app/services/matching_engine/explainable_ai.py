"""Explainable AI: human-readable match reasoning.

Produces the JSON payload stored in ``match_suggestions.explanation`` and
rendered by the frontend MatchCard ("Type match: 100%, Size match: 98%").
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.utils.constants import (
    DECISION_DIFFERENT,
    DECISION_HIGH_CONFIDENCE,
    DECISION_REVIEW,
    GATE_CATEGORY_MISMATCH,
    GATE_CONFLICT,
    GATE_PASS,
    GATE_UNKNOWN,
)

_COMPONENT_LABELS = {
    "text": "Description text similarity",
    "semantic": "Semantic similarity (Qwen-1B-Embedding)",
    "specification": "Specification similarity",
    "material_grade": "Material grade similarity",
    "other_attributes": "Other attributes similarity",
}

_STATUS_THRESHOLDS = ((0.85, "match"), (0.5, "partial"))


def _status_for(score: float) -> str:
    for threshold, label in _STATUS_THRESHOLDS:
        if score >= threshold:
            return label
    return "mismatch"


def _pct(score: float) -> int:
    return int(round(score * 100))


def _gate_summary(gate_status: str, gate_detail: Dict[str, Any]) -> str:
    if gate_status == GATE_PASS:
        return "All critical fields verified."
    if gate_status == GATE_CATEGORY_MISMATCH:
        return (
            f"Category mismatch: {gate_detail.get('category_1')} vs "
            f"{gate_detail.get('category_2')}."
        )
    if gate_status == GATE_CONFLICT:
        conflicting = gate_detail.get("field")
        checks = gate_detail.get("checks", [])
        bad = next((c for c in checks if c.get("result") == "conflict"), None)
        if bad:
            return (
                f"Critical field '{conflicting}' conflicts: "
                f"'{bad.get('v1')}' vs '{bad.get('v2')}'."
            )
        return "Conflicting critical fields detected."
    if gate_status == GATE_UNKNOWN:
        return f"Critical field '{gate_detail.get('field')}' is missing on one or both sides."
    return "Gate evaluation unavailable."


def _build_reasons(
    components: Dict[str, float],
    attr_detail: Dict[str, Any],
    attrs_1: Dict[str, Any],
    attrs_2: Dict[str, Any],
) -> list:
    reasons: list = []

    # Type
    t1, t2 = attrs_1.get("type"), attrs_2.get("type")
    if t1 and t2:
        same = 1.0 if t1.upper() == t2.upper() else 0.0
        reasons.append(
            f"Type match: {_pct(same)}% ({t1} vs {t2})"
        )

    # Size / dimensions
    d1 = attrs_1.get("dimensions") or attrs_1.get("size")
    d2 = attrs_2.get("dimensions") or attrs_2.get("size")
    if d1 and d2:
        same = 1.0 if str(d1).upper() == str(d2).upper() else 0.0
        reasons.append(f"Size match: {_pct(same)}% ({d1} vs {d2})")

    # Grade
    g1, g2 = attrs_1.get("material_grade"), attrs_2.get("material_grade")
    if g1 and g2:
        same = 1.0 if g1.upper() == g2.upper() else 0.0
        reasons.append(f"Material grade: {_pct(same)}% ({g1} vs {g2})")

    # Pressure / voltage
    for field, label in (("pressure_rating", "Pressure rating"), ("voltage_class", "Voltage class")):
        v1, v2 = attrs_1.get(field), attrs_2.get(field)
        if v1 and v2:
            same = 1.0 if str(v1).upper() == str(v2).upper() else 0.0
            reasons.append(f"{label}: {_pct(same)}% ({v1} vs {v2})")

    return reasons


def generate_explanation(
    decision,
    attr_detail: Optional[Dict[str, Any]] = None,
    attrs_1: Optional[Dict[str, Any]] = None,
    attrs_2: Optional[Dict[str, Any]] = None,
    material_code_1: Optional[str] = None,
    material_code_2: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the full explanation payload for a MatchDecision.

    ``decision`` is a ``MatchDecision`` dataclass from ensemble_ranker.
    """
    attr_detail = attr_detail or {}
    attrs_1 = attrs_1 or {}
    attrs_2 = attrs_2 or {}

    components_out = []
    for key, label in _COMPONENT_LABELS.items():
        score = decision.components.get(key, 0.0)
        components_out.append(
            {
                "key": key,
                "label": label,
                "score": score,
                "score_pct": _pct(score),
                "weighted_contribution": decision.contributions.get(key, 0.0),
                "status": _status_for(score),
            }
        )

    decision_label = {
        DECISION_HIGH_CONFIDENCE: "High confidence match - ready for review",
        DECISION_REVIEW: "Requires human review",
        DECISION_DIFFERENT: "Materials are different",
    }.get(decision.decision, decision.decision)

    if decision.decision == DECISION_HIGH_CONFIDENCE:
        summary = (
            f"High confidence match ({_pct(decision.final_confidence)}%): "
            + ", ".join(
                f"{c['key']} {_pct(c['score'])}%" for c in components_out[:3]
            )
        )
    elif decision.decision == DECISION_DIFFERENT:
        summary = (
            f"Materials are different (combined score {_pct(decision.final_confidence)}%, "
            f"below the {_pct(0.45)}% threshold)."
        )
    else:
        summary = (
            f"Score {_pct(decision.final_confidence)}% - {decision_label}. "
            f"{_gate_summary(decision.gate_status, decision.gate_detail)}"
        )

    return {
        "decision": decision.decision,
        "decision_label": decision_label,
        "final_confidence": decision.final_confidence,
        "final_confidence_pct": _pct(decision.final_confidence),
        "summary": summary,
        "components": components_out,
        "gate": {
            "status": decision.gate_status,
            "detail": decision.gate_detail,
            "summary": _gate_summary(decision.gate_status, decision.gate_detail),
        },
        "attribute_detail": attr_detail,
        "reasons": _build_reasons(decision.components, attr_detail, attrs_1, attrs_2),
        "material_1_code": material_code_1,
        "material_2_code": material_code_2,
    }

