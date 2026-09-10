from typing import Any
from app.services.matching.similarity import value_similarity

# Critical fields by material category.
#
# Only fields applicable to the category are evaluated.
CRITICAL_FIELDS = {
    "FASTENER": [
        "material_grade",
        "dimensions",
    ],
    "VALVE": [
        "pressure_rating",
        "dimensions",
    ],
    "PIPE": [
        "pressure_rating",
        "dimensions",
    ],
    "ELECTRICAL CONNECTOR": [
        "voltage_class",
        "dimensions",
    ],
}


def _normalize_category(category: str | None) -> str:
    return (category or "").strip().upper()


def _get_field(
    material: dict[str, Any],
    field: str,
) -> Any:
    """
    Retrieve a field from either the top-level material
    or parsed specifications.
    """

    if field in material:
        return material.get(field)

    specifications = material.get("parsed_specifications") or {}

    return specifications.get(field)


def compare_critical_field(
    source: dict[str, Any],
    target: dict[str, Any],
    field: str,
) -> dict[str, Any]:

    source_value = _get_field(source, field)
    target_value = _get_field(target, field)

    if source_value is None and target_value is None:
        return {
            "field": field,
            "status": "UNKNOWN",
            "source_value": None,
            "target_value": None,
            "reason": "Critical field unavailable in both materials.",
        }

    if source_value is None:
        return {
            "field": field,
            "status": "UNKNOWN",
            "source_value": None,
            "target_value": target_value,
            "reason": "Critical field missing from source material.",
        }

    if target_value is None:
        return {
            "field": field,
            "status": "UNKNOWN",
            "source_value": source_value,
            "target_value": None,
            "reason": "Critical field missing from target material.",
        }

    if value_similarity(source_value, target_value) == 1.0:
        return {
            "field": field,
            "status": "PASS",
            "source_value": source_value,
            "target_value": target_value,
            "reason": "Critical values match after normalization.",
        }

    return {
        "field": field,
        "status": "CONFLICT",
        "source_value": source_value,
        "target_value": target_value,
        "reason": "Critical values conflict.",
    }


def evaluate_critical_gates(
    source: dict[str, Any],
    target: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Evaluate category-specific critical fields.

    UNKNOWN and CONFLICT are deliberately preserved rather
    than converted into a positive match.
    """

    source_category = _normalize_category(source.get("category"))
    target_category = _normalize_category(target.get("category"))

    # Different categories are themselves a review condition.
    if source_category != target_category:
        return [
            {
                "field": "category",
                "status": "CONFLICT",
                "source_value": source_category,
                "target_value": target_category,
                "reason": "Material categories differ.",
            }
        ]

    fields = CRITICAL_FIELDS.get(source_category, [])

    return [
        compare_critical_field(source, target, field)
        for field in fields
    ]


def gates_allow_high_confidence(
    checks: list[dict[str, Any]],
) -> bool:
    """
    HIGH_CONFIDENCE is allowed only when every applicable
    critical field passes.
    """

    return bool(checks) and all(
        check["status"] == "PASS"
        for check in checks
    )
