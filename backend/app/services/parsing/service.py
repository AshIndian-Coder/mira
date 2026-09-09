import re
from typing import Any

GRADE_PATTERNS = [
    r"\bSS[- ]?(304|316|321)\b",
    r"\bSTAINLESS\s+STEEL\s+(304|316|321)\b",
    r"\bAISI[- ]?(304|316|321)\b",
    r"\bIS[- ]?304\b",
]

PRESSURE_PATTERN = re.compile(
    r"(?<!\w)(\d+(?:\.\d+)?)\s*(LB|LBS|POUND|POUNDS|PSI|BAR|#)(?!\w)",
    re.IGNORECASE,
)

SIZE_PATTERN = re.compile(
    r"(?<!\w)(\d+(?:\.\d+)?)\s*(IN|MM)(?!\w)",
    re.IGNORECASE,
)

VOLTAGE_PATTERN = re.compile(
    r"(?<!\w)(\d+(?:\.\d+)?)\s*(V|KV)(?!\w)",
    re.IGNORECASE,
)


def extract_grade(text: str) -> str | None:
    patterns = [
        (r"\bSS[- ]?(304|316|321)\b", lambda m: f"SS{m.group(1)}"),
        (
            r"\bSTAINLESS\s+STEEL\s+(304|316|321)\b",
            lambda m: f"SS{m.group(1)}",
        ),
        (r"\bAISI[- ]?(304|316|321)\b", lambda m: f"SS{m.group(1)}"),
        (r"\bIS[- ]?(304)\b", lambda m: f"SS{m.group(1)}"),
    ]

    for pattern, formatter in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return formatter(match)

    return None


def extract_pressure_rating(text: str) -> dict[str, Any] | None:
    match = PRESSURE_PATTERN.search(text)
    if not match:
        return None

    unit = match.group(2).upper()

    if unit in {"LB", "LBS", "POUND", "POUNDS", "#"}:
        unit = "LB"

    return {
        "value": float(match.group(1)),
        "unit": unit,
    }


def extract_dimensions(text: str) -> dict[str, Any] | None:
    match = SIZE_PATTERN.search(text)
    if not match:
        return None

    return {
        "value": float(match.group(1)),
        "unit": match.group(2).upper(),
    }


def extract_voltage(text: str) -> dict[str, Any] | None:
    match = VOLTAGE_PATTERN.search(text)
    if not match:
        return None

    return {
        "value": float(match.group(1)),
        "unit": match.group(2).upper(),
    }


def parse_specifications(description: str) -> dict[str, Any]:
    text = description.upper()

    return {
        "material_grade": extract_grade(text),
        "pressure_rating": extract_pressure_rating(text),
        "dimensions": extract_dimensions(text),
        "voltage_class": extract_voltage(text),
    }
