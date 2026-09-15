"""
Attribute-level comparison (specification, grade, other attributes).

Implements the 0.35 / 0.15 / 0.10 components of the MIRA hybrid score and
the deterministic critical gates required by the MIRA specification.

Critical fields are category-specific and frozen:
  * FASTENER                -> material_grade, dimensions
  * VALVE                   -> pressure_rating, dimensions
  * PIPE                    -> pressure_rating, dimensions
  * ELECTRICAL CONNECTOR    -> voltage_class, dimensions
  * default                 -> dimensions

Missing applicable critical field   -> UNKNOWN  -> REVIEW
Conflicting critical field          -> CONFLICT -> REVIEW
Category mismatch                   -> CONFLICT -> REVIEW
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.utils.constants import (
    CRITICAL_FIELDS,
    DEFAULT_CRITICAL_FIELDS,
    GATE_CATEGORY_MISMATCH,
    GATE_CONFLICT,
    GATE_PASS,
    GATE_UNKNOWN,
    WEIGHT_MATERIAL_GRADE,
    WEIGHT_OTHER_ATTRIBUTES,
    WEIGHT_SPECIFICATION,
)

_TOKEN_RE = re.compile(r"[^\w]+")


def _norm_tokens(value: Any) -> List[str]:
    if value is None:
        return []
    text = str(value).upper().strip()
    return [t for t in _TOKEN_RE.split(text) if t]


def _norm_num(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    text = _TOKEN_RE.sub("", text)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _num_match(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None and b is None:
        return 1.0
    if a is None or b is None:
        return 0.0
    if a == b:
        return 1.0
    if a == 0 or b == 0:
        return 0.0
    ratio = a / b if a > b else b / a
    if ratio >= 0.95:
        return 1.0
    if ratio >= 0.8:
        return 0.5
    return 0.0


def _norm_set(value: Any) -> set:
    if value is None:
        return set()
    text = str(value).upper().strip()
    if not text:
        return set()
    return {t for t in _TOKEN_RE.split(text) if t}




_spec_field_weights: Dict[str, float] = {
    "dimensions": 0.30,
    "pressure_rating": 0.20,
    "voltage_class": 0.20,
    "size": 0.15,
    "standard": 0.05,
    "material": 0.05,
    "color": 0.02,
    "finish": 0.02,
    "length": 0.01,
}


def compute_specification_similarity(attrs1: Dict[str, Any], attrs2: Dict[str, Any]) -> Dict[str, Any]:
    """Compute specification similarity + per-field breakdown."""
    detail: Dict[str, Any] = {}
    weighted_sum = 0.0
    weight_total = 0.0

    for field, weight in _spec_field_weights.items():
        v1 = attrs1.get(field)
        v2 = attrs2.get(field)
        score = _field_similarity(field, v1, v2)
        detail[field] = {"score": score, "value_1": v1, "value_2": v2}
        weighted_sum += score * weight
        weight_total += weight

    overall = weighted_sum / weight_total if weight_total > 0 else 0.0
    return {
        "specification_similarity": overall,
        "detail": detail,
    }


def _field_similarity(field: str, v1: Any, v2: Any) -> float:
    if v1 is None and v2 is None:
        return 1.0
    if v1 is None or v2 is None:
        return 0.0

    if field in ("dimensions", "pressure_rating", "voltage_class", "size", "length"):
        return float(_num_match(_norm_num(v1), _norm_num(v2)))

    if field in ("standard", "material", "color", "finish"):
        return float(len(_norm_set(v1) & _norm_set(v2)) / max(1, len(_norm_set(v1) | _norm_set(v2))))

    t1, t2 = _norm_tokens(v1), _norm_tokens(v2)
    if not t1 and not t2:
        return 1.0
    return float(len(set(t1) & set(t2)) / max(1, len(set(t1) | set(t2))))




_GRADE_LEVELS = {
    "mild steel": 1,
    "carbon steel": 2,
    "stainless steel": 3,
    "alloy steel": 4,
    "tool steel": 5,
    "aluminium": 6,
    "brass": 7,
    "bronze": 8,
    "copper": 9,
    "plastic": 10,
    "rubber": 11,
    "ptfe": 12,
}

_GRADE_PATTERNS = [
    (r"\b(8\.8|10\.9|12\.9)\b", 10),
    (r"\b(70|80|100)\b", 5),
    (r"\b(a2|304|316|316l)\b", 3),
    (r"\b(cs|ms|carbon)\b", 2),
    (r"\b(ms|mild)\b", 1),
]


def compute_material_grade_similarity(attrs1: Dict[str, Any], attrs2: Dict[str, Any]) -> Dict[str, Any]:
    """Material grade similarity (0..1)."""
    g1 = _normalize_grade(attrs1.get("material_grade") or attrs1.get("material") or "")
    g2 = _normalize_grade(attrs2.get("material_grade") or attrs2.get("material") or "")
    return {
        "material_grade_similarity": _grade_distance(g1, g2),
        "detail": {"grade_1": g1, "grade_2": g2},
    }


def _normalize_grade(value: Any) -> str:
    if not value:
        return ""
    text = str(value).upper()
    for pattern, _ in _GRADE_PATTERNS:
        if re.search(pattern, text):
            return text
    return text


def _grade_distance(g1: str, g2: str) -> float:
    if not g1 and not g2:
        return 1.0
    if not g1 or not g2:
        return 0.0
    if g1 == g2:
        return 1.0
    l1 = _grade_level(g1)
    l2 = _grade_level(g2)
    if l1 is None or l2 is None:
        return 0.0
    if l1 == l2:
        return 0.8
    return 0.0


def _grade_level(grade: str) -> Optional[int]:
    text = grade.upper()
    if "STAINLESS" in text:
        return _GRADE_LEVELS["stainless steel"]
    if "ALLOY" in text:
        return _GRADE_LEVELS["alloy steel"]
    if "TOOL" in text:
        return _GRADE_LEVELS["tool steel"]
    if "CARBON" in text:
        return _GRADE_LEVELS["carbon steel"]
    if "MILD" in text:
        return _GRADE_LEVELS["mild steel"]
    if "ALUMINIUM" in text:
        return _GRADE_LEVELS["aluminium"]
    if "BRASS" in text:
        return _GRADE_LEVELS["brass"]
    if "BRONZE" in text:
        return _GRADE_LEVELS["bronze"]
    if "COPPER" in text:
        return _GRADE_LEVELS["copper"]
    for pattern, level in _GRADE_PATTERNS:
        if re.search(pattern, text):
            return level
    return None




_OTHER_FIELD_WEIGHTS: Dict[str, float] = {
    "seal_type": 0.25,
    "bearing_type": 0.20,
    "bearing_seal": 0.15,
    "bearing_lubrication": 0.10,
    "connection_type": 0.10,
    "number_of_poles": 0.05,
    "phase": 0.05,
    "frequency": 0.05,
    "brand": 0.05,
}


def compute_other_attributes_similarity(attrs1: Dict[str, Any], attrs2: Dict[str, Any]) -> Dict[str, Any]:
    """Similarity over non-critical-but-relevant attributes."""
    detail: Dict[str, Any] = {}
    weighted_sum = 0.0
    weight_total = 0.0

    for field, weight in _OTHER_FIELD_WEIGHTS.items():
        v1 = attrs1.get(field)
        v2 = attrs2.get(field)
        score = _other_field_similarity(field, v1, v2)
        detail[field] = {"score": score, "value_1": v1, "value_2": v2}
        weighted_sum += score * weight
        weight_total += weight

    overall = weighted_sum / weight_total if weight_total > 0 else 0.0
    return {
        "other_attributes_similarity": overall,
        "detail": detail,
    }


def _other_field_similarity(field: str, v1: Any, v2: Any) -> float:
    if v1 is None and v2 is None:
        return 1.0
    if v1 is None or v2 is None:
        return 0.0
    t1, t2 = _norm_tokens(v1), _norm_tokens(v2)
    if not t1 and not t2:
        return 1.0
    return float(len(set(t1) & set(t2)) / max(1, len(set(t1) | set(t2))))




def compute_attribute_scores(
    attrs1: Dict[str, Any],
    attrs2: Dict[str, Any],
) -> Dict[str, Any]:
    """Combine specification / grade / other into the attribute component."""
    spec = compute_specification_similarity(attrs1, attrs2)
    grade = compute_material_grade_similarity(attrs1, attrs2)
    other = compute_other_attributes_similarity(attrs1, attrs2)

    combined = (
        WEIGHT_SPECIFICATION * spec["specification_similarity"]
        + WEIGHT_MATERIAL_GRADE * grade["material_grade_similarity"]
        + WEIGHT_OTHER_ATTRIBUTES * other["other_attributes_similarity"]
    )

    detail = {}
    detail.update(spec["detail"])
    detail.update(grade["detail"])
    detail.update(other["detail"])

    return {
        "specification_similarity": spec["specification_similarity"],
        "material_grade_similarity": grade["material_grade_similarity"],
        "other_attributes_similarity": other["other_attributes_similarity"],
        "attribute_similarity": combined,
        "detail": detail,
    }




def apply_critical_gates(
    attrs1: Dict[str, Any],
    attrs2: Dict[str, Any],
    category1: Optional[str],
    category2: Optional[str],
) -> Tuple[bool, List[str]]:
    """Apply deterministic MIRA critical gates.

    Returns (gates_pass, reasons).
    """
    reasons: List[str] = []

    cat1 = (category1 or "").upper().strip()
    cat2 = (category2 or "").upper().strip()

    if cat1 and cat2 and cat1 != cat2:
        reasons.append("CATEGORY_MISMATCH")
        return False, reasons

    critical_fields = _critical_fields_for(cat1 or cat2 or "")
    for field in critical_fields:
        v1 = attrs1.get(field)
        v2 = attrs2.get(field)
        if v1 is None and v2 is None:
            reasons.append(f"MISSING:{field}")
            continue
        if v1 is None or v2 is None:
            reasons.append(f"MISSING:{field}")
            continue
        if not _critical_field_match(field, v1, v2):
            reasons.append(f"CONFLICT:{field}")

    gates_pass = len(reasons) == 0
    return gates_pass, reasons


def _critical_fields_for(category: str) -> List[str]:
    upper = category.upper().strip()
    for key, fields in CRITICAL_FIELDS.items():
        if key.upper() == upper:
            return list(fields)
    return list(DEFAULT_CRITICAL_FIELDS)


def _critical_field_match(field: str, v1: Any, v2: Any) -> bool:
    if field == "dimensions":
        return _num_match(_norm_num(v1), _norm_num(v2)) >= 0.95
    if field in ("pressure_rating", "voltage_class"):
        return _num_match(_norm_num(v1), _norm_num(v2)) == 1.0
    if field == "material_grade":
        return _grade_distance(_normalize_grade(v1), _normalize_grade(v2)) >= 0.8
    return _norm_tokens(v1) == _norm_tokens(v2)
