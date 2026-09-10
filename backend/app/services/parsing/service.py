import re
from typing import Any


# ---------------------------------------------------------
# MATERIAL GRADES
# ---------------------------------------------------------

GRADE_PATTERNS = [
    # Stainless steel
    (r"\bSS[- ]?(304|316|321)\b", lambda m: f"SS{m.group(1)}"),
    (
        r"\bSTAINLESS\s+STEEL\s+(304|316|321)\b",
        lambda m: f"SS{m.group(1)}",
    ),
    (r"\bAISI[- ]?(304|316|321)\b", lambda m: f"SS{m.group(1)}"),
    (r"\bIS[- ]?(304)\b", lambda m: f"SS{m.group(1)}"),

    # Carbon/alloy steel grades
    (
        r"\b(SA\d{3,4})\s*(?:GR(?:ADE)?\.?\s*)?([A-Z]?\d+(?:\.\d+)?)\b",
        lambda m: f"{m.group(1)} GR{m.group(2)}",
    ),

    # Common fastener/property classes
    (
        r"\b(?:GR|GRADE|CLASS)\s*\.?\s*(\d+(?:\.\d+)?)\b",
        lambda m: f"GR{m.group(1)}",
    ),
    (
        r"\bPC\s*(\d+(?:\.\d+)?)\b",
        lambda m: f"PC{m.group(1)}",
    ),

    # Common material designation
    (
        r"\b(CA6NM)\b",
        lambda m: m.group(1),
    ),
]


# ---------------------------------------------------------
# PRESSURE / VOLTAGE / NB
# ---------------------------------------------------------

PRESSURE_PATTERN = re.compile(
    r"(?<!\w)"
    r"(\d+(?:\.\d+)?)"
    r"\s*(LB|LBS|POUND|POUNDS|PSI|BAR|#)"
    r"(?!\w)",
    re.IGNORECASE,
)

VOLTAGE_PATTERN = re.compile(
    r"(?<!\w)"
    r"(\d+(?:\.\d+)?)"
    r"\s*(KV|V)"
    r"(?!\w)",
    re.IGNORECASE,
)


# Important:
# Allows:
#   25NB
#   25 NB
#   25MMNB
#   25 MM NB
#   200NBX6.35MM
#
# Does NOT require NB to be separated by whitespace.
NB_PATTERN = re.compile(
    r"(?<![\w.])"
    r"(\d+(?:\.\d+)?)"
    r"(?:\s*MM)?"
    r"\s*NB"
    r"(?!\w)",
    re.IGNORECASE,
)


# ---------------------------------------------------------
# METRIC THREAD
# ---------------------------------------------------------

METRIC_THREAD_PATTERN = re.compile(
    r"\bM(\d+(?:\.\d+)?)\s*[Xx]\s*(\d+(?:\.\d+)?)\b",
    re.IGNORECASE,
)



# ---------------------------------------------------------
# PARSER HELPERS
# ---------------------------------------------------------

def extract_grade(text: str) -> str | None:
    text = text.upper()

    for pattern, formatter in GRADE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return formatter(match)

    return None


def extract_pressure_rating(text: str) -> dict[str, Any] | None:
    match = PRESSURE_PATTERN.search(text or "")

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
    match = VOLTAGE_PATTERN.search(text or "")

    if not match:
        return None

    return {
        "value": float(match.group(1)),
        "unit": match.group(2).upper(),
    }


def extract_nominal_bore(text: str) -> dict[str, Any] | None:
    match = NB_PATTERN.search(text or "")

    if not match:
        return None

    return {
        "value": float(match.group(1)),
        "unit": "NB",
    }


def extract_metric_thread(text: str) -> dict[str, Any] | None:
    match = METRIC_THREAD_PATTERN.search(text or "")

    if not match:
        return None

    diameter = float(match.group(1))
    pitch = float(match.group(2))

    # Reject diameter × length expressions such as M8 X 40MM.
    if pitch > diameter * 0.30:
        return None

    return {
        "nominal_diameter": diameter,
        "pitch": pitch,
        "unit": "MM",
    }


DIMENSION_PATTERN = re.compile(
    r"(?<![\w.])"
    r"(\d+(?:\.\d+)?)"
    r"\s*(MM|IN|INCH|INCHES)"
    r"(?!\w)",
    re.IGNORECASE,
)


DIMENSION_TOKEN_PATTERNS = [
    re.compile(
        r"(?<![\w.])"
        r"(\d+(?:\.\d+)?(?:\s*[Xx]\s*\d+(?:\.\d+)?)+)"
        r"\s*MM\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bOD\s*(\d+(?:\.\d+)?)\s*[Xx]\s*"
        r"(\d+(?:\.\d+)?)\s*THK\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(\d+(?:\.\d+)?)\s*[Xx]\s*"
        r"(\d+(?:\.\d+)?)\s*THK\b",
        re.IGNORECASE,
    ),
]


def extract_dimension_tokens(text: str) -> list[dict[str, Any]]:
    text = text or ""
    results: list[dict[str, Any]] = []

    for pattern in DIMENSION_TOKEN_PATTERNS:
        for match in pattern.finditer(text):
            if match.lastindex == 1:
                raw = match.group(1).replace(" ", "")
                values = raw.split("X")

                results.append({
                    "values": [float(v) for v in values],
                    "unit": "MM",
                })

            elif match.lastindex == 2:
                results.append({
                    "values": [
                        float(match.group(1)),
                        float(match.group(2)),
                    ],
                    "unit": "MM",
                    "type": "OD_THICKNESS",
                })

    for match in DIMENSION_PATTERN.finditer(text):
        value = float(match.group(1))
        unit = match.group(2).upper()

        if unit in {"INCH", "INCHES"}:
            unit = "IN"

        token = {
            "value": value,
            "unit": unit,
        }

        if not any(
            existing.get("value") == value
            and existing.get("unit") == unit
            for existing in results
            if isinstance(existing, dict)
        ):
            results.append(token)

    return results


def extract_dished_end_dimensions(
    text: str,
) -> dict[str, Any] | None:
    text = text or ""

    pattern = re.compile(
        r"\bID\s*(\d+(?:\.\d+)?)"
        r"\s*[Xx]\s*"
        r"(\d+(?:\.\d+)?)"
        r"\s*(?:THK)?"
        r"\s*(?:MM)?\b",
        re.IGNORECASE,
    )

    match = pattern.search(text)

    if not match:
        return None

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


def extract_dimensions(text: str):
    tokens = extract_dimension_tokens(text)

    if tokens:
        return tokens[0]

    return extract_dished_end_dimensions(text)


def extract_material_grade(text: str) -> str | None:
    return extract_grade(text)


def extract_voltage_class(text: str) -> dict[str, Any] | None:
    return extract_voltage(text)


def parse_specifications(text: str) -> dict:
    text = text or ""

    dimension_tokens = extract_dimension_tokens(text)
    dished_end_dimensions = extract_dished_end_dimensions(text)

    return {
        "material_grade": extract_material_grade(text),
        "pressure_rating": extract_pressure_rating(text),
        "dimensions": (
            dimension_tokens[0]
            if dimension_tokens
            else dished_end_dimensions
        ),
        "dimension_tokens": dimension_tokens,
        "dished_end_dimensions": dished_end_dimensions,
        "nominal_bore": extract_nominal_bore(text),
        "metric_thread": extract_metric_thread(text),
        "voltage_class": extract_voltage_class(text),
    }

# =========================================================
# PUBLIC PARSER API
# =========================================================
