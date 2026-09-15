from __future__ import annotations

from copy import deepcopy
from typing import Any


UNKNOWN = "UNKNOWN"

# These are the technical fields currently produced by MIRA's parser.
# They are treated as evidence, not inferred values.
CANONICAL_SPEC_FIELDS = (
    "material_grade",
    "pressure_rating",
    "dimensions",
    "dimension_tokens",
    "dished_end_dimensions",
    "nominal_bore",
    "metric_thread",
    "voltage_class",
    "frequency",
    "power",
    "cct",
    "cri",
    "beam_angle",
    "ip_rating",
    "luminous_efficiency",
    "standards",
    "purity",
)


def _normalize_scalar(value: Any) -> Any:
    """Normalize values only for deterministic equality comparison."""
    if isinstance(value, str):
        return value.strip().upper()

    if isinstance(value, dict):
        return {
            str(key): _normalize_scalar(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }

    if isinstance(value, list):
        return [_normalize_scalar(item) for item in value]

    return value


def _same_value(values: list[Any]) -> bool:
    """Return True only when all supplied values are materially identical."""
    if not values:
        return False

    normalized = [_normalize_scalar(value) for value in values]
    return all(value == normalized[0] for value in normalized[1:])


def _known(value: Any) -> bool:
    """Determine whether a source value contains usable evidence."""
    return value is not None and value != "" and value != [] and value != {}


def _source_material(material: dict[str, Any]) -> dict[str, Any]:
    """Build the traceable source representation retained by a CMR."""
    return {
        "material_id": material.get("id"),
        "cpse": material.get("cpse"),
        "material_code": material.get("material_code"),
        "description": material.get("description"),
        "source_file": material.get("source_file"),
        "source_page": material.get("source_page"),
    }


def _canonical_field(
    materials: list[dict[str, Any]],
    field: str,
) -> tuple[Any, bool]:
    """
    Resolve one canonical field.

    A value becomes canonical only when every participating material
    provides evidence and all provided values agree.

    Missing or conflicting evidence becomes UNKNOWN.
    """
    values = []

    for material in materials:
        parsed = material.get("parsed_specifications") or {}

        if field == "material_grade":
            value = material.get("material_grade")
            if not _known(value):
                value = parsed.get(field)
        elif field == "dimensions":
            value = material.get("dimensions")
            if not _known(value):
                value = parsed.get(field)
        else:
            value = parsed.get(field)

            # Some persisted records may carry technical data in
            # specifications rather than parsed_specifications.
            if not _known(value):
                value = (material.get("specifications") or {}).get(field)

        if not _known(value):
            return UNKNOWN, True

        values.append(value)

    if not _same_value(values):
        return UNKNOWN, True

    # Return the first source representation rather than constructing
    # a new technical value.
    return deepcopy(values[0]), False


def build_common_material_record(
    materials: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Build a safe Common Material Record from approved source materials.

    This function does not decide whether materials are equivalent.
    The caller must provide a cluster that has already passed the
    human-approval workflow.

    Canonical values are emitted only when every source agrees.
    Conflicts and missing evidence remain UNKNOWN.
    """
    if not materials:
        raise ValueError("At least one material is required")

    source_materials = [_source_material(material) for material in materials]

    # Category is treated conservatively. A category conflict prevents
    # a single canonical category from being invented.
    categories = [material.get("category") for material in materials]

    if all(_known(category) for category in categories) and _same_value(categories):
        canonical_category = categories[0]
    else:
        canonical_category = UNKNOWN

    # A canonical description is safe only when the normalized source
    # descriptions agree. We never rewrite or synthesize a description.
    normalized_descriptions = [
        material.get("normalized_description")
        for material in materials
    ]

    if (
        all(_known(description) for description in normalized_descriptions)
        and _same_value(normalized_descriptions)
    ):
        canonical_description = normalized_descriptions[0]
    else:
        canonical_description = UNKNOWN

    canonical_technical_attributes: dict[str, Any] = {}
    unknown_fields: list[str] = []

    for field in CANONICAL_SPEC_FIELDS:
        value, is_unknown = _canonical_field(materials, field)
        canonical_technical_attributes[field] = value

        if is_unknown:
            unknown_fields.append(field)

    return {
        "canonical_description": canonical_description,
        "category": canonical_category,
        "canonical_technical_attributes": canonical_technical_attributes,
        "source_materials": source_materials,
        "provenance": {
            "source_count": len(source_materials),
            "material_ids": [
                material.get("id")
                for material in materials
                if material.get("id") is not None
            ],
        },
        "approval_status": "PROVISIONAL",
        "critical_unknown_fields": unknown_fields,
    }
