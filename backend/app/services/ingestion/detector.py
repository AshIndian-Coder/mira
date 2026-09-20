from pathlib import Path

SUPPORTED_FORMATS: dict[str, str] = {
    ".csv": "csv",
    ".txt": "txt",
    ".xml": "xml",
    ".json": "json",
    ".xls": "excel",
    ".xlsx": "excel",
}


def detect_file_type(file_path_or_name: str) -> str:
    """
    Determine which format parser should be used based on file extension.
    Raises ValueError for unsupported formats.
    """
    extension = Path(file_path_or_name).suffix.lower()
    if extension not in SUPPORTED_FORMATS:
        supported_str = ", ".join(sorted(SUPPORTED_FORMATS.keys()))
        raise ValueError(
            f"Unsupported file format: '{extension}'. Supported formats: {supported_str}"
        )
    return SUPPORTED_FORMATS[extension]
