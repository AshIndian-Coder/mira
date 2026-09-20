import re
from typing import Any

# Canonical field name mappings for legacy file ingestion.
FIELD_ALIASES: dict[str, set[str]] = {
    "material_code": {
        "material code",
        "material_code",
        "mat code",
        "mat_code",
        "item no",
        "item_no",
        "item number",
        "item_number",
        "material number",
        "material_number",
        "code",
        "source_material_code",
        "materialcode",
        "matcode",
        "itemnumber",
        "itemno",
        "materialnumber",
        "material id",
        "material_id",
        "item",
    },
    "description": {
        "description",
        "material description",
        "material_description",
        "material name",
        "material_name",
        "item desc",
        "item_desc",
        "item name",
        "item_name",
        "desc",
        "materialdescription",
        "materialname",
        "itemdesc",
        "itemname",
        "item_description",
        "item description",
        "details",
    },
    "unit": {
        "unit",
        "uom",
        "unit of measure",
        "unit_of_measure",
        "measure unit",
        "measure_unit",
        "unitofmeasure",
        "measureunit",
    },
    "category": {
        "category",
        "material category",
        "material_category",
        "materialcategory",
        "group",
        "material group",
        "material_group",
    },
    "manufacturer": {
        "manufacturer",
        "mfr",
        "make",
        "vendor",
        "brand",
        "manufacturer name",
        "manufacturer_name",
    },
    "manufacturer_part_number": {
        "manufacturer part number",
        "manufacturer_part_number",
        "part number",
        "part_number",
        "part no",
        "part_no",
        "partno",
        "partnumber",
        "mpn",
        "mfr part number",
        "mfr_part_number",
        "mfr pn",
        "mfr_pn",
        "pn",
    },
    "material_grade": {
        "material grade",
        "material_grade",
        "grade",
        "mat grade",
        "mat_grade",
        "materialgrade",
    },
    "cpse": {
        "cpse",
        "source org",
        "source_org",
        "company",
        "org",
        "sourceorg",
    },
    "quantity": {
        "quantity",
        "qty",
        "amount",
    },
}


def normalize_field_name(field_name: str) -> str | None:
    """
    Map non-standard column/key names to MIRA's standard internal field names.

    Handles:
    - case differences (e.g. UPPER, CamelCase, lowercase)
    - underscores and hyphens
    - multiple/repeated whitespace
    """
    if not field_name:
        return None

    # Separate camelCase words: "materialCode" -> "material Code"
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(field_name).strip())

    normalized = separated.lower()
    # Replace underscores and hyphens with spaces
    normalized = re.sub(r"[_\-]+", " ", normalized)
    # Compress multiple spaces
    normalized = re.sub(r"\s+", " ", normalized).strip()

    for standard_name, aliases in FIELD_ALIASES.items():
        if normalized in aliases or normalized.replace(" ", "") in {
            a.replace(" ", "").replace("_", "") for a in aliases
        }:
            return standard_name

    return None


def normalize_record_keys(row: dict[str, Any]) -> dict[str, Any]:
    """
    Transform raw row dictionary keys into canonical field names where possible.
    Non-standard unmapped attributes are preserved in other_attributes.
    """
    normalized_row: dict[str, Any] = {}
    other_attributes: dict[str, Any] = {}

    for key, value in row.items():
        if value is None:
            continue

        clean_val = str(value).strip() if isinstance(value, str) else value
        # Don't retain empty strings
        if clean_val == "":
            continue

        standard_key = normalize_field_name(str(key))
        if standard_key:
            if standard_key not in normalized_row:
                normalized_row[standard_key] = clean_val
        else:
            other_attributes[str(key)] = clean_val

    if other_attributes and "other_attributes" not in normalized_row:
        normalized_row["other_attributes"] = other_attributes

    return normalized_row
