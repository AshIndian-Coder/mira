from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = next((candidate for candidate in [BASE_DIR, *BASE_DIR.parents] if (candidate / "backend").is_dir()), BASE_DIR)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.ml_pipeline.training_utils.dataset import ALLOWED_HN_TYPES, build_triplets_from_pairs_df, check_tmk_leakage, load_pairs_dataframe
from backend.app.ml_pipeline.training_utils.loss import MIRAHardNegativeLoss, MIRATripletHardNegativeLoss

CURRENT_DATASET_SHA256 = "fb01ca6f3aa349c2168251d6a38537d3043b57a0655f2127f1cc6b2c15584126"
CURRENT_DATASET_ROWS = 119_932
CURRENT_TRAIN_ROWS = 109_420
CURRENT_TRAIN_HNS = 26_235
CURRENT_CORRUPT_HNS = 17_503
CURRENT_SIBLING_HNS = 8_732
CURRENT_TRIPLET_ROWS = 74_951
CURRENT_UNIQUE_TRIPLET_HNS = 18_217
CURRENT_CORRUPT_TRIPLETS = 69_920


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Regression tests for the MIRA all-data triplet pipeline.")
    parser.add_argument("--data-path", type=Path, default=None)
    parser.add_argument("--skip-current-snapshot", action="store_true")
    return parser.parse_args()


def test_data(data_path: Path, snapshot: bool) -> pd.DataFrame:
    df = load_pairs_dataframe(data_path, require_unique_pair_ids=True)
    assert check_tmk_leakage(df)["status"] == "PASS"
    train = df[df["split"] == "train"]
    hns = train[(train["label"] == 0) & train["pair_type"].isin(ALLOWED_HN_TYPES)]
    assert len(hns) > 0
    assert len({"HN_CORRUPT", "HN_SIBLING"} & set(hns["pair_type"])) == 2

    if snapshot:
        assert sha256_file(data_path) == CURRENT_DATASET_SHA256
        assert len(df) == CURRENT_DATASET_ROWS
        assert len(train) == CURRENT_TRAIN_ROWS
        assert len(hns) == CURRENT_TRAIN_HNS
        assert int((hns["pair_type"] == "HN_CORRUPT").sum()) == CURRENT_CORRUPT_HNS
        assert int((hns["pair_type"] == "HN_SIBLING").sum()) == CURRENT_SIBLING_HNS
    return df


def test_triplets(df: pd.DataFrame, snapshot: bool) -> None:
    triplets, diagnostics = build_triplets_from_pairs_df(df, max_positives_per_hn=4, seed=42, return_diagnostics=True)
    assert len(triplets) > 0
    assert triplets["source_pair_id"].nunique() > 0
    assert not triplets.duplicated(["anchor", "positive", "hard_negative", "tmk", "hn_type"]).any()
    assert not ((triplets["anchor"] == triplets["positive"]) | (triplets["anchor"] == triplets["hard_negative"]) | (triplets["positive"] == triplets["hard_negative"])).any()
    assert triplets["hn_type"].isin(ALLOWED_HN_TYPES).all()
    assert triplets["split"].eq("train").all()
    assert diagnostics["source_hn_rows"] == int((((df["split"] == "train") & (df["label"] == 0) & df["pair_type"].isin(ALLOWED_HN_TYPES))).sum())

    if snapshot:
        assert len(triplets) == CURRENT_TRIPLET_ROWS
        assert int(triplets["source_pair_id"].nunique()) == CURRENT_UNIQUE_TRIPLET_HNS
        assert int((triplets["hn_type"] == "HN_CORRUPT").sum()) == CURRENT_CORRUPT_TRIPLETS
        assert int(diagnostics["generated_by_orientation"]["corrupt"]) == 70_012
        assert int(triplets["orientation"].value_counts()["sibling_a"]) == 2_499
        assert int(triplets["orientation"].value_counts()["sibling_b"]) == 2_532


def test_losses() -> None:
    a = torch.tensor([[1.0, 0.0], [1.0, 0.0]], dtype=torch.float32)
    p = torch.tensor([[1.0, 0.0], [0.99, 0.1]], dtype=torch.float32)
    n = torch.tensor([[0.0, 1.0], [0.8, 0.6]], dtype=torch.float32)
    pair = MIRAHardNegativeLoss()
    labels = torch.tensor([1.0, 0.0])
    mask = torch.tensor([False, True])
    pair_loss = pair(a, p, labels, mask)
    triplet_loss = MIRATripletHardNegativeLoss()(a, p, n)
    assert torch.isfinite(pair_loss).item()
    assert torch.isfinite(triplet_loss).item()
    assert pair_loss.item() >= 0.0
    assert triplet_loss.item() >= 0.0


def main() -> None:
    args = parse_args()
    data_path = args.data_path.resolve() if args.data_path else Path(__file__).resolve().parent / "train_data" / "training" / "Training_Pairs_MIRA_FINAL.csv"
    df = test_data(data_path, snapshot=not args.skip_current_snapshot)
    test_triplets(df, snapshot=not args.skip_current_snapshot)
    test_losses()
    print("MIRA ALL-DATA PIPELINE TEST: PASS")
    print(f"dataset_rows={len(df):,}")
    print(f"train_hns={int((((df['split'] == 'train') & (df['label'] == 0) & df['pair_type'].isin(ALLOWED_HN_TYPES))).sum()):,}")


if __name__ == "__main__":
    main()
