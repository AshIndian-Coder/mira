import csv
from pathlib import Path

from app.services.ingestion.ntpc_parser import parse_ntpc_pdf


def export_ntpc_records(
    pdf_path: str | Path,
    output_path: str | Path,
) -> int:
    records = parse_ntpc_pdf(pdf_path)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "cpse",
        "material_code",
        "description",
        "unit",
        "quantity",
        "source_file",
        "source_page",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    return len(records)


if __name__ == "__main__":
    count = export_ntpc_records(
        "data/raw/NTPC.pdf",
        "data/processed/ntpc_materials.csv",
    )

    print(f"Exported {count} records.")
