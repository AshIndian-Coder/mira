"""
Qwen-Aware Constrained Learned Weights Experiment for MIRA Track 1.

Evaluates whether constrained weight reallocation within:
  - text:             [0.10, 0.25]
  - semantic/Qwen:    [0.20, 0.40]
  - specification:    [0.25, 0.45]
  - material_grade:   [0.10, 0.20]
  - other_attributes: [0.05, 0.15]
improves DEV/HELDOUT discrimination without weakening hard-negative safety or causing regressions.

Baseline Prior: [0.20, 0.20, 0.35, 0.15, 0.10]
Semantic Model: Fine-tuned Qwen INT8 embedding model (1024D)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, precision_recall_fscore_support, roc_auc_score

FEATURE_NAMES = [
    "text_similarity",
    "semantic_similarity",
    "specification_similarity",
    "material_grade_similarity",
    "other_attributes_similarity",
]

BASELINE_WEIGHTS = np.array([0.20, 0.20, 0.35, 0.15, 0.10], dtype=np.float64)
HIGH_CONFIDENCE_THRESHOLD = 0.85
DIFFERENT_THRESHOLD = 0.45

# Grid boundaries per specification
SEARCH_BOUNDS = {
    "text": (0.10, 0.25),
    "semantic": (0.20, 0.40),
    "specification": (0.25, 0.45),
    "material_grade": (0.10, 0.20),
    "other_attributes": (0.05, 0.15),
}


def generate_candidate_grid(step: float = 0.025) -> List[np.ndarray]:
    """Generate deterministic candidate weight grid within the specified bounded region."""
    w1_range = np.arange(SEARCH_BOUNDS["text"][0], SEARCH_BOUNDS["text"][1] + 1e-6, step)
    w2_range = np.arange(SEARCH_BOUNDS["semantic"][0], SEARCH_BOUNDS["semantic"][1] + 1e-6, step)
    w3_range = np.arange(SEARCH_BOUNDS["specification"][0], SEARCH_BOUNDS["specification"][1] + 1e-6, step)
    w4_range = np.arange(SEARCH_BOUNDS["material_grade"][0], SEARCH_BOUNDS["material_grade"][1] + 1e-6, step)
    w5_range = np.arange(SEARCH_BOUNDS["other_attributes"][0], SEARCH_BOUNDS["other_attributes"][1] + 1e-6, step)

    candidates = []
    for w1 in w1_range:
        for w2 in w2_range:
            for w3 in w3_range:
                for w4 in w4_range:
                    for w5 in w5_range:
                        w = np.array([w1, w2, w3, w4, w5], dtype=np.float64)
                        if abs(np.sum(w) - 1.0) < 1e-6:
                            candidates.append(np.round(w, 4))

    # Ensure baseline is strictly present
    if not any(np.allclose(BASELINE_WEIGHTS, c) for c in candidates):
        candidates.insert(0, BASELINE_WEIGHTS.copy())

    return candidates


def evaluate_decisions_vectorized(
    scores: np.ndarray,
    has_conflict: np.ndarray,
    has_unknown: np.ndarray,
    gates_pass: np.ndarray,
) -> Dict[str, Any]:
    """Execute vectorized production decision simulation."""
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


def evaluate_dataset(
    X: np.ndarray,
    y: np.ndarray,
    has_conflict: np.ndarray,
    has_unknown: np.ndarray,
    gates_pass: np.ndarray,
    weights: np.ndarray,
) -> Dict[str, Any]:
    """Calculate discrimination metrics and production decisions on a dataset."""
    scores = X @ weights
    has_both = len(np.unique(y)) > 1

    roc_auc = float(roc_auc_score(y, scores)) if has_both else None
    pr_auc = float(average_precision_score(y, scores)) if has_both else None

    preds_50 = (scores >= 0.50).astype(int)
    if has_both:
        prec, rec, f1, _ = precision_recall_fscore_support(y, preds_50, average="binary", zero_division=0)
    else:
        prec, rec, f1 = None, None, None

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

    return {
        "roc_auc": round(roc_auc, 4) if roc_auc is not None else None,
        "pr_auc": round(pr_auc, 4) if pr_auc is not None else None,
        "f1_at_0.50": round(float(f1), 4) if f1 is not None else None,
        "score_separation": round(sep, 4) if sep is not None else None,
        "pos_mean": round(pos_mean, 4) if pos_mean is not None else None,
        "pos_median": round(pos_med, 4) if pos_med is not None else None,
        "neg_mean": round(neg_mean, 4) if neg_mean is not None else None,
        "neg_median": round(neg_med, 4) if neg_med is not None else None,
        "overall_decisions": {
            "HIGH_CONFIDENCE": dec_res["HIGH_CONFIDENCE"],
            "REVIEW": dec_res["REVIEW"],
            "DIFFERENT": dec_res["DIFFERENT"],
        },
        "pos_decisions": {
            "HIGH_CONFIDENCE": int(np.sum(is_hc & pos_mask)),
            "REVIEW": int(np.sum(is_rev & pos_mask)),
            "DIFFERENT": int(np.sum(is_diff & pos_mask)),
        },
        "neg_decisions": {
            "HIGH_CONFIDENCE": int(np.sum(is_hc & neg_mask)),
            "REVIEW": int(np.sum(is_rev & neg_mask)),
            "DIFFERENT": int(np.sum(is_diff & neg_mask)),
        },
        "scores": scores,
        "decisions": dec_res["decisions"],
    }


def evaluate_hard_negatives(
    X_hn: np.ndarray,
    df_hn: pd.DataFrame,
    has_conflict: np.ndarray,
    has_unknown: np.ndarray,
    gates_pass: np.ndarray,
    weights: np.ndarray,
) -> Dict[str, Any]:
    """Calculate detailed safety metrics and per-field breakdown on 300 Hard Negatives."""
    scores = X_hn @ weights
    dec_res = evaluate_decisions_vectorized(scores, has_conflict, has_unknown, gates_pass)

    # Per-field breakdown
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
        "DIFFERENT": dec_res["DIFFERENT"],
        "REVIEW": dec_res["REVIEW"],
        "HIGH_CONFIDENCE": dec_res["HIGH_CONFIDENCE"],
        "per_field_breakdown": field_stats,
    }


def run_qwen_learned_weights_experiment(
    dev_path: str = "/home/shikhar/mira-model-test/hybrid_ab_results/Qwen_INT8_dev_pairs.csv",
    heldout_path: str = "/home/shikhar/mira-model-test/hybrid_ab_results/Qwen_INT8_heldout_pairs.csv",
    hn_path: str = "/home/shikhar/mira-model-test/hybrid_ab_results/Qwen_INT8_hn300_pairs.csv",
    grid_step: float = 0.025,
) -> Dict[str, Any]:
    print("=== STARTING QWEN-AWARE CONSTRAINED LEARNED WEIGHTS EXPERIMENT ===")

    # Load feature matrices
    print("Loading Qwen INT8 feature datasets...")
    dev_df = pd.read_csv(dev_path)
    held_df = pd.read_csv(heldout_path)
    hn_df = pd.read_csv(hn_path)

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

    print(f"Loaded DEV: {len(dev_df)} pairs, HELDOUT: {len(held_df)} pairs, HN: {len(hn_df)} pairs.")

    # 1. Evaluate Baseline
    base_dev = evaluate_dataset(X_dev, y_dev, dev_conflict, dev_unknown, dev_pass, BASELINE_WEIGHTS)
    base_held = evaluate_dataset(X_held, y_held, held_conflict, held_unknown, held_pass, BASELINE_WEIGHTS)
    base_hn = evaluate_hard_negatives(X_hn, hn_df, hn_conflict, hn_unknown, hn_pass, BASELINE_WEIGHTS)

    print("\n--- BASELINE QWEN RESULTS ---")
    print(f"DEV ROC-AUC: {base_dev['roc_auc']:.4f} | PR-AUC: {base_dev['pr_auc']:.4f} | Margin: {base_dev['score_separation']:+.4f}")
    print(f"DEV Pos Dec: {base_dev['pos_decisions']} | DEV Neg Dec: {base_dev['neg_decisions']}")
    print(f"HELDOUT ROC-AUC: {base_held['roc_auc']:.4f} | PR-AUC: {base_held['pr_auc']:.4f} | Margin: {base_held['score_separation']:+.4f}")
    print(f"HN 300: Mean={base_hn['mean_score']:.4f}, Max={base_hn['max_score']:.4f}, DIFFERENT={base_hn['DIFFERENT']}, REVIEW={base_hn['REVIEW']}, HC={base_hn['HIGH_CONFIDENCE']}")

    # 2. Generate Candidate Grid
    candidates = generate_candidate_grid(step=grid_step)
    print(f"\nGenerated {len(candidates)} deterministic candidate weight vectors.")

    # 3. Evaluate All Candidates
    candidate_records = []
    surviving_candidates = []

    for idx, w in enumerate(candidates):
        is_baseline = bool(np.allclose(w, BASELINE_WEIGHTS))
        dev_res = evaluate_dataset(X_dev, y_dev, dev_conflict, dev_unknown, dev_pass, w)
        held_res = evaluate_dataset(X_held, y_held, held_conflict, held_unknown, held_pass, w)
        hn_res = evaluate_hard_negatives(X_hn, hn_df, hn_conflict, hn_unknown, hn_pass, w)

        # Safety & Rejection Checks
        rejections = []
        if hn_res["count_ge_0_85"] > 0:
            rejections.append(f"HN >= 0.85 count ({hn_res['count_ge_0_85']}) > 0")
        if hn_res["count_ge_0_80"] > base_hn["count_ge_0_80"]:
            rejections.append(f"HN >= 0.80 count ({hn_res['count_ge_0_80']}) > baseline ({base_hn['count_ge_0_80']})")
        if hn_res["HIGH_CONFIDENCE"] > 0:
            rejections.append(f"HN HIGH_CONFIDENCE ({hn_res['HIGH_CONFIDENCE']}) > 0")
        if w[2] < 0.25:
            rejections.append(f"Specification weight ({w[2]}) collapsed below 0.25")
        if w[3] < 0.10:
            rejections.append(f"Material-grade weight ({w[3]}) collapsed below 0.10")

        # Check excessive HN REVIEW inflation (> 15 increase vs baseline 68)
        if hn_res["REVIEW"] > base_hn["REVIEW"] + 15:
            rejections.append(f"HN REVIEW count ({hn_res['REVIEW']}) exceeded baseline ({base_hn['REVIEW']}) by > 15")

        # Check excessive Pos DIFFERENT increase (> 10 increase vs baseline 359 on DEV)
        if dev_res["pos_decisions"]["DIFFERENT"] > base_dev["pos_decisions"]["DIFFERENT"] + 10:
            rejections.append(f"DEV Pos DIFFERENT ({dev_res['pos_decisions']['DIFFERENT']}) increased vs baseline ({base_dev['pos_decisions']['DIFFERENT']}) by > 10")

        is_viable = (len(rejections) == 0)

        record = {
            "candidate_id": f"CAND_{idx:04d}",
            "is_baseline": is_baseline,
            "weights": [round(float(x), 4) for x in w],
            "w_text": round(float(w[0]), 4),
            "w_semantic": round(float(w[1]), 4),
            "w_spec": round(float(w[2]), 4),
            "w_grade": round(float(w[3]), 4),
            "w_other": round(float(w[4]), 4),
            # DEV Metrics
            "dev_roc_auc": dev_res["roc_auc"],
            "dev_pr_auc": dev_res["pr_auc"],
            "dev_f1_50": dev_res["f1_at_0.50"],
            "dev_margin": dev_res["score_separation"],
            "dev_pos_mean": dev_res["pos_mean"],
            "dev_neg_mean": dev_res["neg_mean"],
            "dev_pos_diff": dev_res["pos_decisions"]["DIFFERENT"],
            "dev_pos_rev": dev_res["pos_decisions"]["REVIEW"],
            "dev_pos_hc": dev_res["pos_decisions"]["HIGH_CONFIDENCE"],
            "dev_neg_diff": dev_res["neg_decisions"]["DIFFERENT"],
            "dev_neg_rev": dev_res["neg_decisions"]["REVIEW"],
            "dev_neg_hc": dev_res["neg_decisions"]["HIGH_CONFIDENCE"],
            # HELDOUT Metrics
            "held_roc_auc": held_res["roc_auc"],
            "held_pr_auc": held_res["pr_auc"],
            "held_f1_50": held_res["f1_at_0.50"],
            "held_margin": held_res["score_separation"],
            "held_pos_mean": held_res["pos_mean"],
            "held_neg_mean": held_res["neg_mean"],
            "held_pos_diff": held_res["pos_decisions"]["DIFFERENT"],
            "held_pos_rev": held_res["pos_decisions"]["REVIEW"],
            "held_pos_hc": held_res["pos_decisions"]["HIGH_CONFIDENCE"],
            "held_neg_diff": held_res["neg_decisions"]["DIFFERENT"],
            "held_neg_rev": held_res["neg_decisions"]["REVIEW"],
            "held_neg_hc": held_res["neg_decisions"]["HIGH_CONFIDENCE"],
            # HN 300 Metrics
            "hn_mean_score": hn_res["mean_score"],
            "hn_median_score": hn_res["median_score"],
            "hn_max_score": hn_res["max_score"],
            "hn_count_ge_0_50": hn_res["count_ge_0_50"],
            "hn_count_ge_0_80": hn_res["count_ge_0_80"],
            "hn_count_ge_0_85": hn_res["count_ge_0_85"],
            "hn_diff": hn_res["DIFFERENT"],
            "hn_rev": hn_res["REVIEW"],
            "hn_hc": hn_res["HIGH_CONFIDENCE"],
            # Viability
            "is_viable": is_viable,
            "rejection_reasons": rejections,
            "hn_per_field_breakdown": hn_res["per_field_breakdown"],
        }

        candidate_records.append(record)
        if is_viable:
            surviving_candidates.append(record)

    print(f"\nTotal evaluated: {len(candidate_records)}")
    print(f"Surviving viable candidates: {len(surviving_candidates)} / {len(candidate_records)} ({len(surviving_candidates)/len(candidate_records)*100:.1f}%)")

    # Sort surviving candidates by DEV ROC-AUC and margin
    surviving_candidates.sort(key=lambda c: (c["dev_roc_auc"], c["dev_margin"]), reverse=True)

    top_candidates = surviving_candidates[:5]
    print("\n--- TOP SURVIVING CANDIDATES ---")
    for i, c in enumerate(top_candidates):
        print(f"Rank {i+1}: ID={c['candidate_id']} Weights={c['weights']}")
        print(f"  DEV: ROC-AUC={c['dev_roc_auc']:.4f} (+{c['dev_roc_auc'] - base_dev['roc_auc']:+.4f}) | Margin={c['dev_margin']:.4f} | Pos DIFFERENT={c['dev_pos_diff']}")
        print(f"  HELDOUT: ROC-AUC={c['held_roc_auc']:.4f} (+{c['held_roc_auc'] - base_held['roc_auc']:+.4f}) | Margin={c['held_margin']:.4f}")
        print(f"  HN 300: Mean={c['hn_mean_score']:.4f}, Max={c['hn_max_score']:.4f}, DIFFERENT={c['hn_diff']}, REVIEW={c['hn_rev']}")

    # Save CSV and JSON
    out_dir = Path("data/evaluation")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save candidates summary CSV
    csv_rows = []
    for r in candidate_records:
        csv_row = {k: v for k, v in r.items() if k not in ("rejection_reasons", "hn_per_field_breakdown", "weights")}
        csv_row["rejection_reasons"] = "; ".join(r["rejection_reasons"])
        csv_rows.append(csv_row)

    df_candidates = pd.DataFrame(csv_rows)
    cand_csv_path = out_dir / "qwen_learned_weights_candidates.csv"
    df_candidates.to_csv(cand_csv_path, index=False)
    print(f"\nSaved candidates CSV to {cand_csv_path}")

    # Compile JSON Report
    report = {
        "experiment_name": "Qwen-Aware Constrained Learned Weights Experiment",
        "dataset_audit": {
            "DEV": {"total": len(dev_df), "positive_count": int((y_dev == 1).sum()), "negative_count": int((y_dev == 0).sum())},
            "HELDOUT": {"total": len(held_df), "positive_count": int((y_held == 1).sum()), "negative_count": int((y_held == 0).sum())},
            "HARD_NEGATIVES_300": {"total": len(hn_df), "positive_count": 0, "negative_count": len(hn_df)},
        },
        "feature_source_audit": {
            "semantic_model": "Fine-Tuned Qwen INT8 Embedding Model",
            "model_path": "/home/shikhar/mira-model-test/Mira.ai",
            "embedding_dimension": 1024,
            "quantization": "INT8 (bitsandbytes)",
            "feature_parity": "Exact production parity across text, spec, grade, other_attributes, and critical gates",
        },
        "search_space": {
            "bounds": SEARCH_BOUNDS,
            "grid_step": grid_step,
            "total_candidates": len(candidates),
        },
        "baseline_qwen": {
            "weights": [round(float(x), 4) for x in BASELINE_WEIGHTS],
            "DEV": {k: v for k, v in base_dev.items() if k not in ("scores", "decisions")},
            "HELDOUT": {k: v for k, v in base_held.items() if k not in ("scores", "decisions")},
            "HN_300": base_hn,
        },
        "summary_statistics": {
            "total_evaluated": len(candidate_records),
            "surviving_count": len(surviving_candidates),
            "rejected_count": len(candidate_records) - len(surviving_candidates),
        },
        "top_surviving_candidates": top_candidates,
        "all_candidates": candidate_records,
    }

    class NpEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (np.integer, np.int64, np.int32)):
                return int(obj)
            elif isinstance(obj, (np.floating, np.float64, np.float32)):
                return float(obj)
            elif isinstance(obj, (np.ndarray,)):
                return obj.tolist()
            return super(NpEncoder, self).default(obj)

    json_path = out_dir / "qwen_learned_weights_experiment_report.json"
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2, cls=NpEncoder)
    print(f"Saved experiment JSON report to {json_path}")

    return report


if __name__ == "__main__":
    run_qwen_learned_weights_experiment()
