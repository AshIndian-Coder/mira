import re
from pathlib import Path

from app.services.ingestion.models import MaterialRecord
from app.services.ingestion.pdf_extractor import extract_pdf_text


MATERIAL_CODE_RE = re.compile(r"^\d{8,12}$")
UNIT_RE = re.compile(
    r"^(EA|NO|NOS|KG|M|MTR|SET|LOT|PC|PCS)$",
    re.IGNORECASE,
)
QUANTITY_RE = re.compile(r"^\d+(?:\.\d+)?$")


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def parse_nalco_pdf(
    pdf_path: str | Path,
) -> list[MaterialRecord]:

    pages = extract_pdf_text(Path(pdf_path))
    records: list[MaterialRecord] = []
    seen_codes: set[str] = set()

    for page in pages:
        lines = [
            _clean(line)
            for line in page["text"].splitlines()
        ]
        lines = [line for line in lines if line]

        # Only process pages containing the material table.
        if (
            "Material Code" not in page["text"]
            or "MATERIAL DESCRIPTION" not in page["text"]
        ):
            continue

        for i, line in enumerate(lines):
            if not MATERIAL_CODE_RE.fullmatch(line):
                continue

            material_code = line

            if material_code in seen_codes:
                continue

            description = None
            unit = None
            quantity = None

            for j in range(i + 1, min(i + 7, len(lines))):
                candidate = lines[j]

                if UNIT_RE.fullmatch(candidate):
                    unit = candidate.upper()

                    if (
                        j + 1 < len(lines)
                        and QUANTITY_RE.fullmatch(lines[j + 1])
                    ):
                        quantity = float(lines[j + 1])

                    break

                if (
                    len(candidate) > 5
                    and not candidate.isdigit()
                    and not candidate.startswith("Page No")
                ):
                    description = candidate

            if not description:
                continue

            records.append(
                MaterialRecord(
                    cpse="NALCO",
                    material_code=material_code,
                    description=description,
                    unit=unit,
                    quantity=quantity,
                    source_file=Path(pdf_path).name,
                    source_page=page["page"],
                )
            )

            seen_codes.add(material_code)

    return records


if __name__ == "__main__":
    records = parse_nalco_pdf("data/raw/nalco.pdf")

    print(f"NALCO records: {len(records)}")

    for record in records:
        print(record.to_dict())
