from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = next((candidate for candidate in [BASE_DIR, *BASE_DIR.parents] if (candidate / "backend").is_dir()), BASE_DIR)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.ml_pipeline.training_utils.dataset import ALLOWED_HN_TYPES, check_tmk_leakage, load_pairs_dataframe

DEFAULT_DATA_PATH = BASE_DIR / "train_data" / "training" / "Training_Pairs_MIRA_FINAL.csv"
DEFAULT_TRIPLET_SUMMARY = BASE_DIR / "results" / "epoch2" / "epoch2_triplet_build_all_hn_summary.json"
DEFAULT_OUTPUT = BASE_DIR / "results" / "epoch2" / "all_data_audit_summary.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit MIRA TRAIN/DEV/HELDOUT data and the all-HN triplet build.")
    parser.add_argument("--data-path", type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument("--triplet-summary", type=Path, default=DEFAULT_TRIPLET_SUMMARY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = load_pairs_dataframe(args.data_path.resolve(), require_unique_pair_ids=True)
    leakage = check_tmk_leakage(df)
    train = df[df["split"] == "train"]
    hn = train[(train["label"] == 0) & train["pair_type"].isin(ALLOWED_HN_TYPES)]
    result = {
        "dataset_rows": int(len(df)),
        "train_rows": int(len(train)),
        "dev_rows": int((df["split"] == "dev").sum()),
        "heldout_rows": int((df["split"] == "heldout").sum()),
        "positive_train_rows": int((train["label"] == 1).sum()),
        "negative_train_rows": int((train["label"] == 0).sum()),
        "hard_negative_train_rows": int(len(hn)),
        "hard_negative_by_type": {str(k): int(v) for k, v in hn["pair_type"].value_counts().sort_index().items()},
        "hard_negative_by_field": {str(k): int(v) for k, v in hn["hard_negative_field"].fillna("UNKNOWN").astype(str).str.strip().replace("", "UNKNOWN").value_counts().sort_index().items()} if "hard_negative_field" in hn.columns else {},
        "tmk_leakage": leakage,
    }
    if args.triplet_summary.resolve().is_file():
        summary = json.loads(args.triplet_summary.resolve().read_text(encoding="utf-8"))
        result["triplet_build"] = {
            "validation": summary.get("validation"),
            "source_mode": summary.get("source_mode"),
            "source_hn_rows": summary.get("source_hn_rows"),
            "triplet_rows": summary.get("triplet_rows"),
            "unique_source_hns_used": summary.get("unique_source_hns_used"),
            "pairwise_only_hns_after_triplet_dedup": summary.get("pairwise_only_hns_after_triplet_dedup"),
            "hn_type_counts": summary.get("diagnostics", {}).get("hn_type_counts", {}),
            "orientation_counts": summary.get("diagnostics", {}).get("post_dedup_orientation_counts", {}),
        }
    if leakage.get("status") != "PASS":
        raise RuntimeError(f"TMK leakage detected: {leakage}")
    if len(hn) == 0:
        raise RuntimeError("No TRAIN hard negatives found")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=" * 82)
    print("MIRA ALL-DATA AUDIT: PASS")
    print("=" * 82)
    print(f"Dataset rows:                 {len(df):,}")
    print(f"TRAIN rows:                   {len(train):,}")
    print(f"TRAIN positives:              {(train['label'] == 1).sum():,}")
    print(f"TRAIN hard negatives:         {len(hn):,}")
    print(f"HN types:                     {hn['pair_type'].value_counts().to_dict()}")
    print(f"TMK leakage:                  {leakage['status']}")
    if "triplet_build" in result:
        trip = result["triplet_build"]
        print(f"Triplet build validation:     {trip['validation']}")
        print(f"Triplet rows:                 {trip['triplet_rows']}")
        print(f"Unique HNs with triplets:     {trip['unique_source_hns_used']}")
        print(f"Pairwise-only HNs:            {trip['pairwise_only_hns_after_triplet_dedup']}")
    print(f"Output:                       {output}")
    print("=" * 82)


if __name__ == "__main__":
    main()
