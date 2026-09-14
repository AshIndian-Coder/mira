import csv
import json
from collections import defaultdict
from pathlib import Path

from app.services.blocking.service import (
    MaterialForBlocking,
    generate_block_keys,
)


INPUT = Path("data/processed/ntpc_materials_enriched.csv")
OUTPUT = Path("data/training/ntpc_candidate_pairs.csv")


def load_materials(csv_path: str | Path) -> list[dict]:
    with Path(csv_path).open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:
        records = []

        for row in csv.DictReader(file):
            row["parsed_specifications"] = json.loads(
                row.get("parsed_specifications") or "{}"
            )

            row["dimensions"] = json.loads(
                row.get("dimensions") or "null"
            )

            records.append(row)

        return records


def generate_candidate_pairs(materials: list[dict]) -> list[tuple[int, int]]:
    blocks: dict[str, list[int]] = defaultdict(list)

    for index, material in enumerate(materials):
        specs = material.get("parsed_specifications") or {}

        blocking_material = MaterialForBlocking(
            id=index,
            category=material.get("category"),
            normalized_description=material.get(
                "normalized_description",
                "",
            ),
            material_grade=(
                material.get("material_grade")
                or specs.get("material_grade")
            ),
            manufacturer_part_number=material.get(
                "manufacturer_part_number"
            ),
        )

        for key in generate_block_keys(blocking_material):
            blocks[key].append(index)

    pairs: set[tuple[int, int]] = set()

    for members in blocks.values():
        if len(members) < 2:
            continue

        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                left = members[i]
                right = members[j]

                pairs.add((min(left, right), max(left, right)))

    return sorted(pairs)


def export_pairs(
    materials: list[dict],
    pairs: list[tuple[int, int]],
    output_path: str | Path,
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.writer(file)

        writer.writerow(
            [
                "source_index",
                "target_index",
                "source_material_code",
                "target_material_code",
            ]
        )

        for source_index, target_index in pairs:
            writer.writerow(
                [
                    source_index,
                    target_index,
                    materials[source_index]["material_code"],
                    materials[target_index]["material_code"],
                ]
            )


if __name__ == "__main__":
    materials = load_materials(INPUT)

    print(f"Materials loaded: {len(materials)}")

    pairs = generate_candidate_pairs(materials)

    print(f"Candidate pairs generated: {len(pairs)}")

    export_pairs(materials, pairs, OUTPUT)

    print(f"Saved: {OUTPUT}")
