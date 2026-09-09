import csv
import json
from pathlib import Path
from collections import Counter


MATERIALS = Path("data/processed/ntpc_materials_enriched.csv")
PAIRS = Path("data/training/ntpc_candidate_pairs.csv")
OUTPUT = Path("data/training/ntpc_weak_labels.csv")


def load_materials():
    with MATERIALS.open(encoding="utf-8", newline="") as f:
        materials = list(csv.DictReader(f))

    for material in materials:
        material["parsed_specifications"] = json.loads(
            material.get("parsed_specifications") or "{}"
        )

    return materials


def has_value(value):
    return value is not None and value != ""


def critical_conflict(a, b):
    sa = a["parsed_specifications"]
    sb = b["parsed_specifications"]

    fields = [
        "material_grade",
        "pressure_rating",
        "voltage_class",
        "dimensions",
        "nominal_bore",
        "metric_thread",
    ]

    for field in fields:
        va = sa.get(field)
        vb = sb.get(field)

        if has_value(va) and has_value(vb) and va != vb:
            return field

    return None


def strong_spec_match(a, b):
    sa = a["parsed_specifications"]
    sb = b["parsed_specifications"]

    comparable = 0

    for field in [
        "material_grade",
        "pressure_rating",
        "voltage_class",
        "dimensions",
        "nominal_bore",
        "metric_thread",
    ]:
        va = sa.get(field)
        vb = sb.get(field)

        if has_value(va) and has_value(vb):
            comparable += 1

            if va != vb:
                return False

    return comparable >= 2


def generate_label(a, b):
    # Strongest negative evidence first.
    conflict = critical_conflict(a, b)

    if conflict:
        return "DIFFERENT", f"critical_spec_conflict:{conflict}"

    # Exact same description is useful weak evidence,
    # but not sufficient by itself to claim equivalence.
    desc_a = a["normalized_description"].strip()
    desc_b = b["normalized_description"].strip()

    if desc_a and desc_a == desc_b:
        if strong_spec_match(a, b):
            return "SAME", "exact_description_and_matching_specs"

        return "REVIEW", "exact_description_but_insufficient_specs"

    if strong_spec_match(a, b):
        return "SAME", "multiple_matching_structured_specs"

    return "REVIEW", "insufficient_evidence"


def main():
    materials = load_materials()

    labels = Counter()
    output_rows = []

    with PAIRS.open(encoding="utf-8", newline="") as f:
        for pair in csv.DictReader(f):
            source = materials[int(pair["source_index"])]
            target = materials[int(pair["target_index"])]

            label, reason = generate_label(source, target)

            labels[label] += 1

            output_rows.append(
                {
                    "source_index": pair["source_index"],
                    "target_index": pair["target_index"],
                    "source_material_code": source["material_code"],
                    "target_material_code": target["material_code"],
                    "weak_label": label,
                    "label_reason": reason,
                }
            )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "source_index",
                "target_index",
                "source_material_code",
                "target_material_code",
                "weak_label",
                "label_reason",
            ],
        )

        writer.writeheader()
        writer.writerows(output_rows)

    print("Weak-label results:")
    print(f"  SAME:      {labels['SAME']}")
    print(f"  DIFFERENT: {labels['DIFFERENT']}")
    print(f"  REVIEW:    {labels['REVIEW']}")
    print(f"\nSaved: {OUTPUT}")


if __name__ == "__main__":
    main()
