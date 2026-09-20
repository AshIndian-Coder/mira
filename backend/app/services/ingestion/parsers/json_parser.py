import json
from typing import Any

from app.services.ingestion.normalizer import normalize_record_keys


def parse_json(content_or_path: bytes | str) -> list[dict[str, Any]]:
    """
    Parse JSON content into a list of normalized raw row dictionaries.

    Supports:
    - Top-level list of dicts: [ {"material_code": "MAT001", ...}, ... ]
    - Wrapped object with a list key: {"materials": [...]}, {"records": [...]}, {"items": [...]}, {"data": [...]}, {"rows": [...] }
    - Single material object: {"material_code": "MAT001", "description": "..."}
    - Key alias normalization via normalizer.py
    - Reports clear errors for invalid top-level structures or malformed JSON syntax
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
        raise ValueError(f"Expected bytes or str for JSON parsing, got {type(content_or_path)}")

    if not text.strip():
        return []

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON syntax: {exc}")

    raw_items: list[Any]

    if isinstance(data, list):
        raw_items = data
    elif isinstance(data, dict):
        # Look for wrapped lists
        list_keys = ["materials", "records", "items", "data", "rows", "material_list"]
        found_list = None
        for k in list_keys:
            if k in data and isinstance(data[k], list):
                found_list = data[k]
                break

        if found_list is not None:
            raw_items = found_list
        else:
            # Check if this single dictionary is a material record
            raw_items = [data]
    else:
        raise ValueError(
            f"Invalid JSON top-level structure: expected an array or object, got {type(data).__name__}"
        )

    records: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        normalized = normalize_record_keys(item)
        if normalized:
            records.append(normalized)

    return records
