import csv
import json
from pathlib import Path

from app.services.matching.scoring import calculate_match_score
from app.services.matching.critical_gates import (
    evaluate_critical_gates,
)


INPUT = Path(
    "data/processed/cross_cpse_candidates.csv"
)

OUTPUT = Path(
    "data/processed/cross_cpse_scored.csv"
)


def load_materials():
    path = Path(
        "data/processed/materials_all_enriched.csv"
    )

    materials = {}

    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:

        for row in csv.DictReader(file):

            key = (
                row["cpse"],
                row["material_code"],
            )

            materials[key] = row

    return materials


def prepare_material(row):
    parsed = row.get(
        "parsed_specifications",
        "",
    )

    try:
        parsed_specs = (
            json.loads(parsed)
            if parsed
            else {}
        )
    except json.JSONDecodeError:
        parsed_specs = {}

    return {
        **row,
        "parsed_specifications": parsed_specs,
        "dimensions": (
            json.loads(row["dimensions"])
            if row.get("dimensions")
            else None
        ),
        "other_attributes": (
            json.loads(row["other_attributes"])
            if row.get("other_attributes")
            else {}
        ),
    }


def main():

    materials = load_materials()

    with INPUT.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:
        candidates = list(csv.DictReader(file))

    results = []

    for candidate in candidates:

        source_key = (
            candidate["source_cpse"],
            candidate["source_material_code"],
        )

        target_key = (
            candidate["target_cpse"],
            candidate["target_material_code"],
        )

        source = prepare_material(
            materials[source_key]
        )

        target = prepare_material(
            materials[target_key]
        )

        scores = calculate_match_score(
            source,
            target,
        )

        checks = evaluate_critical_gates(
            source,
            target,
        )

        has_unknown = any(
            check["status"] == "UNKNOWN"
            for check in checks
        )

        has_conflict = any(
            check["status"] == "CONFLICT"
            for check in checks
        )

        if (
            scores["final_score"] >= 0.85
            and checks
            and all(
                check["status"] == "PASS"
                for check in checks
            )
        ):
            decision = "HIGH_CONFIDENCE"

        elif has_unknown or has_conflict:
            decision = "REVIEW"

        elif scores["final_score"] > 0.45:
            decision = "REVIEW"

        else:
            decision = "DIFFERENT"

        results.append({
            **candidate,
            **scores,
            "critical_checks": json.dumps(
                checks,
                ensure_ascii=False,
            ),
            "decision": decision,
        })

    fieldnames = list(results[0].keys())

    with OUTPUT.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(results)

    counts = {}

    for row in results:
        decision = row["decision"]
        counts[decision] = (
            counts.get(decision, 0) + 1
        )

    print(f"Candidates scored: {len(results)}")

    for decision, count in sorted(counts.items()):
        print(
            f"{decision}: {count}"
        )

    print(
        f"\nSaved: {OUTPUT}"
    )


if __name__ == "__main__":
    main()
