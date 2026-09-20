from pathlib import Path
from typing import Any

from app.services.ingestion.detector import detect_file_type
from app.services.ingestion.parsers.csv_parser import parse_csv
from app.services.ingestion.parsers.excel_parser import parse_excel
from app.services.ingestion.parsers.json_parser import parse_json
from app.services.ingestion.parsers.txt_parser import parse_txt
from app.services.ingestion.parsers.xml_parser import parse_xml


def parse_legacy_file(content_or_path: bytes | str, filename: str) -> list[dict[str, Any]]:
    """
    Detect format and parse legacy material file content into normalized raw record dictionaries.
    """
    file_type = detect_file_type(filename)

    if file_type == "csv":
        return parse_csv(content_or_path)
    elif file_type == "txt":
        return parse_txt(content_or_path)
    elif file_type == "xml":
        return parse_xml(content_or_path)
    elif file_type == "json":
        return parse_json(content_or_path)
    elif file_type == "excel":
        return parse_excel(content_or_path, filename=filename)
    else:
        raise ValueError(f"Unsupported file format: {file_type}")


def ingest_file(file_path: str | Path) -> list[dict[str, Any]]:
    """
    Ingest legacy material file from a file path.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with open(path, "rb") as f:
        content = f.read()
    return parse_legacy_file(content, filename=path.name)
