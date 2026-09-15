"""Domain-specific abbreviation expansion for material descriptions.

Critical for cross-CPSE matching: IOCL writes "BRG", BPCL writes "BEARING".
Expansion is word-boundary safe (never touches tokens like "6205" or seal
codes like "2RS") and is a curated, extendable dictionary.

    expand_abbreviations("BRG BALL 6205 2RS") -> "BEARING BALL 6205 2RS"
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

# abbreviation -> full term (all keys uppercase; longer keys are applied
# first so "BEAR" would win over "B" style conflicts).
ABBREVIATION_MAP: Dict[str, str] = {
    # --- Material types ---
    "BRG": "BEARING",
    "VLV": "VALVE",
    "PPL": "PIPE",
    "GSK": "GASKET",
    "WASH": "WASHER",
    "WSH": "WASHER",
    "PLG": "PLUG",
    "SPRG": "SPRING",
    "FLT": "FILTER",
    "CNV": "CONVEX",
    "CLP": "COUPLING",
    "FLG": "FLANGE",
    "ELB": "ELBOW",
    "RDT": "REDUCER",
    "SHFT": "SHAFT",
    "ELEC": "ELECTRICAL",
    "PWR": "POWER",
    "CBL": "CABLE",
    "WIR": "WIRE",
    "SWCH": "SWITCH",
    "CNTC": "CONTACTOR",
    "RLY": "RELAY",
    "XFRMR": "TRANSFORMER",
    "RBR": "RUBBER",
    "FRP": "FIBER REINFORCED PLASTIC",
    "GRD": "GROUND",
    "GND": "GROUND",
    "INSUL": "INSULATION",
    "INS": "INSULATION",
    "GLS": "GLASS",
    "NBR": "NITRILE RUBBER",
    "PVC": "PVC",      # polymer name - intentionally kept
    "PTFE": "PTFE",    # polymer name - intentionally kept
    "EPDM": "EPDM",    # polymer name - intentionally kept

    # --- Metals / grades (word-boundary only) ---
    "CS": "CARBON STEEL",
    "MS": "MILD STEEL",
    "SS": "STAINLESS STEEL",
    "HSLA": "HIGH STRENGTH LOW ALLOY",
    "BRZ": "BRONZE",
    "CU": "COPPER",
    "NI": "NICKEL",
    "AL": "ALUMINIUM",
    "ALUM": "ALUMINIUM",
    "ZI": "ZINC",
    "CI": "CAST IRON",
    "GI": "GALVANIZED IRON",

    # --- Fasteners ---
    "SCRW": "SCREW",
    "HEX": "HEXAGON",
    "LG": "LOCK",
    "RVT": "RIVET",
    "ANCHR": "ANCHOR",

    # --- Standards / dimension prefixes (kept as-is, listed for clarity) ---
    "DN": "DN",        # nominal diameter - parsed by attribute extractor
    "NB": "NB",        # nominal bore - parsed by attribute extractor
    "ISO": "ISO",
    "BS": "BS",
    "EN": "EN",
    "DIN": "DIN",
    "JIS": "JIS",
    "ASTM": "ASTM",
    "ASME": "ASME",
}

_PATTERNS: List[Tuple[str, str]] = []
_REGEXES: List[Tuple["re.Pattern", str]] = []


def _rebuild_patterns() -> None:
    """Recompile replacement patterns (longest abbreviation first)."""
    global _PATTERNS, _REGEXES
    _PATTERNS = sorted(ABBREVIATION_MAP.items(), key=lambda kv: len(kv[0]), reverse=True)
    _REGEXES = [
        (re.compile(rf"\b{re.escape(abbr)}\b"), full)
        for abbr, full in _PATTERNS
        if abbr != full  # no-op entries (PVC, PTFE, ...) skipped
    ]


def expand_abbreviations(text: str) -> str:
    """Expand known industrial abbreviations (input expected uppercase).

    Word boundaries guarantee "6205" or "2RS" are never rewritten, and
    already-expanded words are left alone.
    """
    if not text or not isinstance(text, str):
        return text or ""
    result = text
    for pattern, replacement in _REGEXES:
        if pattern.search(result):
            result = pattern.sub(replacement, result)
    return result


def get_abbreviation_map() -> Dict[str, str]:
    """Copy of the dictionary (for admin UIs / testing)."""
    return dict(ABBREVIATION_MAP)


def add_abbreviation(abbr: str, full_term: str) -> None:
    """Runtime extension (e.g. learned from reviewer feedback)."""
    key = abbr.strip().upper()
    value = full_term.strip().upper()
    if key and value and key != value:
        ABBREVIATION_MAP[key] = value
        _rebuild_patterns()


_rebuild_patterns()

