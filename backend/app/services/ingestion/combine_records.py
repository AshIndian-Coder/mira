import csv
from pathlib import Path


INPUTS = [
    Path("data/processed/ntpc_materials_enriched.csv"),
    Path("data/processed/bhel_materials_enriched.csv"),
    Path("data/processed/nalco_materials_enriched.csv"),
]

OUTPUT = Path(
    "data/processed/materials_all_enriched.csv"
)

CANONICAL_FIELDS = [
    "cpse",
    "material_code",
    "description",
    "normalized_description",
    "category",
    "unit",
    "quantity",
    "manufacturer",
    "manufacturer_part_number",
    "material_grade",
    "dimensions",
    "specifications",
    "other_attributes",
    "parsed_specifications",
    "source_file",
    "source_page",
]


def main():
    rows = []

    for path in INPUTS:
        if not path.exists():
            print(f"Skipping missing file: {path}")
            continue

        with path.open(
            "r",
            encoding="utf-8",
            newline="",
        ) as file:
            file_rows = list(csv.DictReader(file))

        print(f"{path.name}: {len(file_rows)} records")

        for row in file_rows:
            normalized_row = {
                field: row.get(field, "")
                for field in CANONICAL_FIELDS
            }

            rows.append(normalized_row)

    if not rows:
        raise RuntimeError("No material records found.")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=CANONICAL_FIELDS,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)

    cpse_counts = {}

    for row in rows:
        cpse = row["cpse"]
        cpse_counts[cpse] = cpse_counts.get(cpse, 0) + 1

    print(f"\nTotal records: {len(rows)}")

    for cpse, count in sorted(cpse_counts.items()):
        print(f"  {cpse}: {count}")

    print(f"\nSaved: {OUTPUT}")


if __name__ == "__main__":
    main()
