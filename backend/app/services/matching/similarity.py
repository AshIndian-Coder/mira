from difflib import SequenceMatcher
from typing import Any

from app.services.matching.embeddings import semantic_similarity


CATEGORY_SPEC_FIELDS = {
    "FASTENER": [
        "material_grade",
        "dimensions",
    ],
    "VALVE": [
        "material_grade",
        "pressure_rating",
        "dimensions",
    ],
    "PIPE": [
        "material_grade",
        "pressure_rating",
        "dimensions",
    ],
    "ELECTRICAL CONNECTOR": [
        "voltage_class",
        "dimensions",
    ],
}


def text_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0

    left = left.upper().strip()
    right = right.upper().strip()

    if left == right:
        return 1.0

    return SequenceMatcher(None, left, right).ratio()


def value_similarity(left: Any, right: Any) -> float:
    if left is None or right is None:
        return 0.0

    if left == right:
        return 1.0

    return 0.0


def specification_similarity(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
    category: str | None = None,
) -> float:
    left = left or {}
    right = right or {}

    normalized_category = (category or "").strip().upper()

    fields = CATEGORY_SPEC_FIELDS.get(normalized_category)

    if fields is None:
        fields = set(left) | set(right)

    scores = []

    for field in fields:
        left_value = left.get(field)
        right_value = right.get(field)

        if left_value is None and right_value is None:
            continue

        if left_value is None or right_value is None:
            scores.append(0.0)
            continue

        if isinstance(left_value, dict) and isinstance(right_value, dict):
            if (
                left_value.get("value") == right_value.get("value")
                and left_value.get("unit") == right_value.get("unit")
            ):
                scores.append(1.0)
            else:
                scores.append(0.0)
        else:
            scores.append(value_similarity(left_value, right_value))

    if not scores:
        return 1.0

    return sum(scores) / len(scores)
