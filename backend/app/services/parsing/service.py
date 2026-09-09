import re
from typing import Any


GRADE_PATTERNS = [
    (r"\bSS[- ]?(304|316|321)\b", lambda m: f"SS{m.group(1)}"),
    (
        r"\bSTAINLESS\s+STEEL\s+(304|316|321)\b",
        lambda m: f"SS{m.group(1)}",
    ),
    (r"\bAISI[- ]?(304|316|321)\b", lambda m: f"SS{m.group(1)}"),
    (r"\bIS[- ]?(304)\b", lambda m: f"SS{m.group(1)}"),
]


PRESSURE_PATTERN = re.compile(
    r"(?<!\w)(\d+(?:\.\d+)?)\s*(LB|LBS|POUND|POUNDS|PSI|BAR|#)(?!\w)",
    re.IGNORECASE,
)


VOLTAGE_PATTERN = re.compile(
    r"(?<!\w)(\d+(?:\.\d+)?)\s*(KV|V)(?!\w)",
    re.IGNORECASE,
)


NB_PATTERN = re.compile(
    r"(?<!\w)(\d+(?:\.\d+)?)\s*NB(?!\w)",
    re.IGNORECASE,
)


METRIC_THREAD_PATTERN = re.compile(
    r"\bM(\d+(?:\.\d+)?)\s*[Xx]\s*(\d+(?:\.\d+)?)\b",
    re.IGNORECASE,
)


DIMENSION_PATTERN = re.compile(
    r"(?<![\w.])(\d+(?:\.\d+)?)\s*(MM|IN|INCH|INCHES)(?!\w)",
    re.IGNORECASE,
)


def extract_grade(text: str) -> str | None:
    for pattern, formatter in GRADE_PATTERNS:
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


def extract_voltage(text: str) -> dict[str, Any] | None:
    match = VOLTAGE_PATTERN.search(text)

    if not match:
        return None

    return {
        "value": float(match.group(1)),
        "unit": match.group(2).upper(),
    }


def extract_nominal_bore(text: str) -> dict[str, Any] | None:
    match = NB_PATTERN.search(text)

    if not match:
        return None

    return {
        "value": float(match.group(1)),
        "unit": "NB",
    }


def extract_metric_thread(text: str) -> dict[str, Any] | None:
    match = METRIC_THREAD_PATTERN.search(text)

    if not match:
        return None

    return {
        "nominal_diameter": float(match.group(1)),
        "pitch": float(match.group(2)),
        "unit": "MM",
    }


def extract_dimension_tokens(text: str) -> list[dict[str, Any]]:
    text = text.upper()
    dimensions = []

    def add_dimension(value: str, unit: str = "MM") -> None:
        normalized_unit = unit.upper()

        if normalized_unit in {"INCH", "INCHES"}:
            normalized_unit = "IN"

        dimension = {
            "value": float(value),
            "unit": normalized_unit,
        }

        if dimension not in dimensions:
            dimensions.append(dimension)

    # Dimension sequences with an explicit trailing unit.
    #
    # 780X700X4MM
    # 515X480X4.5 MM
    # 1700X25 MM
    sequence_pattern = re.compile(
        r"(\d+(?:\.\d+)?"
        r"(?:\s*[Xx]\s*\d+(?:\.\d+)?)+)"
        r"\s*(MM|IN|INCH|INCHES)\b",
        re.IGNORECASE,
    )

    for sequence, unit in sequence_pattern.findall(text):
        values = re.findall(r"\d+(?:\.\d+)?", sequence)

        for value in values:
            add_dimension(value, unit)

    # OD-prefixed thickness format.
    #
    # OD60.3X5.54THK
    # OD60.3 X 5.54THK MM
    od_thk_pattern = re.compile(
        r"\bOD\s*(\d+(?:\.\d+)?)"
        r"\s*[Xx]\s*(\d+(?:\.\d+)?)"
        r"\s*(?:THK|THICKNESS)"
        r"(?:\s*(MM|IN|INCH|INCHES))?",
        re.IGNORECASE,
    )

    for first, second, unit in od_thk_pattern.findall(text):
        add_dimension(first, unit or "MM")
        add_dimension(second, unit or "MM")

    # Generic X...THK format.
    #
    # 60.3X5.54THK
    # 1700X25THK
    thk_pattern = re.compile(
        r"(?<![A-Z0-9.])"
        r"(\d+(?:\.\d+)?)"
        r"\s*[Xx]\s*"
        r"(\d+(?:\.\d+)?)"
        r"\s*(?:THK|THICKNESS)\b",
        re.IGNORECASE,
    )

    for first, second in thk_pattern.findall(text):
        add_dimension(first)
        add_dimension(second)

    # Explicit standalone dimensions.
    #
    # 60.3 MM
    # 25MM
    # 2 IN
    explicit_pattern = re.compile(
        r"(?<![\w.])"
        r"(\d+(?:\.\d+)?)\s*"
        r"(MM|IN|INCH|INCHES)"
        r"(?!\w)",
        re.IGNORECASE,
    )

    for value, unit in explicit_pattern.findall(text):
        add_dimension(value, unit)

    return dimensions

def extract_dished_end_dimensions(text: str) -> dict[str, Any] | None:
    text = text.upper()

    # Pattern 1:
    # ID1700X25THK
    match = re.search(
        r"\bID\s*(\d+(?:\.\d+)?)\s*X\s*"
        r"(\d+(?:\.\d+)?)\s*THK\b",
        text,
        re.IGNORECASE,
    )

    if match:
        return {
            "internal_diameter": {
                "value": float(match.group(1)),
                "unit": "MM",
            },
            "thickness": {
                "value": float(match.group(2)),
                "unit": "MM",
            },
        }

    # Pattern 2:
    # ID1500X13
    # Used by the TORI dished-end descriptions.
    match = re.search(
        r"\bID\s*(\d+(?:\.\d+)?)\s*X\s*"
        r"(\d+(?:\.\d+)?)\s*(?:\(\s*MIN\s*\))?",
        text,
        re.IGNORECASE,
    )

    if match:
        return {
            "internal_diameter": {
                "value": float(match.group(1)),
                "unit": "MM",
            },
            "thickness": {
                "value": float(match.group(2)),
                "unit": "MM",
            },
        }

    return None

def extract_dimensions(text: str) -> dict[str, Any] | None:
    dimensions = extract_dimension_tokens(text)

    if not dimensions:
        return None

    return dimensions[0]

def parse_specifications(description: str) -> dict[str, Any]:
    text = description.upper()

    dimension_tokens = extract_dimension_tokens(text)
    dished_end_dimensions = extract_dished_end_dimensions(text)

    return {
        "material_grade": extract_grade(text),
        "pressure_rating": extract_pressure_rating(text),
        "dimensions": (
            dished_end_dimensions
            if dished_end_dimensions
            else (
                dimension_tokens[0]
                if dimension_tokens
                else None
            )
        ),
        "dimension_tokens": dimension_tokens,
        "dished_end_dimensions": dished_end_dimensions,
        "nominal_bore": extract_nominal_bore(text),
        "metric_thread": extract_metric_thread(text),
        "voltage_class": extract_voltage(text),
    }