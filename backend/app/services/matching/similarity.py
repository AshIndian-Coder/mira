import ctypes
from difflib import SequenceMatcher
import os
from typing import Any

# Optional C-accelerated SequenceMatcher loader
_c_sequence_matcher = None
try:
    _lib_path = os.path.join(os.path.dirname(__file__), "_fast_sequence_matcher.so")
    if os.path.exists(_lib_path):
        _lib = ctypes.CDLL(_lib_path)
        _lib.fast_sequence_matcher_ratio.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        _lib.fast_sequence_matcher_ratio.restype = ctypes.c_double
        _c_sequence_matcher = _lib.fast_sequence_matcher_ratio
except Exception:
    _c_sequence_matcher = None


CATEGORY_SPEC_FIELDS = {
    "FASTENER": [
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


def text_similarity(left: str, right: str) -> float:
    left = (left or "").upper().strip()
    right = (right or "").upper().strip()

    if not left or not right:
        return 0.0

    if left == right:
        return 1.0

    if _c_sequence_matcher is not None:
        try:
            return float(_c_sequence_matcher(left.encode("utf-8"), right.encode("utf-8")))
        except Exception:
            pass

    return SequenceMatcher(None, left, right).ratio()


def _numeric_value(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def numeric_value_similarity(
    left: dict[str, Any],
    right: dict[str, Any],
) -> float:
    """
    Compare structured numeric values with unit conversion.

    Currently supports dimensions:
      MM <-> IN
    """

    left_value = _numeric_value(left.get("value"))
    right_value = _numeric_value(right.get("value"))

    if left_value is None or right_value is None:
        return 0.0

    left_unit = str(left.get("unit", "")).upper()
    right_unit = str(right.get("unit", "")).upper()

    if left_unit in {"INCH", "INCHES"}:
        left_unit = "IN"

    if right_unit in {"INCH", "INCHES"}:
        right_unit = "IN"

    # Convert inches to millimetres.
    if left_unit == "IN":
        left_value *= 25.4

    if right_unit == "IN":
        right_value *= 25.4

    if left_unit == "MM" and right_unit == "MM":
        return 1.0 if abs(left_value - right_value) < 1e-6 else 0.0

    if left_unit == right_unit:
        return 1.0 if abs(left_value - right_value) < 1e-6 else 0.0

    return 0.0


def value_similarity(left: Any, right: Any) -> float:
    if left is None or right is None:
        return 0.0

    if left == "" or right == "":
        return 0.0

    if isinstance(left, dict) and isinstance(right, dict):

        if (
            "value" in left
            and "value" in right
            and "unit" in left
            and "unit" in right
        ):
            return numeric_value_similarity(left, right)

    if isinstance(left, (list, tuple, set)) and len(left) == 0:
        return 0.0

    if isinstance(right, (list, tuple, set)) and len(right) == 0:
        return 0.0

    if isinstance(left, dict) and len(left) == 0:
        return 0.0

    if isinstance(right, dict) and len(right) == 0:
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
        fields = (set(left) | set(right)) - {"material_grade"}

    scores = []

    for field in fields:
        left_value = left.get(field)
        right_value = right.get(field)

        # Neither material provides this field.
        if left_value is None and right_value is None:
            continue

        # One side is missing.
        if left_value is None or right_value is None:
            scores.append(0.0)
            continue

        scores.append(
            value_similarity(
                left_value,
                right_value,
            )
        )

    if not scores:
        return 0.0

    return sum(scores) / len(scores)

# Compatibility wrapper used by the scorer.
# Keeps semantic embedding logic in embeddings.py while exposing
# the expected similarity API.
def semantic_similarity(
    text_a: str,
    text_b: str,
    embedding_cache: Any = None,
) -> float:
    from app.services.matching.embeddings import (
        semantic_similarity as _semantic_similarity,
    )
    return _semantic_similarity(text_a, text_b, embedding_cache=embedding_cache)


# =========================================================
# UNIT-AWARE VALUE SIMILARITY
# =========================================================

_LENGTH_TO_MM = {
    "MM": 1.0,
    "M": 1000.0,
    "IN": 25.4,
}


def _normalize_unit(unit: Any) -> str:
    unit = str(unit or "").strip().upper()

    aliases = {
        "INCH": "IN",
        "INCHES": "IN",
        '"': "IN",
        "MILLIMETER": "MM",
        "MILLIMETERS": "MM",
        "MILLIMETRE": "MM",
        "MILLIMETRES": "MM",
    }

    return aliases.get(unit, unit)


def _numeric_values_equal(
    left_value: float,
    left_unit: str,
    right_value: float,
    right_unit: str,
) -> bool:
    left_unit = _normalize_unit(left_unit)
    right_unit = _normalize_unit(right_unit)

    if left_unit == right_unit:
        return abs(left_value - right_value) < 1e-6

    # Convert compatible length units to millimetres.
    if (
        left_unit in _LENGTH_TO_MM
        and right_unit in _LENGTH_TO_MM
    ):
        left_mm = left_value * _LENGTH_TO_MM[left_unit]
        right_mm = right_value * _LENGTH_TO_MM[right_unit]

        return abs(left_mm - right_mm) < 1e-6

    return False


def value_similarity(left: Any, right: Any) -> float:
    if left is None or right is None:
        return 0.0

    if left == "" or right == "":
        return 0.0

    if isinstance(left, dict) and isinstance(right, dict):

        # Numeric value + unit.
        if (
            "value" in left
            and "value" in right
            and "unit" in left
            and "unit" in right
        ):
            try:
                return 1.0 if _numeric_values_equal(
                    float(left["value"]),
                    left["unit"],
                    float(right["value"]),
                    right["unit"],
                ) else 0.0
            except (TypeError, ValueError):
                return 0.0

        # Structured dimension dictionaries such as:
        # {"size": "2 IN"}
        if left == right:
            return 1.0

        # Recursively compare matching dictionary fields.
        if set(left.keys()) == set(right.keys()) and left:
            scores = [
                value_similarity(left[key], right[key])
                for key in left
            ]
            return (
                sum(scores) / len(scores)
                if scores
                else 0.0
            )

        return 0.0

    if isinstance(left, (list, tuple, set)):
        if not left:
            return 0.0

    if isinstance(right, (list, tuple, set)):
        if not right:
            return 0.0

    if isinstance(left, (list, tuple)) and isinstance(
        right, (list, tuple)
    ):
        if len(left) != len(right):
            return 0.0

        scores = [
            value_similarity(a, b)
            for a, b in zip(left, right)
        ]

        return (
            sum(scores) / len(scores)
            if scores
            else 0.0
        )

    if left == right:
        return 1.0

    return 0.0
