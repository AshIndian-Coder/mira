import re
from pathlib import Path
from typing import Any

from app.services.ingestion.pdf_extractor import extract_pdf_text


MATERIAL_CODE_RE = re.compile(r"^\d{8,12}$")
UNIT_RE = re.compile(r"^(EA|NO|NOS|KG|M|MTR|SET|LOT|PC|PCS)$", re.IGNORECASE)
QUANTITY_RE = re.compile(r"^\d+(?:\.\d+)?$")


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def parse_nalco_pdf(pdf_path: str | Path) -> list[dict[str, Any]]:
    pages = extract_pdf_text(Path(pdf_path))
    records: list[dict[str, Any]] = []

    for page in pages:
        lines = [_clean(line) for line in page["text"].splitlines()]
        lines = [line for line in lines if line]

        for i, line in enumerate(lines):
            if not MATERIAL_CODE_RE.fullmatch(line):
                continue

            material_code = line

            description = None
            unit = None
            quantity = None

            for j in range(i + 1, min(i + 7, len(lines))):
                candidate = lines[j]

                if UNIT_RE.fullmatch(candidate):
                    unit = candidate.upper()

                    if j + 1 < len(lines) and QUANTITY_RE.fullmatch(lines[j + 1]):
                        quantity = float(lines[j + 1])

                    break

                if (
                    not candidate.isdigit()
                    and len(candidate) > 5
                    and not candidate.startswith("Page No")
                ):
                    description = candidate

            if not description:
                continue

            records.append(
                {
                    "cpse": "NALCO",
                    "material_code": material_code,
                    "description": description,
                    "category": None,
                    "unit": unit,
                    "quantity": quantity,
                    "manufacturer": None,
                    "manufacturer_part_number": None,
                    "source_file": Path(pdf_path).name,
                    "source_page": page["page"],
                }
            )

    return records


if __name__ == "__main__":
    import json

    records = parse_nalco_pdf("data/raw/nalco.pdf")

    print(f"NALCO records: {len(records)}")

    for record in records[:10]:
        print(json.dumps(record, indent=2))
