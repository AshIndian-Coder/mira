import csv
from pathlib import Path

from app.services.ingestion.adapters.bhel import parse_bhel_pdf
from app.services.ingestion.adapters.nalco import parse_nalco_pdf


OUTPUT_FIELDS = [
    "cpse",
    "material_code",
    "description",
    "category",
    "unit",
    "quantity",
    "manufacturer",
    "manufacturer_part_number",
    "material_grade",
    "dimensions",
    "specifications",
    "other_attributes",
    "source_file",
    "source_page",
]


def export_records(records, output_path: str | Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=OUTPUT_FIELDS,
        )

        writer.writeheader()

        for record in records:
            writer.writerow(record.to_dict())


def main():
    bhel = parse_bhel_pdf("data/raw/GAIL.pdf")
    nalco = parse_nalco_pdf("data/raw/nalco.pdf")

    export_records(
        bhel,
        "data/processed/bhel_materials.csv",
    )

    export_records(
        nalco,
        "data/processed/nalco_materials.csv",
    )

    print(f"BHEL records exported: {len(bhel)}")
    print(f"NALCO records exported: {len(nalco)}")


if __name__ == "__main__":
    main()
