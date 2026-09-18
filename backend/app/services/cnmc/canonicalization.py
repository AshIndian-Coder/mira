from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.services.cnmc.taxonomy import resolve_type_and_category


CATEGORY_IDENTITY_FIELDS: dict[str, list[str]] = {
    "VALVE": [
        "material_grade",
        "pressure_rating",
        "nominal_bore",
        "dimensions",
        "schedule",
        "standards",
    ],
    "PIPE": [
        "material_grade",
        "nominal_bore",
        "dimensions",
        "schedule",
        "pressure_rating",
        "standards",
    ],
    "BEARING": [
        "bearing",
        "dimensions",
        "standards",
    ],
    "FASTENER": [
        "material_grade",
        "metric_thread",
        "dimensions",
        "standards",
    ],
    "ELECTRICAL CONNECTOR": [
        "voltage_class",
        "power",
        "frequency",
        "ip_rating",
        "dimensions",
        "material_grade",
        "standards",
    ],
    "GASKET": [
        "material_grade",
        "dimensions",
        "pressure_rating",
        "standards",
    ],
    "CABLE": [
        "voltage_class",
        "dimensions",
        "standards",
    ],
    "FLANGE": [
        "material_grade",
        "pressure_rating",
        "nominal_bore",
        "dimensions",
        "schedule",
        "standards",
    ],
    "PUMP": [
        "power",
        "frequency",
        "voltage_class",
        "dimensions",
        "standards",
    ],
}


def _canonical_unit(unit: Any) -> str:
    unit_str = str(unit or "").strip().upper()
    aliases = {
        "INCH": "IN",
        "INCHES": "IN",
        '"': "IN",
        "MILLIMETER": "MM",
        "MILLIMETERS": "MM",
        "MILLIMETRE": "MM",
        "MILLIMETRES": "MM",
        "POUND": "LB",
        "POUNDS": "LB",
        "LBS": "LB",
        "#": "LB",
        "KILOVOLT": "KV",
        "VOLT": "V",
        "VOLTS": "V",
    }
    return aliases.get(unit_str, unit_str)


def _format_number(val: float | int) -> str:
    try:
        f = float(val)
        if f.is_integer():
            return str(int(f))
        return f"{f:g}"
    except (ValueError, TypeError):
        return str(val).strip().upper()


def _canonical_value_repr(value: Any) -> str:
    """
    Format attribute values deterministically.
    Missing/unknown values remain explicitly UNKNOWN.
    """
    if value is None or value == "" or value == "UNKNOWN":
        return "UNKNOWN"

    if isinstance(value, (int, float)):
        return _format_number(value)

    if isinstance(value, str):
        val = value.strip().upper()
        return val if val else "UNKNOWN"

    if isinstance(value, dict):
        if "value" in value and "unit" in value:
            num = _format_number(value["value"])
            unit = _canonical_unit(value["unit"])
            return f"{num}{unit}" if unit else num

        if "min" in value and "max" in value:
            min_v = _format_number(value["min"])
            max_v = _format_number(value["max"])
            unit = _canonical_unit(value.get("unit"))
            return f"{min_v}-{max_v}{unit}" if unit else f"{min_v}-{max_v}"

        # General dictionary: sort keys deterministically
        pairs = []
        for k in sorted(value.keys()):
            v_repr = _canonical_value_repr(value[k])
            if v_repr != "UNKNOWN":
                pairs.append(f"{str(k).upper()}={v_repr}")
        return "{" + ",".join(pairs) + "}" if pairs else "UNKNOWN"

    if isinstance(value, (list, tuple, set)):
        items = sorted([_canonical_value_repr(x) for x in value if _canonical_value_repr(x) != "UNKNOWN"])
        return "[" + ",".join(items) + "]" if items else "UNKNOWN"

    return str(value).strip().upper()


def build_canonical_identity_string(
    cmr: dict[str, Any],
    type_code: str,
    category_code: str,
) -> str:
    """
    Construct a deterministic canonical identity string from the Common Material Record.
    """
    category = (cmr.get("category") or "").strip().upper()
    tech_attrs = cmr.get("canonical_technical_attributes") or {}

    # Select category-specific identity fields
    identity_fields = CATEGORY_IDENTITY_FIELDS.get(category)
    if identity_fields is None:
        # Fallback to all present technical attributes sorted alphabetically
        identity_fields = sorted(tech_attrs.keys())

    parts: list[str] = [
        f"MIRA_TYPE:{type_code}",
        f"MIRA_CAT:{category_code}",
    ]

    for field in identity_fields:
        val = tech_attrs.get(field)
        val_repr = _canonical_value_repr(val)
        parts.append(f"{field.upper()}:{val_repr}")

    return "|".join(parts)


def compute_identity_hash(canonical_identity_string: str) -> str:
    """
    Compute SHA-256 machine identity fingerprint.
    """
    return hashlib.sha256(canonical_identity_string.encode("utf-8")).hexdigest()
