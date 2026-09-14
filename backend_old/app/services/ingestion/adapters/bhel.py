import re
from pathlib import Path

from app.services.ingestion.models import MaterialRecord
from app.services.ingestion.pdf_extractor import extract_pdf_text


MATERIAL_CODE_RE = re.compile(r"^HE\d{10}$")
UNIT_RE = re.compile(
    r"^(EA|NO|NOS|KG|M|MTR|SET|LOT|PC|PCS)$",
    re.IGNORECASE,
)
QUANTITY_RE = re.compile(r"^\d+(?:\.\d+)?$")


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _extract_description(lines: list[str], code_index: int) -> str | None:
    """
    Extract description from the bounded material-row region.

    Expected structure:

        material code
        HSN
        drawing/spec reference [possibly containing description]
        description [optional separate line]
        unit
        quantity
    """

    candidates: list[str] = []

    for j in range(code_index + 1, min(code_index + 7, len(lines))):
        value = lines[j]

        # Once another material code appears, this record is over.
        if MATERIAL_CODE_RE.fullmatch(value):
            break

        # Unit marks the end of the description area.
        if UNIT_RE.fullmatch(value):
            break

        # HSN code.
        if value.isdigit() and len(value) == 4:
            continue

        # Quantity/delivery/etc.
        if QUANTITY_RE.fullmatch(value):
            continue

        # Drawing/specification reference may contain the description.
        if re.search(r"\bNA\b", value, re.IGNORECASE):
            after_na = re.split(r"\bNA\b", value, maxsplit=1, flags=re.IGNORECASE)[-1]
            after_na = _clean(after_na)

            if after_na:
                candidates.append(after_na)

            continue

        # A separate description line.
        if len(value) >= 8:
            candidates.append(value)

    if not candidates:
        return None

    # The first candidate is the description associated with this row.
    return candidates[0]


def _extract_unit_quantity(
    lines: list[str],
    code_index: int,
) -> tuple[str | None, float | None]:

    for j in range(code_index + 1, min(code_index + 10, len(lines))):
        value = lines[j]

        if MATERIAL_CODE_RE.fullmatch(value):
            break

        if UNIT_RE.fullmatch(value):
            unit = value.upper()

            quantity = None

            if (
                j + 1 < len(lines)
                and QUANTITY_RE.fullmatch(lines[j + 1])
            ):
                quantity = float(lines[j + 1])

            return unit, quantity

    return None, None


def parse_bhel_pdf(
    pdf_path: str | Path,
) -> list[MaterialRecord]:

    pdf_path = Path(pdf_path)
    pages = extract_pdf_text(pdf_path)

    records: list[MaterialRecord] = []
    seen_codes: set[str] = set()

    for page in pages:

        # Only pages containing the actual RFQ material table.
        text = page["text"]

        if not (
            "Material Code" in text
            and "Description" in text
            and "Qty" in text
        ):
            continue

        lines = [
            _clean(line)
            for line in text.splitlines()
            if _clean(line)
        ]

        for i, line in enumerate(lines):

            if not MATERIAL_CODE_RE.fullmatch(line):
                continue

            material_code = line

            if material_code in seen_codes:
                continue

            description = _extract_description(lines, i)

            if not description:
                continue

            unit, quantity = _extract_unit_quantity(lines, i)

            records.append(
                MaterialRecord(
                    cpse="BHEL",
                    material_code=material_code,
                    description=description,
                    unit=unit,
                    quantity=quantity,
                    source_file=pdf_path.name,
                    source_page=page["page"],
                )
            )

            seen_codes.add(material_code)

    return records


if __name__ == "__main__":
    records = parse_bhel_pdf("data/raw/GAIL.pdf")

    print(f"BHEL records: {len(records)}")

    for record in records:
        print(record.to_dict())
