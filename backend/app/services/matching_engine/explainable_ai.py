from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.matching_engine.ensemble_ranker import MatchDecision


def generate_explanation(
    decision: MatchDecision,
    attribute_details: Optional[Dict[str, Any]] = None,
    attributes_1: Optional[Dict[str, Any]] = None,
    attributes_2: Optional[Dict[str, Any]] = None,
    material_code_1: Optional[str] = None,
    material_code_2: Optional[str] = None,
) -> Dict[str, Any]:
    """Produce a structured explanation dict for a scored match."""
    attr_details = attribute_details or {}

    summary = _build_summary(decision)
    contributing_factors = _contributing_factors(decision, attr_details)
    gate_explanation = _gate_explanation(decision)
    material_highlights = _material_highlights(
        attributes_1 or {},
        attributes_2 or {},
        material_code_1,
        material_code_2,
    )
    review_guidance = _review_guidance(decision, attr_details)

    return {
        "decision": decision.decision,
        "final_confidence": round(decision.final_confidence, 4),
        "gate_status": decision.gate_status,
        "gate_reasons": decision.gate_reasons,
        "component_scores": {
            "text_similarity": round(decision.text_similarity, 4),
            "semantic_similarity": round(decision.semantic_similarity, 4),
            "specification_similarity": round(decision.specification_similarity, 4),
            "material_grade_similarity": round(decision.material_grade_similarity, 4),
            "other_attributes_similarity": round(decision.other_attributes_similarity, 4),
        },
        "summary": summary,
        "contributing_factors": contributing_factors,
        "gate_explanation": gate_explanation,
        "material_highlights": material_highlights,
        "review_guidance": review_guidance,
    }


def _build_summary(decision: MatchDecision) -> str:
    score = decision.final_confidence
    decision_label = decision.decision
    gate = decision.gate_status

    if decision_label == "HIGH_CONFIDENCE":
        return (
            f"High-confidence match ({score:.1%}). "
            f"Critical gates passed; the materials are very likely equivalent."
        )
    if decision_label == "DIFFERENT":
        return (
            f"Low-confidence match ({score:.1%}). "
            f"The materials appear to be different."
        )
    reasons = []
    if gate != GATE_PASS:
        reasons.append(f"critical gate issue ({gate})")
    if score < 0.65:
        reasons.append("low overall score")
    elif score < 0.85:
        reasons.append("moderate score")
    reason_str = " and ".join(reasons) if reasons else "review recommended"
    return f"Review recommended ({score:.1%}). {reason_str}."


def _contributing_factors(decision: MatchDecision, details: Dict[str, Any]) -> List[Dict[str, Any]]:
    factors: List[Dict[str, Any]] = []

    components = [
        ("text_similarity", decision.text_similarity),
        ("semantic_similarity", decision.semantic_similarity),
        ("specification_similarity", decision.specification_similarity),
        ("material_grade_similarity", decision.material_grade_similarity),
        ("other_attributes_similarity", decision.other_attributes_similarity),
    ]
    components.sort(key=lambda x: x[1], reverse=True)
    for name, value in components:
        factors.append({
            "factor": name,
            "score": round(value, 4),
            "strength": _strength_label(value),
        })

    for field, info in details.items():
        if not isinstance(info, dict):
            continue
        score = info.get("score", 0)
        if score <= 0:
            factors.append({
                "factor": f"attribute:{field}",
                "score": round(score, 4),
                "strength": "conflict" if score == 0 else "weak",
                "note": f"Mismatch on {field}",
            })

    factors.sort(key=lambda x: x["score"], reverse=True)
    return factors[:8]


def _gate_explanation(decision: MatchDecision) -> Dict[str, Any]:
    if decision.gate_status == GATE_PASS:
        return {"status": "PASS", "message": "Critical gates passed."}
    reasons = decision.gate_reasons or []
    if GATE_CATEGORY_MISMATCH in reasons:
        return {"status": GATE_CATEGORY_MISMATCH, "message": "Category mismatch detected."}
    conflicts = [r for r in reasons if r.startswith("CONFLICT:")]
    missing = [r for r in reasons if r.startswith("MISSING:")]
    parts: List[str] = []
    if conflicts:
        fields = [r.split(":", 1)[1] for r in conflicts]
        parts.append(f"Conflicting critical fields: {', '.join(fields)}")
    if missing:
        fields = [r.split(":", 1)[1] for r in missing]
        parts.append(f"Missing critical fields: {', '.join(fields)}")
    return {"status": decision.gate_status, "message": ". ".join(parts)}


def _material_highlights(
    attrs1: Dict[str, Any],
    attrs2: Dict[str, Any],
    code1: Optional[str],
    code2: Optional[str],
) -> Dict[str, Any]:
    fields_of_interest = ["dimensions", "pressure_rating", "voltage_class", "material_grade", "seal_type", "standard"]
    highlights: List[Dict[str, Any]] = []
    for field in fields_of_interest:
        v1 = attrs1.get(field)
        v2 = attrs2.get(field)
        if v1 is not None or v2 is not None:
            highlights.append({
                "field": field,
                "value_1": v1,
                "value_2": v2,
                "match": v1 == v2 if v1 is not None and v2 is not None else None,
            })
    return {
        "material_code_1": code1,
        "material_code_2": code2,
        "highlights": highlights,
    }


def _review_guidance(decision: MatchDecision, details: Dict[str, Any]) -> List[str]:
    guidance: List[str] = []
    if decision.decision == DECISION_HIGH_CONFIDENCE:
        guidance.append("Reviewer may approve if the materials are indeed equivalent.")
        guidance.append("Check the material codes and categories before approving.")
    elif decision.decision == DECISION_DIFFERENT:
        guidance.append("These materials appear different. Reject if confirmed.")
        guidance.append("If they are actually the same, add a note explaining why.")
    else:  # REVIEW
        guidance.append("Review the conflicting or missing critical fields below.")
        for field, info in details.items():
            if not isinstance(info, dict):
                continue
            score = info.get("score", 0)
            if score == 0:
                guidance.append(f"Resolve {field} mismatch (values differ).")
            elif score < 0.5:
                guidance.append(f"Verify {field} — partial match.")
        guidance.append("Use the comment field to capture the reviewer's reasoning.")
    return guidance


def _strength_label(value: float) -> str:
    if value >= 0.85:
        return "strong"
    if value >= 0.65:
        return "moderate"
    if value >= 0.45:
        return "weak"
    return "low"
