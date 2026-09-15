"""Attribute extraction (NLP stage 2).

Parses a cleaned material description into a structured attribute dict that
feeds:
  * attribute_matcher (specification / grade / other similarity)
  * critical gates (dimensions, pressure_rating, voltage_class, material_grade)
  * taxonomy_mapper (category classification)

Rule-based by design: deterministic, dependency-free, and reproducible.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# Canonical attribute keys produced by the extractor.
ATTRIBUTE_KEYS = [
    "type",
    "subtype",
    "category",
    "size",
    "dimensions",
    "material_grade",
    "pressure_rating",
    "voltage_class",
    "seal",
    "standard",
    "thread",
    "bore",
    "length",
]

# ---------------------------------------------------------------------- #
# Material type taxonomy (checked in priority order)
# ---------------------------------------------------------------------- #
_TYPE_PATTERNS: List[tuple] = [
    ("Bearing", re.compile(r"\b(BEARING|BRG)\b")),
    ("Valve", re.compile(r"\b(VALVE|VLV)\b")),
    ("Pipe Fitting", re.compile(r"\b(FLANGE|ELBOW|T EE|TEE|REDUCER|COUPLING|PLUG|CAP|SLEEVE|UNION)\b")),
    ("Pipe", re.compile(r"\b(PIPE|PIPES|PIPELINE|PPL)\b")),
    ("Fastener", re.compile(r"\b(BOLT|BOLTS|SCREW|SCREWS|NUT|NUTS|WASHER|WASHERS|STUD|STUDS|RIVET|RIVETS|ANCHOR|PIN|PINS|RIGGING)\b")),
    ("Gasket", re.compile(r"\b(GASKET|GSKET|GSK)\b")),
    ("Seal", re.compile(r"\b(SEAL|SEALS|O RING|O-RING|MECHANICAL SEAL)\b")),
    ("Spring", re.compile(r"\bSPRING(S)?\b")),
    ("Filter", re.compile(r"\bFILTER(S)?\b")),
    ("Pump", re.compile(r"\bPUMP(S)?\b")),
    ("Motor", re.compile(r"\bMOTOR(S)?|MTR\b")),
    ("Electrical Connector", re.compile(r"\b(CONNECTOR|CONNECTORS|TERMINAL|TERMINALS|PLUG SOCKET)\b")),
    ("Switch", re.compile(r"\bSWITCH|SWCH\b")),
    ("Contact", re.compile(r"\b(CONTACTOR|CONTACTORS|CONTACT)\b")),
    ("Relay", re.compile(r"\bRELAY|RLY\b")),
    ("Transformer", re.compile(r"\bTRANSFORMER|XFRMR\b")),
    ("Cable", re.compile(r"\bCABLE|CABLES|CBL\b")),
    ("Wire", re.compile(r"\bWIRE|WIRES|WIR\b")),
    ("Electrode", re.compile(r"\bELECTRODE|ELECTRODES\b")),
    ("Rod", re.compile(r"\bROD(S)?\b")),
    ("Sheet", re.compile(r"\bSHEET(S)?|PLATE|PLATES\b")),
    ("Coil", re.compile(r"\bCOIL(S)?\b")),
    ("Cylinder", re.compile(r"\bCYLINDER|HYDRAULIC|PNEUMATIC\b")),
    ("Bush", re.compile(r"\bBUSH|BUSHINGS?\b")),
    ("Shaft", re.compile(r"\bSHAFT|SHFT\b")),
]

_SUBTYPE_PATTERNS: List[tuple] = [
    # Bearing subtypes
    ("Ball", re.compile(r"\bBALL\b")),
    ("Tapered Roller", re.compile(r"\bTAPERED?\b")),
    ("Cylindrical Roller", re.compile(r"\bCYLINDRICAL\b")),
    ("Roller", re.compile(r"\bROLLER(S)?\b")),
    ("Needle", re.compile(r"\bNEEDLE\b")),
    ("Deep Groove", re.compile(r"\bDEEP GROOVE\b")),
    ("Thrust", re.compile(r"\bTHRUST\b")),
    ("Sleeve", re.compile(r"\bSLEEVE\b")),
    # Valve subtypes
    ("Gate", re.compile(r"\bGATE\b")),
    ("Globe", re.compile(r"\bGLOBE\b")),
    ("Check", re.compile(r"\bCHECK\b")),
    ("Butterfly", re.compile(r"\bBUTTERFLY\b")),
    ("Needle Valve", re.compile(r"\bNEEDLE\b")),
    ("Diaphragm", re.compile(r"\bDIAPHRAGM\b")),
    ("Plug", re.compile(r"\bPLUG\b")),
    ("Angular", re.compile(r"\bANGULAR\b")),
    # Fastener subtypes
    ("Hex", re.compile(r"\bHEX|HEXAGON|HEXAGONAL\b")),
    ("Union", re.compile(r"\bUNION\b")),
    ("Lock Nut", re.compile(r"\bLOCK\b")),
    ("Dome", re.compile(r"\bDOME\b")),
    ("Flange Bolt", re.compile(r"\bFLANGE\b")),
    ("Spring Washer", re.compile(r"\bSPRING\b")),
    ("Anchor", re.compile(r"\bANCHOR\b")),
    # Pipe subtypes
    ("Galvanized", re.compile(r"\bGALVANIZED|GI\b")),
    ("Weld", re.compile(r"\bWELD|WELDED\b")),
    ("Seamless", re.compile(r"\bSEAMLESS\b")),
]

# ---------------------------------------------------------------------- #
# Material grade patterns
# ---------------------------------------------------------------------- #
_GRADE_PATTERNS: List[tuple] = [
    ("Carbon Steel", re.compile(r"\b(CARBON STEEL|CS|HYPEREUTECTOID|HYPOEUTECTOID)\b")),
    ("Stainless Steel", re.compile(r"\bSTAINLESS STEEL|SS ?\d{3,4}\b")),
    ("Mild Steel", re.compile(r"\bMILD STEEL|MS\b")),
    ("High Strength Low Alloy", re.compile(r"\bHSLA\b")),
    ("Cast Iron", re.compile(r"\bCAST IRON|CI\b")),
    ("Galvanized Iron", re.compile(r"\bGALVANIZED IRON|GI\b")),
    ("Brass", re.compile(r"\bBRASS\b")),
    ("Bronze", re.compile(r"\bBRONZE|BRZ\b")),
    ("Copper", re.compile(r"\bCOPPER|CU\b")),
    ("Nickel", re.compile(r"\bNICKEL|NI\b")),
    ("Aluminium", re.compile(r"\bALUMINIUM|ALUMINUM|AL\b")),
    ("Zinc", re.compile(r"\bZINC|ZI\b")),
    ("Rubber", re.compile(r"\bRUBBER\b")),
    ("PVC", re.compile(r"\bPVC\b")),
    ("PTFE", re.compile(r"\bPTFE\b")),
    ("EPDM", re.compile(r"\bEPDM\b")),
    ("Nitrile Rubber", re.compile(r"\bNITRILE RUBBER|NBR\b")),
    ("Fiberglass", re.compile(r"\bFIBERGLASS|FIBER REINFORCED PLASTIC\b")),
]

# Map a grade name to a coarse family (for compatible-grade scoring)
GRADE_FAMILY = {
    "Carbon Steel": "steel",
    "Mild Steel": "steel",
    "High Strength Low Alloy": "steel",
    "Stainless Steel": "stainless",
    "Cast Iron": "iron",
    "Galvanized Iron": "iron",
    "Brass": "copper alloy",
    "Bronze": "copper alloy",
    "Copper": "copper alloy",
    "Nickel": "nickel",
    "Aluminium": "aluminium",
    "Zinc": "zinc",
}

# ---------------------------------------------------------------------- #
# Other field patterns
# ---------------------------------------------------------------------- #
_PRESSURE_RE = re.compile(
    r"\b(?:PN|CLASS|PRESSURE ?RATING)?\s*(\d{1,4})\s*(?:PN|BAR|PSI|KGF/CM2|KG/CM2)\b"
    r"|\bPN\s*(\d{1,4})\b|\bASME\s*CLASS\s*(\d{1,4})\b|\bCLASS\s+(\d{1,4})\b",
    re.IGNORECASE,
)
_VOLTAGE_RE = re.compile(r"\b(\d{2,5})\s*(?:KV|KVA|VOLTS?|V)\b", re.IGNORECASE)
_DN_RE = re.compile(r"\bDN\s*(\d{1,4})\b", re.IGNORECASE)
_NB_RE = re.compile(r"\b(\d{1,4})\s*(?:NB|MM)\b", re.IGNORECASE)
_BEARING_SIZE_RE = re.compile(r"\b(\d{4})\b")
_DIMENSION_EXPR_RE = re.compile(
    r"\b(\d{1,4}(?:\.\d{1,2})?)\s*(?:MM|NB|DN|CM|INCH|FT|MTR)\b", re.IGNORECASE
)
_LENGTH_RE = re.compile(r"\b(\d{1,4}(?:\.\d{1,2})?)\s*(MTR|M|FT|CM|INCH)\b", re.IGNORECASE)
_THREAD_RE = re.compile(r"\b(M[0-9]+(?:\.\d+)?|G\s?\d+(?:\.\d+)?|BS\s?\d+(?:\.\d+)?|UNC\s?\d+|UNF\s?\d+|N\s?\d+)\b", re.IGNORECASE)
_SEAL_RE = re.compile(r"\b(2RS|2ZZ|2Z|6SH|ZZ|RS|DU|C3|C4|N[A-Z]?)\b")
_STANDARD_RE = re.compile(r"\b(ISO|BS|EN|ASTM|ASME|DIN|JIS|IS|IEC)\s?(\d{2,6}[A-Z0-9/-]{0,8})\b")


def _first(regex: "re.Pattern", text: str, groups: int = 1) -> Optional[str]:
    match = regex.search(text)
    if not match:
        return None
    for i in range(1, groups + 1):
        if match.group(i):
            return match.group(i).strip()
    return match.group(0).strip()


def detect_type(text: str) -> Optional[str]:
    for name, pattern in _TYPE_PATTERNS:
        if pattern.search(text):
            return name
    return None


def detect_subtype(text: str, material_type: Optional[str]) -> Optional[str]:
    for name, pattern in _SUBTYPE_PATTERNS:
        if pattern.search(text):
            return name
    return None


def extract_material_grade(text: str) -> Optional[str]:
    for name, pattern in _GRADE_PATTERNS:
        if pattern.search(text):
            return name
    return None


def extract_pressure_rating(text: str) -> Optional[str]:
    match = _PRESSURE_RE.search(text)
    if not match:
        return None
    for value in match.groups():
        if value:
            return f"PN{value}" if "PN" in match.group(0).upper() else f"{value} BAR" if "BAR" in match.group(0).upper() else value
    return None


def extract_voltage_class(text: str) -> Optional[str]:
    match = _VOLTAGE_RE.search(text)
    if not match:
        return None
    value = match.group(1)
    if "K" in match.group(0).upper():
        return f"{value}KV"
    return f"{value}V"


# Types where a bare number + NB/MM means nominal bore (canonical DN form)
_BORE_TYPES = ("Pipe", "Valve", "Pipe Fitting", "Gasket", "Seal", "Spring", "Filter", "Cylinder")


def extract_dimensions(text: str, material_type: Optional[str]) -> Optional[str]:
    """Best-effort primary dimension (bore/size) of the material.

    Canonical forms:
      * nominal bores for pipe-like types -> "DN150" (so 150NB / 150MM / DN150
        all compare equal across CPSEs)
      * bearings -> 4-digit size code ("6205")
      * everything else -> "<value> <UNIT>" (e.g. "60 MM")
    """
    dn = _DN_RE.search(text)
    if dn:
        return f"DN{dn.group(1)}"
    if material_type in _BORE_TYPES:
        nb = _NB_RE.search(text)
        if nb:
            return f"DN{nb.group(1)}"
    if material_type == "Bearing":
        size = _BEARING_SIZE_RE.search(text)
        if size:
            return size.group(1)
    expr = _DIMENSION_EXPR_RE.search(text)
    if expr:
        full = expr.group(0).upper()
        unit_match = re.match(r"^\d+(?:\.\d+)?([A-Z]+)$", full)
        unit = unit_match.group(1) if unit_match else ""
        return f"{expr.group(1)} {unit}".strip()
    return None


def extract_size(text: str, material_type: Optional[str]) -> Optional[str]:
    """Bearing size codes / nominal sizes (kept separate from generic dims)."""
    if material_type == "Bearing":
        size = _BEARING_SIZE_RE.search(text)
        if size:
            return size.group(1)
    dn = _DN_RE.search(text)
    if dn:
        return dn.group(1)
    nb = _NB_RE.search(text)
    if nb:
        return nb.group(1)
    return None


def extract_seal(text: str) -> Optional[str]:
    match = _SEAL_RE.search(text)
    return match.group(1).upper() if match else None


def extract_standard(text: str) -> Optional[str]:
    match = _STANDARD_RE.search(text)
    if not match:
        return None
    return f"{match.group(1)} {match.group(2)}".strip()


def extract_thread(text: str) -> Optional[str]:
    match = _THREAD_RE.search(text)
    return match.group(1).upper() if match else None


def extract_length(text: str) -> Optional[str]:
    match = _LENGTH_RE.search(text)
    if not match:
        return None
    return f"{match.group(1)} {match.group(2).upper()}"


def extract_attributes(raw_description: str, category_hint: Optional[str] = None) -> Dict[str, Any]:
    """Extract structured attributes from a (cleaned, uppercase) description.

    Returns a dict with a stable set of keys (missing values are None) so
    downstream matchers can compare fields uniformly.
    """
    text = (raw_description or "").strip().upper()
    attrs: Dict[str, Any] = {key: None for key in ATTRIBUTE_KEYS}
    if not text:
        return attrs

    material_type = detect_type(text)
    attrs["type"] = material_type
    attrs["subtype"] = detect_subtype(text, material_type)
    attrs["category"] = category_hint or material_type
    attrs["material_grade"] = extract_material_grade(text)
    attrs["pressure_rating"] = extract_pressure_rating(text)
    attrs["voltage_class"] = extract_voltage_class(text)
    attrs["seal"] = extract_seal(text)
    attrs["standard"] = extract_standard(text)
    attrs["thread"] = extract_thread(text)
    attrs["length"] = extract_length(text)
    attrs["size"] = extract_size(text, material_type)
    attrs["dimensions"] = extract_dimensions(text, material_type)
    return attrs


def grade_family(grade: Optional[str]) -> Optional[str]:
    """Coarse metallurgical family for compatible-grade scoring."""
    if not grade:
        return None
    return GRADE_FAMILY.get(grade)

