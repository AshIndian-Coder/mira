"""Classification mapping: material category -> UNSPSC / NIC codes.

UNSPSC codes are the UN Standard Products and Services Code (verified
family/class level). NIC codes are India's National Industrial
Classification (2011) at section/sub-section level.

These are curated DEFAULTS - refine per category as the national taxonomy
is finalized. The mapping is intentionally a plain dict so domain experts
can extend it without code changes.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

TAXONOMY: Dict[str, Dict[str, str]] = {
    #            UNSPSC (verified family/class)      NIC 2011
    "BEARING": {"unspsc_code": "31171500", "nic_code": "281100"},
    "VALVE": {"unspsc_code": "40141600", "nic_code": "281400"},
    "PIPE": {"unspsc_code": "31300000", "nic_code": "241000"},
    "PIPE FITTING": {"unspsc_code": "31310000", "nic_code": "241000"},
    "FASTENER": {"unspsc_code": "31161500", "nic_code": "251100"},
    "GASKET": {"unspsc_code": "24110000", "nic_code": "222000"},
    "SEAL": {"unspsc_code": "24110000", "nic_code": "222000"},
    "SPRING": {"unspsc_code": "31150000", "nic_code": "259900"},
    "FILTER": {"unspsc_code": "40161500", "nic_code": "281400"},
    "PUMP": {"unspsc_code": "41110000", "nic_code": "281400"},
    "MOTOR": {"unspsc_code": "26112000", "nic_code": "271000"},
    "ELECTRICAL CONNECTOR": {"unspsc_code": "26121500", "nic_code": "271000"},
    "SWITCH": {"unspsc_code": "32150000", "nic_code": "271000"},
    "CONTACT": {"unspsc_code": "32150000", "nic_code": "271000"},
    "RELAY": {"unspsc_code": "32150000", "nic_code": "271000"},
    "TRANSFORMER": {"unspsc_code": "26112000", "nic_code": "271000"},
    "CABLE": {"unspsc_code": "26121500", "nic_code": "271000"},
    "WIRE": {"unspsc_code": "26121500", "nic_code": "271000"},
    "ELECTRODE": {"unspsc_code": "19120000", "nic_code": "242000"},
    "ROD": {"unspsc_code": "19110000", "nic_code": "241000"},
    "SHEET": {"unspsc_code": "19110000", "nic_code": "241000"},
    "COIL": {"unspsc_code": "19110000", "nic_code": "241000"},
    "CYLINDER": {"unspsc_code": "40141600", "nic_code": "281400"},
    "BUSH": {"unspsc_code": "31171500", "nic_code": "281100"},
    "SHAFT": {"unspsc_code": "31110000", "nic_code": "241000"},
}

# Subtype refinement (optional 2nd level): type|subtype -> UNSPSC
SUBTYPE_REFINEMENTS: Dict[str, str] = {
    "VALVE|GATE": "40141600",
    "VALVE|BALL": "40141600",
    "BEARING|BALL": "31171500",
}

DEFAULT_TAXONOMY = {"unspsc_code": None, "nic_code": None}


def map_to_taxonomy(
    category: Optional[str],
    attributes: Optional[Dict[str, Any]] = None,
) -> Dict[str, Optional[str]]:
    """Map a category (and optional subtype) to UNSPSC + NIC codes.

    Returns {"unspsc_code": str|None, "nic_code": str|None}.
    Unknown categories return None codes (never a wrong guess).
    """
    if not category:
        return dict(DEFAULT_TAXONOMY)
    key = str(category).strip().upper()
    entry = TAXONOMY.get(key)
    if entry is None:
        return dict(DEFAULT_TAXONOMY)
    return dict(entry)


def add_taxonomy_entry(category: str, unspsc_code: str, nic_code: str) -> None:
    """Runtime extension of the taxonomy table."""
    TAXONOMY[str(category).strip().upper()] = {
        "unspsc_code": unspsc_code,
        "nic_code": nic_code,
    }

