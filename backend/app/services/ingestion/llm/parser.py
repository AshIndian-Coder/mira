from __future__ import annotations

import json
import re
from typing import Any


ALLOWED_FIELDS = {
    "material_grade",
    "manufacturer",
    "manufacturer_part_number",
    "model",
    "dimensions",
    "other_specifications",
}


def parse_llm_json(text: str) -> dict[str, Any]:
    """
    Parse JSON returned by the local model.

    Handles both plain JSON and Markdown fenced JSON.
    Unknown fields are discarded.
    Invalid JSON returns an empty dictionary.
    """

    cleaned = text.strip()

    # Remove ```json ... ``` or ``` ... ```
    fenced = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if fenced:
        cleaned = fenced.group(1).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Best-effort recovery if the model surrounded JSON with text.
        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if start == -1 or end <= start:
            return {}

        try:
            data = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return {}

    if not isinstance(data, dict):
        return {}

    return {
        key: value
        for key, value in data.items()
        if key in ALLOWED_FIELDS
    }
