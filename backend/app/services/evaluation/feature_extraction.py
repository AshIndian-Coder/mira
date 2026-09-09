import csv
import json
from pathlib import Path

from app.services.matching.similarity import (
    text_similarity,
    semantic_similarity,
    specification_similarity,
    value_similarity,
)
from app.services.parsing.service import (
    parse_specifications,
)


INPUT_FILES = {
    "dev": Path(
        "data/evaluation/dataset_a_dev.csv"
    ),
    "heldout": Path(
        "data/evaluation/dataset_a_heldout.csv"
    ),
    "hard_negatives": Path(
        "data/evaluation/dataset_a_hard_negatives.csv"
    ),
}

OUTPUT_DIR = Path(
    "data/evaluation/features"
)


def load_pairs(path):
    with path.open(
        encoding="utf-8",
        newline="",
    ) as f:
        return list(csv.DictReader(f))


def build_material(description):
    specs = parse_specifications(
        description
    )

    return {
        "normalized_description": description,
        "parsed_specifications": specs,
        "material_grade": specs.get(
            "material_grade"
        ),
        "other_attributes": {},
    }


def extract_features(row):
    source = build_material(
        row["source_description"]
    )

    target = build_material(
        row["target_description"]
    )

    text_score = text_similarity(
        source["normalized_description"],
        target["normalized_description"],
    )

    semantic_score = semantic_similarity(
        source["normalized_description"],
        target["normalized_description"],
    )

    specification_score = specification_similarity(
        source["parsed_specifications"],
        target["parsed_specifications"],
        None,
    )

    grade_score = value_similarity(
        source["material_grade"],
        target["material_grade"],
    )

    # Dataset A currently has no other_attributes.
    other_score = 0.0

    return {
        "pair_id": row["pair_id"],
        "source_material_code": row[
            "source_material_code"
        ],
        "target_material_code": row[
            "target_material_code"
        ],
        "ground_truth": row["ground_truth"],
        "generation_type": row[
            "generation_type"
        ],
        "text_similarity": f"{text_score:.6f}",
        "semantic_similarity": f"{semantic_score:.6f}",
        "specification_similarity": (
            f"{specification_score:.6f}"
        ),
        "material_grade_similarity": (
            f"{grade_score:.6f}"
        ),
        "other_attributes_similarity": (
            f"{other_score:.6f}"
        ),
    }


def write_features(name, rows):
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output = (
        OUTPUT_DIR
        / f"{name}_features.csv"
    )

    fields = [
        "pair_id",
        "source_material_code",
        "target_material_code",
        "ground_truth",
        "generation_type",
        "text_similarity",
        "semantic_similarity",
        "specification_similarity",
        "material_grade_similarity",
        "other_attributes_similarity",
    ]

    with output.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fields,
        )

        writer.writeheader()
        writer.writerows(rows)

    return output


def main():
    for name, path in INPUT_FILES.items():
        pairs = load_pairs(path)

        features = [
            extract_features(row)
            for row in pairs
        ]

        output = write_features(
            name,
            features,
        )

        print(
            f"{name}: "
            f"{len(features)} pairs → {output}"
        )


if __name__ == "__main__":
    main()
