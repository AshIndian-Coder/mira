import xml.etree.ElementTree as ET
from typing import Any

from app.services.ingestion.normalizer import normalize_record_keys


def parse_xml(content_or_path: bytes | str) -> list[dict[str, Any]]:
    """
    Parse XML content into a list of normalized raw row dictionaries.

    Supports:
    - Standard structures: <materials><material>...</material></materials>
    - Generic item structures: <items><item>...</item></items>, <records><record>...</record></records>, <root><row>...</row></root>
    - Reading both child tags and element attributes
    - Missing optional fields handled safely
    - Raises ValueError with clear error details on malformed XML
    """
    if isinstance(content_or_path, bytes):
        raw_bytes = content_or_path
    elif isinstance(content_or_path, str):
        if "\n" not in content_or_path and len(content_or_path) < 1024:
            try:
                with open(content_or_path, "rb") as f:
                    raw_bytes = f.read()
            except (OSError, FileNotFoundError):
                raw_bytes = content_or_path.encode("utf-8")
        else:
            raw_bytes = content_or_path.encode("utf-8")
    else:
        raise ValueError(f"Expected bytes or str for XML parsing, got {type(content_or_path)}")

    if not raw_bytes.strip():
        return []

    try:
        root = ET.fromstring(raw_bytes)
    except ET.ParseError as exc:
        raise ValueError(f"Malformed XML syntax: {exc}")

    # Identify record nodes: look for common container child tags or use direct children
    record_tags = {"material", "item", "record", "row", "product", "part", "entry"}
    found_nodes: list[ET.Element] = []

    # First search for any tag in record_tags anywhere in the document
    for tag in record_tags:
        nodes = root.findall(f".//{tag}")
        if nodes:
            found_nodes.extend(nodes)

    # If no specific tags matched, use direct children of root
    if not found_nodes:
        found_nodes = list(root)

    records: list[dict[str, Any]] = []

    for node in found_nodes:
        row_dict: dict[str, Any] = {}

        # 1. Include element attributes if present
        for attr_k, attr_v in node.attrib.items():
            if attr_v and attr_v.strip():
                row_dict[attr_k] = attr_v.strip()

        # 2. Include child element tags
        for child in node:
            tag_name = child.tag
            # Remove namespace prefix if present (e.g. '{http://...}code' -> 'code')
            if "}" in tag_name:
                tag_name = tag_name.split("}", 1)[1]

            text_val = (child.text or "").strip()
            if text_val:
                row_dict[tag_name] = text_val

            # Also check child attributes
            for cattr_k, cattr_v in child.attrib.items():
                if cattr_v and cattr_v.strip() and cattr_k not in row_dict:
                    row_dict[f"{tag_name}_{cattr_k}"] = cattr_v.strip()

        if row_dict:
            normalized = normalize_record_keys(row_dict)
            if normalized:
                records.append(normalized)

    return records
