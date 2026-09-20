import csv
import io
from typing import Any

from app.services.ingestion.normalizer import normalize_record_keys


def parse_csv(content_or_path: bytes | str) -> list[dict[str, Any]]:
    """
    Parse CSV text or bytes into a list of normalized raw row dictionaries.
    Handles BOM (utf-8-sig) and maps column headers via field normalization.
    """
    if isinstance(content_or_path, bytes):
        text = content_or_path.decode("utf-8-sig", errors="replace")
    elif isinstance(content_or_path, str):
        # Check if it's a file path
        if "\n" not in content_or_path and len(content_or_path) < 1024:
            try:
                with open(content_or_path, "r", encoding="utf-8-sig", errors="replace") as f:
                    text = f.read()
            except (OSError, FileNotFoundError):
                text = content_or_path
        else:
            text = content_or_path
    else:
        raise ValueError(f"Expected bytes or str for CSV parsing, got {type(content_or_path)}")

    if not text.strip():
        return []

    # Detect delimiter if possible, defaulting to comma
    sample = text[:2048]
    delimiter = ","
    try:
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(sample, delimiters=",\t;|")
        delimiter = dialect.delimiter
    except Exception:
        delimiter = ","

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    records: list[dict[str, Any]] = []

    for row in reader:
        # Filter None keys or values
        clean_row = {k: v for k, v in row.items() if k is not None and v is not None}
        if not clean_row:
            continue
        normalized = normalize_record_keys(clean_row)
        if normalized:
            records.append(normalized)

    return records
