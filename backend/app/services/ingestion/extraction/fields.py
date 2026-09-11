import re
from typing import Any


def extract_labeled_fields(
    lines: list[str],
) -> dict[str, Any]:
    """
    Extract strongly recognizable KEY:VALUE fields from free-form
    material descriptions / report rows.

    This function deliberately extracts only fields whose labels are
    unambiguous. Unknown text remains untouched for later processing.
    """

    result: dict[str, Any] = {}

    for line in lines:
        text = re.sub(r"\s+", " ", line).strip()

        if not text:
            continue

        # -------------------------------------------------------------
        # Material of construction / material grade
        #
        # Examples:
        #   MOC:AISI 410
        #   MOC: SA516 GR70
        # -------------------------------------------------------------
        match = re.match(
            r"^\s*MOC\s*[:\-]\s*(.+?)\s*$",
            text,
            re.IGNORECASE,
        )

        if match:
            result["material_grade"] = match.group(1).strip()
            continue

        # -------------------------------------------------------------
        # Part number
        #
        # Examples:
        #   PN:223
        #   P/N:787 WT 03001
        #   PART NO: ABC123
        # -------------------------------------------------------------
        match = re.match(
            r"^\s*(?:PN|P/N|PART\s*NO\.?|PART\s*NUMBER)"
            r"\s*[:\-]\s*(.+?)\s*$",
            text,
            re.IGNORECASE,
        )

        if match:
            result["manufacturer_part_number"] = (
                match.group(1).strip()
            )
            continue

        # -------------------------------------------------------------
        # Model
        #
        # Examples:
        #   MODEL:CC-200-400
        #   PUMP MODEL:CC-200-400
        # -------------------------------------------------------------
        match = re.search(
            r"\bMODEL\s*[:\-]\s*([A-Z0-9][A-Z0-9._/\- ]*)",
            text,
            re.IGNORECASE,
        )

        if match:
            result["model"] = match.group(1).strip()

        # -------------------------------------------------------------
        # Serial number
        # -------------------------------------------------------------
        match = re.search(
            r"\b(?:SL\.?\s*NO\.?|SERIAL\s*NO\.?|SERIAL\s*NUMBER)"
            r"\s*[:\-]\s*([A-Z0-9./\-]+)",
            text,
            re.IGNORECASE,
        )

        if match:
            result["serial_number"] = match.group(1).strip()

        # -------------------------------------------------------------
        # Tag number
        # -------------------------------------------------------------
        match = re.search(
            r"\bTAG\s*NO\.?\s*[:\-]\s*([A-Z0-9./\-]+)",
            text,
            re.IGNORECASE,
        )

        if match:
            result["tag_number"] = match.group(1).strip()

        # -------------------------------------------------------------
        # Location
        # -------------------------------------------------------------
        match = re.match(
            r"^\s*LOCATION\s*[:\-]\s*(.+?)\s*$",
            text,
            re.IGNORECASE,
        )

        if match:
            result["location"] = match.group(1).strip()
            continue

    return result
