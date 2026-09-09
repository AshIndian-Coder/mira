import csv
import json
from pathlib import Path

from app.services.blocking.service import (
    MaterialForBlocking,
    generate_block_keys,
)


INPUT = Path("data/processed/materials_all_enriched.csv")
OUTPUT = Path("data/processed/cross_cpse_candidates.csv")


def load_materials():
    materials = []

    with INPUT.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:
        for row in csv.DictReader(file):
            parsed = row.get("parsed_specifications", "")

            try:
                parsed_specs = json.loads(parsed) if parsed else {}
            except json.JSONDecodeError:
                parsed_specs = {}

            materials.append({
                **row,
                "parsed_specifications": parsed_specs,
            })

    return materials


def to_blocking_material(row):
    return MaterialForBlocking(
        id=int(row["material_code"].strip()[-8:], 36)
        if False
        else hash(
            f'{row["cpse"]}:{row["material_code"]}'
        ),
        category=row.get("category") or None,
        normalized_description=row.get(
            "normalized_description", ""
        ),
        material_grade=row.get("material_grade") or None,
        manufacturer_part_number=(
            row.get("manufacturer_part_number") or None
        ),
    )


def main():
    materials = load_materials()

    # Build blocking keys once.
    keyed = []

    for row in materials:
        material = to_blocking_material(row)

        keyed.append((
            row,
            generate_block_keys(material),
        ))

    total_pairs = 0
    candidate_pairs = 0

    output_rows = []

    for i, (source, source_keys) in enumerate(keyed):

        for target, target_keys in keyed[i + 1:]:

            # Only cross-CPSE pairs.
            if source["cpse"] == target["cpse"]:
                continue

            total_pairs += 1

            shared = source_keys.intersection(target_keys)

            if not shared:
                continue

            candidate_pairs += 1

            output_rows.append({
                "source_cpse": source["cpse"],
                "source_material_code": source["material_code"],
                "source_description": source["description"],
                "target_cpse": target["cpse"],
                "target_material_code": target["material_code"],
                "target_description": target["description"],
                "shared_block_keys": "|".join(sorted(shared)),
            })

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:

        fields = [
            "source_cpse",
            "source_material_code",
            "source_description",
            "target_cpse",
            "target_material_code",
            "target_description",
            "shared_block_keys",
        ]

        writer = csv.DictWriter(
            file,
            fieldnames=fields,
        )

        writer.writeheader()
        writer.writerows(output_rows)

    reduction_ratio = (
        1 - candidate_pairs / total_pairs
        if total_pairs
        else 0
    )

    print(f"Total cross-CPSE pairs: {total_pairs:,}")
    print(f"Candidate pairs: {candidate_pairs:,}")
    print(f"Reduction ratio: {reduction_ratio:.2%}")
    print(f"Saved: {OUTPUT}")


if __name__ == "__main__":
    main()
