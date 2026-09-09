import re
from pathlib import Path
import pymupdf


MATERIAL_CODE_PATTERN = re.compile(r"^M[A-Z0-9]{6,}$")
QUANTITY_PATTERN = re.compile(r"^\d+(?:\.\d+)?$")


def is_material_code(line: str) -> bool:
    return bool(MATERIAL_CODE_PATTERN.fullmatch(line.strip()))


def is_quantity(line: str) -> bool:
    return bool(QUANTITY_PATTERN.fullmatch(line.strip()))


def parse_ntpc_pdf(pdf_path: str | Path) -> list[dict]:
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    records = []

    with pymupdf.open(pdf_path) as document:
        for page_number, page in enumerate(document, start=1):
            lines = [
                line.strip()
                for line in page.get_text("text").splitlines()
                if line.strip()
            ]

            i = 0

            while i < len(lines):
                if not is_material_code(lines[i]):
                    i += 1
                    continue

                material_code = lines[i]

                # Expected structure:
                # material code
                # description
                # quantity
                # unit

                if i + 3 >= len(lines):
                    i += 1
                    continue

                description = lines[i + 1]
                quantity = lines[i + 2]
                unit = lines[i + 3]

                if not is_quantity(quantity):
                    i += 1
                    continue

                # Avoid accidentally treating headers or unrelated text
                # as material records.
                if len(description) < 3:
                    i += 1
                    continue

                records.append(
                    {
                        "cpse": "NTPC",
                        "material_code": material_code,
                        "description": description,
                        "unit": unit,
                        "quantity": float(quantity),
                        "source_file": pdf_path.name,
                        "source_page": page_number,
                    }
                )

                i += 4

    return records
