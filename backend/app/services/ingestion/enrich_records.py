import csv
import json
from pathlib import Path

from app.services.normalization.service import normalize_material_description
from app.services.parsing.service import parse_specifications


INPUTS = [
    Path("data/processed/ntpc_materials.csv"),
    Path("data/processed/bhel_materials.csv"),
    Path("data/processed/nalco_materials.csv"),
]


def enrich_file(input_path: Path) -> Path:
    output_path = input_path.with_name(
        f"{input_path.stem}_enriched.csv"
    )

    records = []

    with input_path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:
            description = row.get("description", "")

            normalized = normalize_material_description(
                description
            )

            parsed = parse_specifications(description)

            row["normalized_description"] = normalized
            row["parsed_specifications"] = json.dumps(
                parsed,
                ensure_ascii=False,
            )

            # Preserve an existing structured grade if one exists.
            row["material_grade"] = (
                row.get("material_grade")
                or parsed.get("material_grade")
                or ""
            )

            row["dimensions"] = json.dumps(
                parsed.get("dimensions"),
                ensure_ascii=False,
            )

            records.append(row)

    fieldnames = list(records[0].keys()) if records else []

    # Ensure these fields exist even for empty/unusual inputs.
    for field in [
        "normalized_description",
        "parsed_specifications",
        "material_grade",
        "dimensions",
    ]:
        if field not in fieldnames:
            fieldnames.append(field)

    with output_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(records)

    return output_path


def main():
    for input_path in INPUTS:

        if not input_path.exists():
            print(f"Skipping missing file: {input_path}")
            continue

        output_path = enrich_file(input_path)

        with output_path.open(
            "r",
            encoding="utf-8",
            newline="",
        ) as file:
            count = sum(1 for _ in file) - 1

        print(
            f"{input_path.name}: "
            f"{count} records → {output_path.name}"
        )


if __name__ == "__main__":
    main()
