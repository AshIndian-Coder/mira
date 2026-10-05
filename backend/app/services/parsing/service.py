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

# ANSI/ASME class notation puts the marker *before* the number, so the
# suffix pattern above cannot see it: "CL150", "CLASS 150", "CL 150".
# In the project's own corpus this is the dominant form -- 50 rows use
# CL<n> and 8 use CLASS <n>, against only 10 using the "<n>#" form that
# PRESSURE_PATTERN matches. Missing it leaves pressure_rating empty, and
# since pressure_rating is a critical gate field for VALVE and PIPE, those
# materials are permanently barred from HIGH_CONFIDENCE whatever they score.
PRESSURE_CLASS_PATTERN = re.compile(
    r"(?<!\w)"
    r"(?:CL|CLASS)"
    r"\s*\.?\s*"
    r"(\d+(?:\.\d+)?)"
    r"(?!\w)",
    re.IGNORECASE,
)

VOLTAGE_PATTERN = re.compile(
    r"(?<!\w)"
    r"(\d+(?:\.\d+)?)"
    r"\s*(KVAC|KVA|KVDC|VAC|VDC|KV|V)"
    r"(?!\w)",
    re.IGNORECASE,
)

VOLTAGE_RANGE_PATTERN = re.compile(
    r"(?<!\w)"
    r"(\d+(?:\.\d+)?)"
    r"\s*(KVAC|KVA|KVDC|VAC|VDC|KV|V)?"
    r"\s*[-–]"
    r"\s*"
    r"(\d+(?:\.\d+)?)"
    r"\s*(KVAC|KVA|KVDC|VAC|VDC|KV|V)"
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

NB_PREFIX_PATTERN = re.compile(
    r"\bNB\.?\s*[:\-]?\s*(\d+(?:\.\d+)?)(?:\s*MM)?(?!\w)",
    re.IGNORECASE,
)


# ---------------------------------------------------------
# METRIC THREAD / SCHEDULE
# ---------------------------------------------------------

METRIC_THREAD_PATTERN = re.compile(
    r"\bM(\d+(?:\.\d+)?)\s*[Xx]\s*(\d+(?:\.\d+)?)\b",
    re.IGNORECASE,
)

SCHEDULE_PATTERN = re.compile(
    r"\b(?:SCHEDULE|SCHED|SCH)\.?\s*[:\-]?\s*(STD|XXS|XS|\d{1,3}(?:[A-Z]{1,2})?)\b",
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


def extract_pressure_rating(
    text: str,
) -> dict[str, Any] | None:

    text = text or ""

    match = PRESSURE_PATTERN.search(text)

    if match:
        unit = match.group(2).upper()

        if unit in {
            "LB",
            "LBS",
            "POUND",
            "POUNDS",
            "#",
        }:
            unit = "LB"

        return {
            "value": float(match.group(1)),
            "unit": unit,
        }

    # Fall back to the prefix class form. A class number is a pound-class
    # rating, so it normalises to the same "LB" unit -- which is what makes
    # "CL150", "150#" and "150 LB" compare equal downstream.
    class_match = PRESSURE_CLASS_PATTERN.search(text)

    if class_match:
        return {
            "value": float(class_match.group(1)),
            "unit": "LB",
        }

    return None


def extract_voltage(
    text: str,
) -> dict[str, Any] | None:

    text = text or ""

    # ---------------------------------------------------------
    # Prefer an explicitly stated voltage range.
    #
    # Supports:
    #   80V -140V
    #   80 V - 140 V
    #   80-140V
    #   80V-140V
    # ---------------------------------------------------------

    range_match = VOLTAGE_RANGE_PATTERN.search(text)

    if range_match:
        first_unit = range_match.group(2)
        second_unit = range_match.group(4)

        unit = second_unit or first_unit

        if unit:
            return {
                "min": float(range_match.group(1)),
                "max": float(range_match.group(3)),
                "unit": unit.upper(),
            }

    # ---------------------------------------------------------
    # Single voltage
    #
    # Examples:
    #   415VAC
    #   415 V
    #   11KV
    # ---------------------------------------------------------

    match = VOLTAGE_PATTERN.search(text)

    if not match:
        return None

    return {
        "value": float(match.group(1)),
        "unit": match.group(2).upper(),
    }

def extract_frequency(
    text: str,
) -> dict[str, Any] | None:
    """
    Extract electrical frequency.

    Examples:
        50 Hz
        60HZ
        FREQUENCY: 50 Hz
    """

    text = text or ""

    match = re.search(
        r"(?<![\w.])"
        r"(\d+(?:\.\d+)?)"
        r"\s*HZ\b",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    return {
        "value": float(match.group(1)),
        "unit": "HZ",
    }

def extract_power(
    text: str,
) -> dict[str, Any] | None:
    """
    Extract electrical power.

    Examples:
        45 KW
        45KW
        18W
        18W-20W
        18 W - 20 W

    Returns a single value or a range.
    """

    text = text or ""

    # Prefer an explicitly stated power range.
    range_match = re.search(
        r"(?<![\w.])"
        r"(\d+(?:\.\d+)?)"
        r"\s*(KW|W)"
        r"\s*[-–]"
        r"\s*"
        r"(\d+(?:\.\d+)?)"
        r"\s*(KW|W)"
        r"(?!\w)",
        text,
        re.IGNORECASE,
    )

    if range_match:
        first_unit = range_match.group(2).upper()
        second_unit = range_match.group(4).upper()

        # A range should normally use the same unit on both sides.
        # If the source uses different units, preserve the explicit
        # units rather than silently converting them.
        if first_unit == second_unit:
            return {
                "min": float(range_match.group(1)),
                "max": float(range_match.group(3)),
                "unit": first_unit,
            }

        return {
            "min": float(range_match.group(1)),
            "min_unit": first_unit,
            "max": float(range_match.group(3)),
            "max_unit": second_unit,
        }

    # Single power value.
    match = re.search(
        r"(?<![\w.])"
        r"(\d+(?:\.\d+)?)"
        r"\s*(KW|W)"
        r"(?!\w)",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    return {
        "value": float(match.group(1)),
        "unit": match.group(2).upper(),
    }

def extract_cct(
    text: str,
) -> dict[str, Any] | None:
    """
    Extract correlated colour temperature (CCT).

    Examples:
        CCT:5700-6500 DEGREE K
        CCT: 5700 K
        CCT 5700-6500K
    """

    text = text or ""

    # CCT range.
    range_match = re.search(
        r"\bCCT\b"
        r"\s*[:=\-]?\s*"
        r"(\d+(?:\.\d+)?)"
        r"\s*[-–]"
        r"\s*"
        r"(\d+(?:\.\d+)?)"
        r"\s*(?:DEG(?:REE)?\s*)?K\b",
        text,
        re.IGNORECASE,
    )

    if range_match:
        return {
            "min": float(range_match.group(1)),
            "max": float(range_match.group(2)),
            "unit": "K",
        }

    # CCT single value.
    match = re.search(
        r"\bCCT\b"
        r"\s*[:=\-]?\s*"
        r"(\d+(?:\.\d+)?)"
        r"\s*(?:DEG(?:REE)?\s*)?K\b",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    return {
        "value": float(match.group(1)),
        "unit": "K",
    }

def extract_cri(
    text: str,
) -> dict[str, Any] | None:
    """
    Extract colour rendering index (CRI).

    Examples:
        CRI-70
        CRI:70
        CRI 70
        CRI-90
    """

    text = text or ""

    match = re.search(
        r"\bCRI\b"
        r"\s*[:=\-]?\s*"
        r"(\d+(?:\.\d+)?)\b",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    return {
        "value": float(match.group(1)),
    }

def extract_ip_rating(
    text: str,
) -> dict[str, Any] | None:
    """
    Extract ingress protection (IP) rating.

    Examples:
        IP 66
        IP66
        IP-65
        IP:67
    """

    text = text or ""

    match = re.search(
        r"\bIP"
        r"\s*[:=\-]?\s*"
        r"(\d{2})\b",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    return {
        "value": int(match.group(1)),
    }

def extract_luminous_efficiency(
    text: str,
) -> dict[str, Any] | None:
    """
    Extract luminous efficiency.

    Examples:
        >=130 Lm/Watt
        >120 LM/W
        130 lm/w
        130 LUMENS/WATT
    """

    text = text or ""

    match = re.search(
        r"(?<![\w.])"
        r"(>=|<=|>|<|=)?"
        r"\s*"
        r"(\d+(?:\.\d+)?)"
        r"\s*"
        r"(?:LM|LUMEN|LUMENS)"
        r"\s*/\s*"
        r"(?:W|WATT|WATTS)\b",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    operator = match.group(1)

    result = {
        "value": float(match.group(2)),
        "unit": "LM/W",
    }

    if operator:
        result["operator"] = operator

    return result


def extract_nominal_bore(
    text: str,
) -> dict[str, Any] | None:

    text = text or ""

    # Prefer prefix form: NB 80, NB 200, NB: 25, NB-600, NB80
    prefix_match = NB_PREFIX_PATTERN.search(text)
    if prefix_match:
        return {
            "value": float(prefix_match.group(1)),
            "unit": "NB",
        }

    # Suffix form: 50NB, 50 NB, 25MMNB, 200NBX6.35MM
    match = NB_PATTERN.search(text)

    if not match:
        return None

    return {
        "value": float(match.group(1)),
        "unit": "NB",
    }


def extract_schedule(
    text: str,
) -> str | None:
    """
    Extract pipe schedule specification.

    Examples:
        SCH40, SCH 40, SCHEDULE 40 -> SCH40
        SCH80, SCH 80, SCHEDULE 80 -> SCH80
        SCHXS, SCH XS, SCHEDULE XS -> SCHXS
    """

    match = SCHEDULE_PATTERN.search(text or "")

    if not match:
        return None

    return f"SCH{match.group(1).upper()}"


def extract_metric_thread(
    text: str,
) -> dict[str, Any] | None:

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


# ---------------------------------------------------------
# FASTENER DIMENSIONS
# ---------------------------------------------------------

FASTENER_CONTEXT_PATTERN = re.compile(
    r"\b(?:HEX\s+HEAD\s+BOLT|HEXAGONAL\s+HEAD\s+BOLT|HEX\s+HD\s+BOLT|HEX\s+BOLT|HEX\s+HD|HEX\s+HEAD|HEXAGONAL|"
    r"BOLT|SCREW|STUD|FASTENER|CAP\s*SCREW|CAPSCREW|SOCKET\s+HEAD|CSK|COUNTERSUNK|GRUB|ANCHOR|"
    r"THREADED\s+ROD|TIE\s+ROD|WASHER|NUT|IS\s*[:\-]?\s*136[34]|IS\s*[:\-]?\s*2269)\b",
    re.IGNORECASE,
)

M_PITCH_LENGTH_PATTERN = re.compile(
    r"\bM\s*(\d+(?:\.\d+)?)"
    r"\s*[*Xx×\u00d7\u2715]\s*"
    r"(\d+(?:\.\d+)?)"
    r"\s*[*Xx×\u00d7\u2715]\s*"
    r"(\d+(?:\.\d+)?)"
    r"(?:\s*MM)?\b",
    re.IGNORECASE,
)

M_FASTENER_PATTERN = re.compile(
    r"(?:\bSIZE\s*[:\-]?\s*)?"
    r"\bM\s*(\d+(?:\.\d+)?)"
    r"\s*[*Xx×\u00d7\u2715]\s*"
    r"(\d+(?:\.\d+)?)"
    r"(?:\s*MM)?\b",
    re.IGNORECASE,
)

PLAIN_FASTENER_PATTERN = re.compile(
    r"(?<![\w.])"
    r"(\d+(?:\.\d+)?)"
    r"\s*[*Xx×\u00d7\u2715]\s*"
    r"(\d+(?:\.\d+)?)"
    r"\s*MM\b",
    re.IGNORECASE,
)


def extract_fastener_dimensions(text: str) -> dict[str, Any] | None:
    text = text or ""

    # 1. 3-part chain: M<dia> x <pitch> x <length> (e.g. M140X4X810)
    m3 = M_PITCH_LENGTH_PATTERN.search(text)
    if m3:
        dia = float(m3.group(1))
        pitch = float(m3.group(2))
        length = float(m3.group(3))
        return {
            "diameter": {"value": dia, "unit": "MM"},
            "pitch": {"value": pitch, "unit": "MM"},
            "length": {"value": length, "unit": "MM"},
        }

    # 2. Metric bolt callout: M<dia> x <length> (e.g. M8 X 25 MM, M8x25, M8×30, SIZE M8×30)
    m2 = M_FASTENER_PATTERN.search(text)
    if m2:
        dia = float(m2.group(1))
        second_val = float(m2.group(2))
        has_explicit_mm = bool(
            re.search(
                r"[*Xx×\u00d7\u2715]\s*" + re.escape(m2.group(2)) + r"\s*MM\b",
                text,
                re.IGNORECASE,
            )
        )
        has_context = bool(FASTENER_CONTEXT_PATTERN.search(text)) or bool(
            re.search(r"\bSIZE\b", text, re.IGNORECASE)
        )

        is_length = False
        if has_explicit_mm:
            is_length = True
        elif second_val > dia * 0.35:
            is_length = True
        elif has_context and second_val >= 5.0 and second_val > dia * 0.30:
            is_length = True

        if is_length:
            return {
                "diameter": {"value": dia, "unit": "MM"},
                "length": {"value": second_val, "unit": "MM"},
            }

    # 3. Plain <dia> x <length> MM in explicit fastener context (e.g. "MS HEX HD BOLT WITH NUT IS:1363 6X25MM")
    if FASTENER_CONTEXT_PATTERN.search(text):
        m_plain = PLAIN_FASTENER_PATTERN.search(text)
        if m_plain:
            dia = float(m_plain.group(1))
            length = float(m_plain.group(2))
            if dia <= 64.0 and length >= 4.0:
                return {
                    "diameter": {"value": dia, "unit": "MM"},
                    "length": {"value": length, "unit": "MM"},
                }

    return None


# ---------------------------------------------------------
# DIMENSIONS
# ---------------------------------------------------------

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
        r"(?<![\w.])(\d+(?:\.\d+)?)\s*[Xx]\s*"
        r"(\d+(?:\.\d+)?)\s*THK\b",
        re.IGNORECASE,
    ),
]


def extract_dimension_tokens(
    text: str,
) -> list[dict[str, Any]]:

    text = text or ""
    results: list[dict[str, Any]] = []

    fastener_dims = extract_fastener_dimensions(text)
    if fastener_dims:
        results.append(fastener_dims)

    for pattern in DIMENSION_TOKEN_PATTERNS:

        for match in pattern.finditer(text):

            if match.lastindex == 1:

                raw = match.group(1).replace(" ", "")
                values = re.split(r"[Xx]", raw)

                results.append({
                    "values": [
                        float(v)
                        for v in values
                    ],
                    "unit": "MM",
                })

            elif match.lastindex == 2:

                results.append({
                    "value": float(match.group(1)),
                    "unit": "MM",
                    "type": "OD",
                })

                results.append({
                    "value": float(match.group(2)),
                    "unit": "MM",
                    "type": "THICKNESS",
                })

    for match in DIMENSION_PATTERN.finditer(text):

        value = float(match.group(1))
        unit = match.group(2).upper()

        if unit in {
            "INCH",
            "INCHES",
        }:
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
    fastener_dims = extract_fastener_dimensions(text)
    if fastener_dims:
        return fastener_dims

    tokens = extract_dimension_tokens(text)

    if tokens:
        return tokens[0]

    return extract_dished_end_dimensions(text)


def extract_material_grade(
    text: str,
) -> str | None:

    return extract_grade(text)


def extract_voltage_class(
    text: str,
) -> dict[str, Any] | None:

    return extract_voltage(text)


# ---------------------------------------------------------
# MAIN SPECIFICATION PARSER
# ---------------------------------------------------------

def parse_specifications(
    text: str,
) -> dict:

    """
    Extract structured technical specifications from a material
    description.

    Existing parser fields are preserved. Additional fields are
    deliberately generic so they can be used by downstream matching
    without pretending that ambiguous values have a more specific
    meaning than the source text.
    """

    text = text or ""
    upper = text.upper()

    dimension_tokens = extract_dimension_tokens(text)
    dished_end_dimensions = extract_dished_end_dimensions(text)

    result = {
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
        "schedule": extract_schedule(text),
        "metric_thread": extract_metric_thread(text),
        "voltage_class": extract_voltage_class(text),

        # Generic electrical / lighting specifications.
        "frequency": extract_frequency(text),
        "power": extract_power(text),
        "cct": extract_cct(text),
        "cri": extract_cri(text),
        "beam_angle": None,
        "ip_rating": extract_ip_rating(text),
        "luminous_efficiency": extract_luminous_efficiency(text),
    }

    # ---------------------------------------------------------------
    # Standards: IS:1239, IS 1747, IS:10658, ASTM-A-105, etc.
    # ---------------------------------------------------------------

    standards = []

    for match in re.finditer(
        r"\bIS\s*[:\-]?\s*(\d{3,6})\b",
        upper,
    ):
        standards.append(
            f"IS {match.group(1)}"
        )

    for match in re.finditer(
        r"\bASTM\s*[-:]?\s*A\s*[-:]?\s*(\d{2,5})\b",
        upper,
    ):
        standards.append(
            f"ASTM A{match.group(1)}"
        )

    result["standards"] = list(
        dict.fromkeys(standards)
    )

    # ---------------------------------------------------------------
    # Purity: PURITY 99.999%
    # ---------------------------------------------------------------

    match = re.search(
        r"\bPURITY\s*[:\-]?\s*"
        r"(\d+(?:\.\d+)?)\s*%",
        upper,
    )

    result["purity"] = (
        {
            "value": float(match.group(1)),
            "unit": "%",
        }
        if match
        else None
    )

    # ---------------------------------------------------------------
    # Temperature range: 20-150 DEG C
    # ---------------------------------------------------------------

    match = re.search(
        r"(?<![\w.])"
        r"(\d+(?:\.\d+)?)\s*[-–]\s*"
        r"(\d+(?:\.\d+)?)\s*"
        r"(?:DEG(?:REE)?\s*)?C\b",
        upper,
    )

    result["temperature_range"] = (
        {
            "min": float(match.group(1)),
            "max": float(match.group(2)),
            "unit": "C",
        }
        if match
        else None
    )

    # ---------------------------------------------------------------
    # Pressure range: RANGE 0-10 KG/CM2
    # ---------------------------------------------------------------

    match = re.search(
        r"\b(?:RANGE\s*)?"
        r"(\d+(?:\.\d+)?)\s*[-–]\s*"
        r"(\d+(?:\.\d+)?)\s*"
        r"(KG\s*/\s*CM2|KG/CM²|PSI|BAR)\b",
        upper,
    )

    result["pressure_range"] = (
        {
            "min": float(match.group(1)),
            "max": float(match.group(2)),
            "unit": re.sub(
                r"\s+",
                "",
                match.group(3),
            ),
        }
        if match
        else None
    )

    # ---------------------------------------------------------------
    # Property class: P.C.-4.6 / PC 4.6
    # ---------------------------------------------------------------

    match = re.search(
        r"\bP\s*\.?\s*C\s*\.?\s*[-:]?\s*"
        r"(\d+(?:\.\d+)?)\b",
        upper,
    )

    result["property_class"] = (
        float(match.group(1))
        if match
        else None
    )

    # ---------------------------------------------------------------
    # Poles: 4P
    # ---------------------------------------------------------------

    match = re.search(
        r"(?<![\w.])"
        r"(\d+)P\b",
        upper,
    )

    result["poles"] = (
        int(match.group(1))
        if match
        else None
    )

    # ---------------------------------------------------------------
    # Voltage
    #
    # IMPORTANT:
    # Use the canonical extractor above rather than maintaining
    # another independent voltage regex here.
    #
    # This supports:
    #   415VAC
    #   415 V
    #   11KV
    #   80-140V
    #   80V-140V
    #   80V -140V
    #   80 V - 140 V
    # ---------------------------------------------------------------

    result["voltage_class"] = extract_voltage(upper)

    # ---------------------------------------------------------------
    # Motor-specific attributes
    # ---------------------------------------------------------------

    result["mounting"] = None

    if re.search(
        r"\b(?:MOTR|MOTOR)\b",
        upper,
    ):

        mounting = re.search(
            r"(?<![A-Z0-9])"
            r"B[0-9]{1,2}"
            r"(?![A-Z0-9])",
            upper,
        )

        if mounting:
            result["mounting"] = mounting.group(0)

    result["enclosure"] = (
        "TEFC"
        if re.search(r"\bTEFC\b", upper)
        else None
    )

    # Frame size such as 225M.
    result["frame_size"] = None

    if re.search(
        r"\b(?:MOTR|MOTOR)\b",
        upper,
    ):

        frame = re.search(
            r"(?<![A-Z0-9])"
            r"([0-9]{2,4}[A-Z])\b",
            upper,
        )

        if frame:
            result["frame_size"] = frame.group(1)

    # ---------------------------------------------------------------
    # Compact metric dimension chains.
    #
    # Examples:
    #   M140X4X810
    #   30MMX18MMX6M
    # ---------------------------------------------------------------

    compact = []

    # Mixed-unit chain such as 30MMX18MMX6M
    for match in re.finditer(
        r"(\d+(?:\.\d+)?)\s*MM\s*[Xx]\s*"
        r"(\d+(?:\.\d+)?)\s*MM\s*[Xx]\s*"
        r"(\d+(?:\.\d+)?)\s*M\b",
        upper,
    ):

        compact.append({
            "values": [
                float(match.group(1)),
                float(match.group(2)),
                float(match.group(3)),
            ],
            "units": [
                "MM",
                "MM",
                "M",
            ],
        })

    # Compact metric form such as M140X4X810
    for match in re.finditer(
        r"\bM(\d+(?:\.\d+)?)\s*[Xx]\s*"
        r"(\d+(?:\.\d+)?)\s*[Xx]\s*"
        r"(\d+(?:\.\d+)?)\b",
        upper,
    ):

        compact.append({
            "values": [
                float(match.group(1)),
                float(match.group(2)),
                float(match.group(3)),
            ],
            "unit": "MM",
            "prefix": "M",
        })

    result["compact_dimensions"] = compact

    # Simple metric size such as M10.
    # Do not treat M140 from M140X4X810 as a standalone size.
    metric_size = re.search(
        r"(?<![A-Z0-9])"
        r"M\s*(\d+(?:\.\d+)?)(?!\s*[Xx])\b",
        upper,
    )

    result["metric_size"] = (
        {
            "value": float(metric_size.group(1)),
            "unit": "MM",
        }
        if metric_size
        else None
    )

    # ---------------------------------------------------------------
    # Fractional inch nominal size: 3/4"
    # ---------------------------------------------------------------

    match = re.search(
        r"(?<![\w.])"
        r"(\d+)\s*/\s*(\d+)\s*[\"”]",
        upper,
    )

    result["nominal_size"] = (
        {
            "value": float(match.group(1))
            / float(match.group(2)),
            "unit": "IN",
        }
        if match
        else None
    )

    # ---------------------------------------------------------------
    # Angle such as 45 DEG. ELBOW
    # ---------------------------------------------------------------

    # ---------------------------------------------------------------
    # Angle
    #
    # Require explicit angle context so values such as:
    #
    #   CCT:5700-6500 DEGREE K
    #
    # are NOT interpreted as an angle.
    #
    # Supported examples:
    #   ANGLE 45 DEG
    #   BEAM ANGLE 120 DEG
    #   BEAM ANGLE-120-degree
    #   45 DEG ELBOW
    # ---------------------------------------------------------------

    angle = re.search(
        r"\b(?:BEAM\s+)?ANGLE"
        r"\s*[-:=]?\s*"
        r"(\d+(?:\.\d+)?)"
        r"\s*(?:DEG(?:REE)?\.?)?\b",
        upper,
    )

    if not angle:
        angle = re.search(
            r"\bANGLE"
            r"\s*[-:=]?\s*"
            r"(\d+(?:\.\d+)?)"
            r"\s*DEG(?:REE)?\.?\b",
            upper,
        )

    result["beam_angle"] = (
        {
            "value": float(angle.group(1)),
            "unit": "DEG",
        }
        if angle
        else None
    )

    # ---------------------------------------------------------------
    # Bearing designation
    #
    # Bearing descriptions are often written in catalog shorthand:
    #   BEARING 6208 Z
    #   BEARING;6204 ZZ C3
    #   BALL BEARING-SR:6306:ZC3
    #   CYLINDRICAL ROLLER BRG.NU317 ECJ
    #   TAPER ROLLER BRG#:30312:JR
    #   SELF ALIG SPHR RLR BRG:DR:22328CC/C3/W34
    #   SPECIAL BRG: BC1B316548(SKF)/541126(FAG)
    #
    # Preserve the first catalog designation as a technical identifier.
    # This is intentionally separate from dimensions.
    # ---------------------------------------------------------------

    bearing = None

    bearing_context = re.search(
        r"\b(?:BEARING|BRG(?:\s+NO)?\.?)\b",
        upper,
    )

    if bearing_context:

        tail = upper[
            bearing_context.end():
        ]

        # Remove common separators / short catalog qualifiers.
        tail = re.sub(
            r"^[\s;:#.\-]*"
            r"(?:NO\.?|SR|DR)"
            r"[\s;:#.\-]*",
            "",
            tail,
        )

        # First preference: conventional numeric bearing designation.
        designation_match = re.search(
            r"\b([A-Z]{0,3}[- ]?\d{3,6}"
            r"(?:[-/ ]?[A-Z0-9]{1,8}){0,5})\b",
            tail,
        )

        # Some special bearings use an alphanumeric catalog code.
        if not designation_match:

            designation_match = re.search(
                r"\b([A-Z]{1,6}\d[A-Z0-9]{3,})\b",
                tail,
            )

        if designation_match:

            designation = re.sub(
                r"\s+",
                " ",
                designation_match.group(1).strip(),
            )

            family = None

            if re.search(
                r"\bTAPER(?:ED)?\s+ROLLER\b",
                upper,
            ):
                family = "TAPER_ROLLER"

            elif re.search(
                r"\bSPH(?:ERICAL)?\s+ROLLER\b",
                upper,
            ):
                family = "SPHERICAL_ROLLER"

            elif re.search(
                r"\bCYL(?:INDRICAL)?\.?\s+ROLLER\b",
                upper,
            ):
                family = "CYLINDRICAL_ROLLER"

            elif re.search(
                r"\bANGULAR\s+CONTACT\b",
                upper,
            ):
                family = "ANGULAR_CONTACT"

            elif re.search(
                r"\bTHRUST\b",
                upper,
            ):
                family = "THRUST"

            elif re.search(
                r"\bSELF\s+AL(?:IGN|N)\b",
                upper,
            ):
                family = "SELF_ALIGNING"

            elif re.search(
                r"\bBALL\b",
                upper,
            ):
                family = "BALL"

            bearing = {
                "designation": designation,
                "family": family,
            }

    result["bearing"] = bearing

    return result