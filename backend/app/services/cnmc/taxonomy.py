from __future__ import annotations

import re
from typing import Any


# Standard category definitions: (Type Code, Category Code)
# Short deterministic MIRA type codes with stable category numbers.
TAXONOMY_MAP: dict[str, tuple[str, str]] = {
    "VALVE": ("VLV", "17"),
    "VALVES": ("VLV", "17"),
    "GATE VALVE": ("VLV", "17"),
    "GLOBE VALVE": ("VLV", "17"),
    "BALL VALVE": ("VLV", "17"),
    "CHECK VALVE": ("VLV", "17"),
    "BUTTERFLY VALVE": ("VLV", "17"),
    "PIPE": ("PIP", "23"),
    "PIPES": ("PIP", "23"),
    "PIPING": ("PIP", "23"),
    "TUBE": ("PIP", "23"),
    "TUBING": ("PIP", "23"),
    "BEARING": ("BRG", "08"),
    "BEARINGS": ("BRG", "08"),
    "BALL BEARING": ("BRG", "08"),
    "ROLLER BEARING": ("BRG", "08"),
    "FASTENER": ("FST", "12"),
    "FASTENERS": ("FST", "12"),
    "BOLT": ("FST", "12"),
    "NUT": ("FST", "12"),
    "SCREW": ("FST", "12"),
    "STUD": ("FST", "12"),
    "ELECTRICAL CONNECTOR": ("ELC", "31"),
    "ELECTRICAL": ("ELC", "31"),
    "CONNECTOR": ("ELC", "31"),
    "GASKET": ("GSK", "14"),
    "GASKETS": ("GSK", "14"),
    "CABLE": ("CBL", "26"),
    "CABLES": ("CBL", "26"),
    "WIRE": ("CBL", "26"),
    "FLANGE": ("FLG", "19"),
    "FLANGES": ("FLG", "19"),
    "PUMP": ("PMP", "45"),
    "PUMPS": ("PMP", "45"),
}

# Regex keywords for inferring material category if category is UNKNOWN / General
KEYWORD_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:VALVE|GATE\s+VALVE|GLOBE\s+VALVE|BALL\s+VALVE|CHECK\s+VALVE|BUTTERFLY\s+VALVE)\b", re.I), "VALVE"),
    (re.compile(r"\b(?:PIPE|PIPING|SEAMLESS\s+PIPE|ERW\s+PIPE|TUBE)\b", re.I), "PIPE"),
    (re.compile(r"\b(?:BEARING|BRG|ROLLER\s+BEARING|BALL\s+BEARING)\b", re.I), "BEARING"),
    (re.compile(r"\b(?:FASTENER|BOLT|NUT|SCREW|STUD\s+BOLT)\b", re.I), "FASTENER"),
    (re.compile(r"\b(?:ELECTRICAL\s+CONNECTOR|CONNECTOR|TERMINAL\s+BLOCK)\b", re.I), "ELECTRICAL CONNECTOR"),
    (re.compile(r"\b(?:GASKET|SPIRAL\s+WOUND\s+GASKET)\b", re.I), "GASKET"),
    (re.compile(r"\b(?:CABLE|POWER\s+CABLE|CONTROL\s+CABLE|WIRE)\b", re.I), "CABLE"),
    (re.compile(r"\b(?:FLANGE|WNRF|BLRF|SORF)\b", re.I), "FLANGE"),
    (re.compile(r"\b(?:PUMP|CENTRIFUGAL\s+PUMP)\b", re.I), "PUMP"),
]


def _normalize_category_name(category: str | None) -> str:
    return (category or "").strip().upper()


def resolve_type_and_category(
    category: str | None = None,
    canonical_description: str | None = None,
    materials: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    """
    Deterministically resolve the (TYPE, CATEGORY) code pair for CNMC generation.

    Returns:
        (type_code, category_code), e.g. ("VLV", "17")
    """
    # 1. Try direct category resolution
    norm_cat = _normalize_category_name(category)
    if norm_cat and norm_cat not in ("UNKNOWN", "GENERAL", "UNCATEGORISED", "UNCATEGORIZED", ""):
        if norm_cat in TAXONOMY_MAP:
            return TAXONOMY_MAP[norm_cat]

    # 2. Try materials list if any material provides a specific category
    if materials:
        for mat in materials:
            mat_cat = _normalize_category_name(mat.get("category"))
            if mat_cat and mat_cat not in ("UNKNOWN", "GENERAL", "UNCATEGORISED", "UNCATEGORIZED", ""):
                if mat_cat in TAXONOMY_MAP:
                    return TAXONOMY_MAP[mat_cat]

    # 3. Infer from canonical description or material descriptions
    candidate_texts: list[str] = []
    if canonical_description and canonical_description != "UNKNOWN":
        candidate_texts.append(canonical_description)

    if materials:
        for mat in materials:
            desc = mat.get("normalized_description") or mat.get("description")
            if desc:
                candidate_texts.append(desc)

    for text in candidate_texts:
        for pattern, matched_cat in KEYWORD_PATTERNS:
            if pattern.search(text):
                return TAXONOMY_MAP[matched_cat]

    # 4. Fallback for custom or unknown categories
    if norm_cat and norm_cat not in ("UNKNOWN", "GENERAL", "UNCATEGORISED", "UNCATEGORIZED", ""):
        # Generate a clean 3-character uppercase alphanumeric code
        clean_name = re.sub(r"[^A-Z0-9]", "", norm_cat)
        type_code = (clean_name[:3] if len(clean_name) >= 3 else clean_name.ljust(3, "X"))
        return (type_code, "01")

    return ("GEN", "01")
