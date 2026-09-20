import re
from typing import Any

from app.services.ingestion.normalizer import normalize_field_name, normalize_record_keys


def parse_txt(content_or_path: bytes | str) -> list[dict[str, Any]]:
    """
    Parse pipe-delimited legacy TXT files into a list of normalized row dictionaries.

    Supports:
    - Positional pipe format: CODE|DESCRIPTION|UNIT
    - Header-defined pipe format: MATERIAL_CODE|DESCRIPTION|UNIT
    - Skipping blank lines and malformed rows safely without failing the whole upload
    - Trimming leading and trailing whitespace around tokens
    """
    if isinstance(content_or_path, bytes):
        text = content_or_path.decode("utf-8-sig", errors="replace")
    elif isinstance(content_or_path, str):
        if "\n" not in content_or_path and len(content_or_path) < 1024:
            try:
                with open(content_or_path, "r", encoding="utf-8-sig", errors="replace") as f:
                    text = f.read()
            except (OSError, FileNotFoundError):
                text = content_or_path
        else:
            text = content_or_path
    else:
        raise ValueError(f"Expected bytes or str for TXT parsing, got {type(content_or_path)}")

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    records: list[dict[str, Any]] = []

    # Check if first line contains recognized column header names
    first_parts = [p.strip() for p in lines[0].split("|")]
    header_mapping: list[str | None] | None = None

    if len(first_parts) >= 2:
        mapped_headers = [normalize_field_name(p) for p in first_parts]
        # If at least material_code or description is recognized in the first row
        if any(h in {"material_code", "description"} for h in mapped_headers):
            header_mapping = mapped_headers
            data_lines = lines[1:]
        else:
            data_lines = lines
    else:
        data_lines = lines

    default_positional_fields = [
        "material_code",
        "description",
        "unit",
        "manufacturer",
        "category",
        "material_grade",
    ]

    for line in data_lines:
        parts = [p.strip() for p in line.split("|")]
        # A valid material record needs at least code and description or 2+ non-empty parts
        if len(parts) < 2:
            continue

        row_dict: dict[str, Any] = {}
        if header_mapping:
            for idx, part in enumerate(parts):
                if not part:
                    continue
                if idx < len(header_mapping) and header_mapping[idx]:
                    field_name = header_mapping[idx]
                    row_dict[field_name] = part
                elif idx < len(first_parts):
                    row_dict[first_parts[idx]] = part
                else:
                    row_dict[f"column_{idx + 1}"] = part
        else:
            for idx, part in enumerate(parts):
                if not part:
                    continue
                if idx < len(default_positional_fields):
                    field_name = default_positional_fields[idx]
                    row_dict[field_name] = part
                else:
                    row_dict[f"attribute_{idx + 1}"] = part

        if row_dict.get("description") or (len(parts) >= 2 and parts[1]):
            normalized = normalize_record_keys(row_dict)
            if normalized:
                records.append(normalized)

    return records
