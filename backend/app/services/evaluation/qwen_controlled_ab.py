"""
Final Controlled Qwen A/B Experiment for MIRA Track 1.

Evaluates three candidate weight arms using existing Qwen INT8 feature matrices
and exact MIRA decision/gate logic:

- Arm A (CONTROL):   [0.200, 0.200, 0.350, 0.150, 0.100] (Current Production Prior)
- Arm B (CAND_0804): [0.200, 0.400, 0.250, 0.100, 0.050] (Discrimination Champion)
- Arm C (CAND_0678): [0.175, 0.400, 0.250, 0.125, 0.050] (Safety & Workload Champion)

Datasets:
- DEV: 5,228 pairs (3,661 positive, 1,567 negative)
- HELDOUT: 5,284 pairs (3,804 positive, 1,480 negative)
- Hard Negatives: 300 engineering pairs across 5 conflict categories
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, confusion_matrix, precision_recall_fscore_support, roc_auc_score

FEATURE_NAMES = [
    "text_similarity",
    "semantic_similarity",
    "specification_similarity",
    "material_grade_similarity",
    "other_attributes_similarity",
]

ARMS = {
    "Arm_A_CONTROL": {
        "name": "Arm A — CONTROL (Production Prior)",
        "arm_id": "Arm_A_CONTROL",
        "weights": np.array([0.200, 0.200, 0.350, 0.150, 0.100], dtype=np.float64),
        "description": "Production prior baseline with fine-tuned Qwen INT8 semantic features",
    },
    "Arm_B_CAND_0804": {
        "name": "Arm B — CAND_0804 (Discrimination Champion)",
        "arm_id": "Arm_B_CAND_0804",
        "weights": np.array([0.200, 0.400, 0.250, 0.100, 0.050], dtype=np.float64),
        "description": "Highest DEV/HELDOUT discrimination and positive pair recovery",
    },
    "Arm_C_CAND_0678": {
        "name": "Arm C — CAND_0678 (Safety & Workload Champion)",
        "arm_id": "Arm_C_CAND_0678",
        "weights": np.array([0.175, 0.400, 0.250, 0.125, 0.050], dtype=np.float64),
        "description": "Lowest hard-negative mean score and highest auto-rejection rate",
    },
}

HIGH_CONFIDENCE_THRESHOLD = 0.85
DIFFERENT_THRESHOLD = 0.45


def evaluate_decisions_vectorized(
    scores: np.ndarray,
    has_conflict: np.ndarray,
    has_unknown: np.ndarray,
    gates_pass: np.ndarray,
) -> Dict[str, Any]:
    """Execute vectorized production decision simulation adhering to classifier.py logic."""
    is_hc = (scores >= HIGH_CONFIDENCE_THRESHOLD) & gates_pass
    is_rev = (~is_hc) & (has_conflict | has_unknown | (scores > DIFFERENT_THRESHOLD))
    is_diff = (~is_hc) & (~is_rev)

    decisions = np.full(len(scores), "DIFFERENT", dtype=object)
    decisions[is_hc] = "HIGH_CONFIDENCE"
    decisions[is_rev] = "REVIEW"

    return {
        "decisions": decisions,
        "HIGH_CONFIDENCE": int(np.sum(is_hc)),
        "REVIEW": int(np.sum(is_rev)),
        "DIFFERENT": int(np.sum(is_diff)),
        "is_hc": is_hc,
        "is_rev": is_rev,
        "is_diff": is_diff,
    }


def compute_confusion_matrix_at_50(y_true: np.ndarray, scores: np.ndarray) -> Dict[str, Any]:
    """Compute binary classification metrics and confusion matrix at threshold 0.50."""
    y_pred = (scores >= 0.50).astype(int)
    has_both = len(np.unique(y_true)) > 1

    if has_both:
        tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
        prec, rec, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)
        acc = float((tp + tn) / len(y_true))
    else:
        # All one class (e.g., all negatives in HN dataset)
        tp = int(np.sum((y_true == 1) & (y_pred == 1)))
        fp = int(np.sum((y_true == 0) & (y_pred == 1)))
        tn = int(np.sum((y_true == 0) & (y_pred == 0)))
        fn = int(np.sum((y_true == 1) & (y_pred == 0)))
        prec = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        rec = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0
        f1 = float(2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
        acc = float((tp + tn) / len(y_true))

    return {
        "threshold": 0.50,
        "true_positives": int(tp),
        "false_positives": int(fp),
        "true_negatives": int(tn),
        "false_negatives": int(fn),
        "precision": round(float(prec), 4),
        "recall": round(float(rec), 4),
        "f1_score": round(float(f1), 4),
        "accuracy": round(float(acc), 4),
    }


def evaluate_dataset(
    X: np.ndarray,
    y: np.ndarray,
    has_conflict: np.ndarray,
    has_unknown: np.ndarray,
    gates_pass: np.ndarray,
    weights: np.ndarray,
) -> Dict[str, Any]:
    """Calculate discrimination metrics, confusion matrix, and production decisions."""
    scores = X @ weights
    has_both = len(np.unique(y)) > 1

    roc_auc = float(roc_auc_score(y, scores)) if has_both else None
    pr_auc = float(average_precision_score(y, scores)) if has_both else None

    cm_50 = compute_confusion_matrix_at_50(y, scores)

    pos_mask = (y == 1)
    neg_mask = (y == 0)

    pos_scores = scores[pos_mask] if pos_mask.any() else np.array([])
    neg_scores = scores[neg_mask] if neg_mask.any() else np.array([])

    pos_mean = float(np.mean(pos_scores)) if len(pos_scores) else None
    pos_med = float(np.median(pos_scores)) if len(pos_scores) else None
    neg_mean = float(np.mean(neg_scores)) if len(neg_scores) else None
    neg_med = float(np.median(neg_scores)) if len(neg_scores) else None
    sep = float(pos_mean - neg_mean) if (pos_mean is not None and neg_mean is not None) else None

    dec_res = evaluate_decisions_vectorized(scores, has_conflict, has_unknown, gates_pass)
    is_hc = dec_res["is_hc"]
    is_rev = dec_res["is_rev"]
    is_diff = dec_res["is_diff"]

    pos_diff = int(np.sum(is_diff & pos_mask))
    pos_rev = int(np.sum(is_rev & pos_mask))
    pos_hc = int(np.sum(is_hc & pos_mask))

    neg_diff = int(np.sum(is_diff & neg_mask))
    neg_rev = int(np.sum(is_rev & neg_mask))
    neg_hc = int(np.sum(is_hc & neg_mask))

    return {
        "roc_auc": round(roc_auc, 4) if roc_auc is not None else None,
        "pr_auc": round(pr_auc, 4) if pr_auc is not None else None,
        "score_separation": round(sep, 4) if sep is not None else None,
        "pos_mean": round(pos_mean, 4) if pos_mean is not None else None,
        "pos_median": round(pos_med, 4) if pos_med is not None else None,
        "neg_mean": round(neg_mean, 4) if neg_mean is not None else None,
        "neg_median": round(neg_med, 4) if neg_med is not None else None,
        "confusion_matrix_at_0_50": cm_50,
        "overall_decisions": {
            "HIGH_CONFIDENCE": dec_res["HIGH_CONFIDENCE"],
            "REVIEW": dec_res["REVIEW"],
            "DIFFERENT": dec_res["DIFFERENT"],
        },
        "pos_decisions": {
            "HIGH_CONFIDENCE": pos_hc,
            "REVIEW": pos_rev,
            "DIFFERENT": pos_diff,
        },
        "neg_decisions": {
            "HIGH_CONFIDENCE": neg_hc,
            "REVIEW": neg_rev,
            "DIFFERENT": neg_diff,
        },
        "positive_pairs_classified_different": pos_diff,
        "negative_pairs_classified_high_confidence": neg_hc,
    }


def evaluate_hard_negatives(
    X_hn: np.ndarray,
    df_hn: pd.DataFrame,
    has_conflict: np.ndarray,
    has_unknown: np.ndarray,
    gates_pass: np.ndarray,
    weights: np.ndarray,
) -> Dict[str, Any]:
    """Calculate detailed safety metrics, decision distribution, and per-field breakdown on 300 HNs."""
    scores = X_hn @ weights
    dec_res = evaluate_decisions_vectorized(scores, has_conflict, has_unknown, gates_pass)

    fields = ["dimensions", "metric_thread", "nominal_bore", "pressure_rating", "voltage_class"]
    field_stats = {}
    for f in fields:
        grp = df_hn[df_hn["conflicting_fields"] == f]
        if len(grp):
            grp_idx = grp.index.to_numpy()
            grp_scores = scores[grp_idx]
            grp_dec = dec_res["decisions"][grp_idx]
            field_stats[f] = {
                "count": len(grp),
                "mean_score": round(float(np.mean(grp_scores)), 4),
                "median_score": round(float(np.median(grp_scores)), 4),
                "max_score": round(float(np.max(grp_scores)), 4),
                "count_ge_0_50": int(np.sum(grp_scores >= 0.50)),
                "count_ge_0_80": int(np.sum(grp_scores >= 0.80)),
                "count_ge_0_85": int(np.sum(grp_scores >= 0.85)),
                "DIFFERENT": int(np.sum(grp_dec == "DIFFERENT")),
                "REVIEW": int(np.sum(grp_dec == "REVIEW")),
                "HIGH_CONFIDENCE": int(np.sum(grp_dec == "HIGH_CONFIDENCE")),
            }

    return {
        "mean_score": round(float(np.mean(scores)), 4),
        "median_score": round(float(np.median(scores)), 4),
        "max_score": round(float(np.max(scores)), 4),
        "count_ge_0_50": int(np.sum(scores >= 0.50)),
        "count_ge_0_80": int(np.sum(scores >= 0.80)),
        "count_ge_0_85": int(np.sum(scores >= 0.85)),
        "decision_distribution": {
            "HIGH_CONFIDENCE": dec_res["HIGH_CONFIDENCE"],
            "REVIEW": dec_res["REVIEW"],
            "DIFFERENT": dec_res["DIFFERENT"],
        },
        "per_field_breakdown": field_stats,
    }


def resolve_data_paths() -> Tuple[Path, Path, Path]:
    """Find the valid paths for DEV, HELDOUT, and HN datasets."""
    candidates = [
        (
            Path("/home/shikhar/mira-model-test/hybrid_ab_results/Qwen_INT8_dev_pairs.csv"),
            Path("/home/shikhar/mira-model-test/hybrid_ab_results/Qwen_INT8_heldout_pairs.csv"),
            Path("/home/shikhar/mira-model-test/hybrid_ab_results/Qwen_INT8_hn300_pairs.csv"),
        ),
        (
            Path("data/evaluation/features/dev_features.csv"),
            Path("data/evaluation/features/heldout_features.csv"),
            Path("data/evaluation/features/hard_negatives_features.csv"),
        ),
    ]
    for dev_p, held_p, hn_p in candidates:
        if dev_p.exists() and held_p.exists() and hn_p.exists():
            return dev_p, held_p, hn_p

    raise FileNotFoundError("Could not locate required Qwen feature CSV files.")


def run_qwen_controlled_ab(
    output_report_path: Optional[str] = "data/evaluation/qwen_controlled_ab_report.json",
    output_csv_path: Optional[str] = "data/evaluation/qwen_controlled_ab_summary.csv",
) -> Dict[str, Any]:
    """Run the complete controlled Qwen A/B experiment across Arms A, B, and C."""
    print("=== STARTING FINAL CONTROLLED QWEN A/B EXPERIMENT ===")
    dev_path, held_path, hn_path = resolve_data_paths()
    print(f"Loading feature datasets:\n  DEV: {dev_path}\n  HELDOUT: {held_path}\n  HN: {hn_path}")

    dev_df = pd.read_csv(dev_path)
    held_df = pd.read_csv(held_path)
    hn_df = pd.read_csv(hn_path)

    # Extract feature matrices and critical checks
    X_dev = dev_df[FEATURE_NAMES].to_numpy(dtype=np.float64)
    y_dev = dev_df["label"].to_numpy(dtype=np.int64)
    dev_conflict = dev_df["critical_has_conflict"].to_numpy(dtype=bool)
    dev_unknown = dev_df["critical_has_unknown"].to_numpy(dtype=bool)
    dev_pass = dev_df["critical_all_pass"].to_numpy(dtype=bool)

    X_held = held_df[FEATURE_NAMES].to_numpy(dtype=np.float64)
    y_held = held_df["label"].to_numpy(dtype=np.int64)
    held_conflict = held_df["critical_has_conflict"].to_numpy(dtype=bool)
    held_unknown = held_df["critical_has_unknown"].to_numpy(dtype=bool)
    held_pass = held_df["critical_all_pass"].to_numpy(dtype=bool)

    X_hn = hn_df[FEATURE_NAMES].to_numpy(dtype=np.float64)
    y_hn = hn_df["label"].to_numpy(dtype=np.int64)
    hn_conflict = hn_df["critical_has_conflict"].to_numpy(dtype=bool)
    hn_unknown = hn_df["critical_has_unknown"].to_numpy(dtype=bool)
    hn_pass = hn_df["critical_all_pass"].to_numpy(dtype=bool)

    # Invariant verification
    for arm_id, arm_info in ARMS.items():
        w = arm_info["weights"]
        assert len(w) == 5, f"{arm_id} must have 5 weights"
        assert np.all(w >= 0.0), f"{arm_id} must have non-negative weights"
        assert abs(np.sum(w) - 1.0) < 1e-6, f"{arm_id} weights must sum to 1.0"

    results = {}
    csv_rows = []

    for arm_id, arm_info in ARMS.items():
        w = arm_info["weights"]
        print(f"\nEvaluating {arm_info['name']} -> weights: {w.tolist()}...")

        dev_res = evaluate_dataset(X_dev, y_dev, dev_conflict, dev_unknown, dev_pass, w)
        held_res = evaluate_dataset(X_held, y_held, held_conflict, held_unknown, held_pass, w)
        hn_res = evaluate_hard_negatives(X_hn, hn_df, hn_conflict, hn_unknown, hn_pass, w)

        # Invariant check: zero HN receiving HIGH_CONFIDENCE
        assert hn_res["decision_distribution"]["HIGH_CONFIDENCE"] == 0, f"{arm_id} produced HN HIGH_CONFIDENCE!"

        arm_record = {
            "arm_id": arm_id,
            "name": arm_info["name"],
            "description": arm_info["description"],
            "weights": {
                "text_similarity": float(w[0]),
                "semantic_similarity": float(w[1]),
                "specification_similarity": float(w[2]),
                "material_grade_similarity": float(w[3]),
                "other_attributes_similarity": float(w[4]),
                "weight_vector": w.tolist(),
            },
            "DEV": dev_res,
            "HELDOUT": held_res,
            "HARD_NEGATIVES_300": hn_res,
        }
        results[arm_id] = arm_record

        # Construct CSV row
        csv_rows.append({
            "arm_id": arm_id,
            "arm_name": arm_info["name"],
            "w_text": float(w[0]),
            "w_semantic": float(w[1]),
            "w_spec": float(w[2]),
            "w_grade": float(w[3]),
            "w_other": float(w[4]),
            # DEV
            "dev_roc_auc": dev_res["roc_auc"],
            "dev_pr_auc": dev_res["pr_auc"],
            "dev_separation": dev_res["score_separation"],
            "dev_pos_mean": dev_res["pos_mean"],
            "dev_neg_mean": dev_res["neg_mean"],
            "dev_f1_50": dev_res["confusion_matrix_at_0_50"]["f1_score"],
            "dev_acc_50": dev_res["confusion_matrix_at_0_50"]["accuracy"],
            "dev_tp_50": dev_res["confusion_matrix_at_0_50"]["true_positives"],
            "dev_fp_50": dev_res["confusion_matrix_at_0_50"]["false_positives"],
            "dev_tn_50": dev_res["confusion_matrix_at_0_50"]["true_negatives"],
            "dev_fn_50": dev_res["confusion_matrix_at_0_50"]["false_negatives"],
            "dev_pos_diff": dev_res["pos_decisions"]["DIFFERENT"],
            "dev_pos_rev": dev_res["pos_decisions"]["REVIEW"],
            "dev_pos_hc": dev_res["pos_decisions"]["HIGH_CONFIDENCE"],
            "dev_neg_diff": dev_res["neg_decisions"]["DIFFERENT"],
            "dev_neg_rev": dev_res["neg_decisions"]["REVIEW"],
            "dev_neg_hc": dev_res["neg_decisions"]["HIGH_CONFIDENCE"],
            # HELDOUT
            "held_roc_auc": held_res["roc_auc"],
            "held_pr_auc": held_res["pr_auc"],
            "held_separation": held_res["score_separation"],
            "held_pos_mean": held_res["pos_mean"],
            "held_neg_mean": held_res["neg_mean"],
            "held_f1_50": held_res["confusion_matrix_at_0_50"]["f1_score"],
            "held_acc_50": held_res["confusion_matrix_at_0_50"]["accuracy"],
            "held_tp_50": held_res["confusion_matrix_at_0_50"]["true_positives"],
            "held_fp_50": held_res["confusion_matrix_at_0_50"]["false_positives"],
            "held_tn_50": held_res["confusion_matrix_at_0_50"]["true_negatives"],
            "held_fn_50": held_res["confusion_matrix_at_0_50"]["false_negatives"],
            "held_pos_diff": held_res["pos_decisions"]["DIFFERENT"],
            "held_pos_rev": held_res["pos_decisions"]["REVIEW"],
            "held_pos_hc": held_res["pos_decisions"]["HIGH_CONFIDENCE"],
            "held_neg_diff": held_res["neg_decisions"]["DIFFERENT"],
            "held_neg_rev": held_res["neg_decisions"]["REVIEW"],
            "held_neg_hc": held_res["neg_decisions"]["HIGH_CONFIDENCE"],
            # HN
            "hn_mean_score": hn_res["mean_score"],
            "hn_median_score": hn_res["median_score"],
            "hn_max_score": hn_res["max_score"],
            "hn_count_ge_0_50": hn_res["count_ge_0_50"],
            "hn_count_ge_0_80": hn_res["count_ge_0_80"],
            "hn_count_ge_0_85": hn_res["count_ge_0_85"],
            "hn_diff": hn_res["decision_distribution"]["DIFFERENT"],
            "hn_rev": hn_res["decision_distribution"]["REVIEW"],
            "hn_hc": hn_res["decision_distribution"]["HIGH_CONFIDENCE"],
        })

    report = {
        "experiment_name": "Final Controlled Qwen A/B Experiment",
        "objective": "Controlled evaluation of Control Prior vs CAND_0804 vs CAND_0678 with frozen production gates/thresholds",
        "dataset_audit": {
            "DEV": {"total": len(dev_df), "positive_count": int(np.sum(y_dev == 1)), "negative_count": int(np.sum(y_dev == 0))},
            "HELDOUT": {"total": len(held_df), "positive_count": int(np.sum(y_held == 1)), "negative_count": int(np.sum(y_held == 0))},
            "HARD_NEGATIVES_300": {"total": len(hn_df), "positive_count": 0, "negative_count": len(hn_df)},
        },
        "feature_source_audit": {
            "semantic_model": "Fine-Tuned Qwen INT8 Embedding Model",
            "model_path": "/home/shikhar/mira-model-test/Mira.ai",
            "embedding_dimension": 1024,
            "quantization": "INT8 (bitsandbytes)",
            "feature_parity": "Exact production parity across text, spec, grade, other_attributes, and critical gates",
        },
        "arms_evaluated": results,
    }

    # Save report JSON
    if output_report_path:
        out_p = Path(output_report_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w") as f:
            json.dump(report, f, indent=2)
        print(f"Saved full experiment report to: {out_p}")

    # Save summary CSV
    if output_csv_path:
        csv_p = Path(output_csv_path)
        csv_p.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(csv_rows).to_csv(csv_p, index=False)
        print(f"Saved summary CSV to: {csv_p}")

    return report


if __name__ == "__main__":
    run_qwen_controlled_ab()
