"""
Unit of Measure (UOM) standardization.

"KG / Kilogram / Kgs / KGM" -> "KG",  "MTR / Meter / M" -> "MTR",
"NOS / Numbers / Pcs" -> "NOS", etc.

Unknown UOMs are returned upper-cased (data preservation) but flagged as
unknown via ``is_known_uom`` so quality scoring can penalize them.
"""
from __future__ import annotations

import re
from typing import Dict, Optional

UOM_MAP: Dict[str, str] = {
    "NOS": "NOS", "NO": "NOS", "NUM": "NOS", "NUMS": "NOS", "NUMBER": "NOS",
    "NUMBERS": "NOS", "PCS": "NOS", "PC": "NOS", "PIECE": "NOS",
    "PIECES": "NOS", "EA": "NOS", "EACH": "NOS", "ITEM": "NOS", "ITEMS": "NOS",
    "KG": "KG", "KGS": "KG", "KGM": "KG", "KLO": "KG", "KILO": "KG",
    "KILOGRAM": "KG", "KILOGRAMS": "KG", "K": "KG", "KGS.": "KG",
    "MT": "MT", "METRIC TONNE": "MT", "MTS": "MT",
    "TNE": "TNE", "TNE.": "TNE", "TON": "TNE", "TONNE": "TNE", "TONNES": "TNE",
    "QT": "QT", "QUINTAL": "QT", "QUINTALS": "QT",
    "GM": "GM", "G": "GM", "GRAM": "GM", "GRAMS": "GM",
    "MTR": "MTR", "MTRS": "MTR", "M": "MTR", "METER": "MTR", "METERS": "MTR",
    "METRE": "MTR", "METRES": "MTR", "LTH": "MTR",
    "FT": "FT", "Ft": "FT", "FOOT": "FT", "FEET": "FT",
    "INCH": "INCH", "IN": "INCH", "INS": "INCH",
    "CM": "CM", "CENTIMETER": "CM", "CENTIMETRE": "CM",
    "MM": "MM", "MILLIMETER": "MM", "MILLIMETRE": "MM",
    "SQR MTR": "SQR MTR", "SQM": "SQR MTR", "SQ M": "SQR MTR",
    "SQ.M": "SQR MTR", "M2": "SQR MTR", "SQMT": "SQR MTR",
    "SQR MTRS": "SQR MTR", "SQMTR": "SQR MTR",
    "CBM": "CBM", "CUM": "CBM", "CUMES": "CBM", "M3": "CBM",
    "CUBIC METER": "CBM", "CUBIC METRE": "CBM", "CFT": "CBM", "CUBIC FT": "CBM",
    "L": "L", "LTR": "L", "LITRE": "L", "LITRES": "L", "LITER": "L",
    "LITERS": "L", "LT": "L",
    "SET": "SET", "SET.": "SET", "SET OF": "SET",
    "PAIR": "PAIR", "PAIRS": "PAIR",
    "DOZEN": "DOZEN", "DOZ": "DOZEN", "DZN": "DOZEN",
    "LOT": "LOT", "LTH SET": "SET",
    "BAG": "BAG", "BAGS": "BAG", "PKT": "PACKET", "PACK": "PACKET",
    "PACKS": "PACKET", "PACKET": "PACKET", "PACKETS": "PACKET",
    "DRUM": "DRUM", "DRM": "DRUM", "CAN": "CAN", "CANS": "CAN",
    "BOX": "BOX", "BOXES": "BOX", "CTN": "BOX", "CARTON": "BOX",
    "ROLL": "ROLL", "ROLLS": "ROLL", "BALE": "BALE", "BLS": "BALE",
    "UNIT": "UNIT", "UNITS": "UNIT", "RIM": "RIM",
    "BOLTING": "KG",  # rod sold by weight
    "HR": "HR", "HOUR": "HR", "HOURS": "HR", "HRS": "HR",
    "DAY": "DAY", "DAYS": "DAY",
    "KW": "KW", "KVA": "KVA", "KV": "KV", "KWH": "KWH", "AMP": "AMP",
    "AMPERE": "AMP", "A": "AMP",
    "PSI": "PSI", "BAR": "BAR", "PN": "PN",
    "LPM": "LPM", "GPM": "GPM", "GSM": "GSM",
    "BOTTLE": "BOTTLE", "JT": "SET", "JOINT": "SET",
}


def _clean(raw: str) -> str:
    text = str(raw).strip().upper()
    text = re.sub(r"\s+", " ", text)
    return text.rstrip(".")


def normalize_uom(raw: Optional[str]) -> Optional[str]:
    """Return the canonical UOM code, or None for empty input.

    Unknown units are upper-cased and returned as-is (never silently lost);
    use ``is_known_uom`` to check canonicality.
    """
    if raw is None:
        return None
    text = _clean(raw)
    if not text:
        return None
    if text in UOM_MAP:
        return UOM_MAP[text]
    return text


def is_known_uom(uom: Optional[str]) -> bool:
    """True when the (possibly already normalized) UOM is canonical."""
    if uom is None:
        return False
    return _clean(uom) in set(UOM_MAP.values())


def get_uom_map() -> Dict[str, str]:
    return dict(UOM_MAP)
