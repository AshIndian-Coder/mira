from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = next((candidate for candidate in [BASE_DIR, *BASE_DIR.parents] if (candidate / "backend").is_dir()), BASE_DIR)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.ml_pipeline.training_utils.dataset import (
    ALLOWED_HN_TYPES,
    build_triplets_from_pairs_df,
    check_tmk_leakage,
    load_pairs_dataframe,
)

DEFAULT_BASE_DATASET = BASE_DIR / "train_data" / "training" / "Training_Pairs_MIRA_FINAL.csv"
DEFAULT_OUTPUT = BASE_DIR / "results" / "epoch2" / "Training_Triplets_MIRA_ALL_HN.csv"
DEFAULT_SUMMARY = BASE_DIR / "results" / "epoch2" / "epoch2_triplet_build_all_hn_summary.json"
DEFAULT_MAX_POSITIVES = 4
DEFAULT_MIN_TRIPLETS = 50_000
DEFAULT_MIN_UNIQUE_HNS = 10_000
DEFAULT_SEED = 42
OUTPUT_COLUMNS = [
    "triplet_id",
    "source_pair_id",
    "anchor",
    "positive",
    "hard_negative",
    "tmk",
    "hn_type",
    "hard_negative_field",
    "epoch1_similarity",
    "split",
    "orientation",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_csv_write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    try:
        df.to_csv(temp, index=False)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def atomic_json_write(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    try:
        temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False, default=str), encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def validate_triplets(
    triplets: pd.DataFrame,
    *,
    expected_source_hns: int,
    min_triplets: int,
    min_unique_hns: int,
) -> dict[str, Any]:
    missing = set(OUTPUT_COLUMNS) - set(triplets.columns)
    if missing:
        raise ValueError("Triplet output is missing columns: " + ", ".join(sorted(missing)))
    if triplets.empty:
        raise ValueError("Triplet output is empty.")

    result = triplets[OUTPUT_COLUMNS].copy()
    text_columns = [column for column in OUTPUT_COLUMNS if column != "epoch1_similarity"]
    for column in text_columns:
        result[column] = result[column].fillna("").astype(str).str.strip()
    result["epoch1_similarity"] = pd.to_numeric(result["epoch1_similarity"], errors="coerce")

    for column in ("triplet_id", "source_pair_id", "anchor", "positive", "hard_negative", "tmk", "hn_type", "hard_negative_field"):
        if result[column].eq("").any():
            raise ValueError(f"Triplet output contains empty {column} values.")
    if not result["split"].eq("train").all():
        raise ValueError("Triplet output contains non-train rows.")
    if not result["hn_type"].isin(ALLOWED_HN_TYPES).all():
        raise ValueError("Triplet output contains unsupported HN types.")
    if result["triplet_id"].duplicated().any():
        raise ValueError("Triplet IDs are not unique.")
    if result["source_pair_id"].nunique() > expected_source_hns:
        raise ValueError("Triplet output references more source HNs than exist in TRAIN.")
    if result.duplicated(["anchor", "positive", "hard_negative", "tmk", "hn_type"]).any():
        raise ValueError("Triplet output contains duplicate semantic triplets.")
    if ((result["anchor"] == result["positive"]) | (result["anchor"] == result["hard_negative"]) | (result["positive"] == result["hard_negative"])).any():
        raise ValueError("Triplet output contains identical triplet members.")

    values = result["epoch1_similarity"].dropna()
    if not values.empty and ((values < -1.0) | (values > 1.0)).any():
        raise ValueError("Triplet output contains out-of-range epoch1_similarity values.")

    actual_hns = int(result["source_pair_id"].nunique())
    actual_rows = int(len(result))
    checks = {
        "source_hn_population_present": expected_source_hns > 0,
        "triplet_count": actual_rows >= min_triplets,
        "unique_source_hn_count": actual_hns >= min_unique_hns,
        "type_coverage": bool(set(result["hn_type"].unique()).issubset(ALLOWED_HN_TYPES)),
    }
    if not all(checks.values()):
        raise RuntimeError("Triplet viability checks failed: " + json.dumps(checks, sort_keys=True))
    return {"rows": actual_rows, "unique_source_hns": actual_hns, "checks": checks}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build triplets from every TRAIN hard-negative relationship with a valid clean-TMK positive pool.")
    parser.add_argument("--base-dataset", type=Path, default=DEFAULT_BASE_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--max-positives-per-hn", type=int, default=DEFAULT_MAX_POSITIVES)
    parser.add_argument("--min-triplets", type=int, default=DEFAULT_MIN_TRIPLETS)
    parser.add_argument("--min-unique-hns", type=int, default=DEFAULT_MIN_UNIQUE_HNS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.max_positives_per_hn < 1 or args.min_triplets < 1 or args.min_unique_hns < 1 or args.seed < 0:
        raise ValueError("Numeric arguments must be positive, except seed which may be zero.")

    base_path = args.base_dataset.resolve()
    base_df = load_pairs_dataframe(base_path, require_unique_pair_ids=True)
    leakage = check_tmk_leakage(base_df)
    if leakage.get("status") != "PASS":
        raise RuntimeError(f"TMK split-leakage gate failed: {leakage}")

    train_df = base_df[base_df["split"] == "train"]
    train_hn = train_df[
        (train_df["label"] == 0) & train_df["pair_type"].isin(ALLOWED_HN_TYPES)
    ].copy()
    source_hn_rows = int(len(train_hn))
    if source_hn_rows == 0:
        raise RuntimeError("No TRAIN hard negatives were found.")

    triplets, diagnostics = build_triplets_from_pairs_df(
        base_df,
        max_positives_per_hn=args.max_positives_per_hn,
        seed=args.seed,
        return_diagnostics=True,
    )
    triplets = triplets[OUTPUT_COLUMNS].copy()
    validation = validate_triplets(
        triplets,
        expected_source_hns=source_hn_rows,
        min_triplets=args.min_triplets,
        min_unique_hns=args.min_unique_hns,
    )

    atomic_csv_write(triplets, args.output.resolve())
    reloaded = pd.read_csv(args.output.resolve(), low_memory=False)
    validate_triplets(
        reloaded,
        expected_source_hns=source_hn_rows,
        min_triplets=args.min_triplets,
        min_unique_hns=args.min_unique_hns,
    )

    summary = {
        "validation": "PASS",
        "source_mode": "base_train_all_hard_negatives",
        "base_dataset": str(base_path),
        "base_dataset_sha256": sha256_file(base_path),
        "output": str(args.output.resolve()),
        "output_sha256": sha256_file(args.output.resolve()),
        "base_rows": int(len(base_df)),
        "base_train_rows": int(len(train_df)),
        "source_hn_rows": source_hn_rows,
        "source_hn_by_type": {str(k): int(v) for k, v in train_hn["pair_type"].value_counts().sort_index().items()},
        "triplet_rows": validation["rows"],
        "unique_source_hns_used": validation["unique_source_hns"],
        "pairwise_only_hns_after_triplet_dedup": int(source_hn_rows - validation["unique_source_hns"]),
        "positive_train_rows": int((train_df["label"] == 1).sum()),
        "max_positives_per_hn": int(args.max_positives_per_hn),
        "seed": int(args.seed),
        "tmk_leakage": leakage,
        "diagnostics": diagnostics,
        "checks": validation["checks"],
    }
    atomic_json_write(summary, args.summary.resolve())

    print("=" * 82)
    print("MIRA EPOCH-2 TRIPLET BUILD: PASS")
    print("=" * 82)
    print(f"TRAIN pairs:                         {len(train_df):,}")
    print(f"TRAIN positives:                     {(train_df['label'] == 1).sum():,}")
    print(f"TRAIN hard negatives:                {source_hn_rows:,}")
    for hn_type in sorted(ALLOWED_HN_TYPES):
        print(f"{hn_type}:                         {int((train_hn['pair_type'] == hn_type).sum()):,}")
    print(f"HNs with >=1 triplet:                {validation['unique_source_hns']:,}")
    print(f"Pairwise-only HNs:                   {source_hn_rows - validation['unique_source_hns']:,}")
    print(f"Generated unique triplets:           {validation['rows']:,}")
    print(f"Triplets by type:                    {diagnostics['hn_type_counts']}")
    print(f"Triplets by field:                   {diagnostics['field_counts']}")
    print(f"Output:                              {args.output.resolve()}")
    print(f"Summary:                             {args.summary.resolve()}")
    print("=" * 82)


if __name__ == "__main__":
    main()
