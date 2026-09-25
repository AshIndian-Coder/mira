"""
Evaluation pipeline for Step 7 Independent Stress-Test Population.
Evaluates BASELINE, REG_1.00, and REG_HN_2.00 configurations on the 712-pair stress test dataset.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, precision_recall_fscore_support, roc_auc_score

from app.services.evaluation.feature_extraction import extract_features_for_dataframe
from app.services.evaluation.learned_weights_experiment import (
    BASELINE_WEIGHTS,
    DIFFERENT_THRESHOLD,
    FEATURE_NAMES,
    HIGH_CONFIDENCE_THRESHOLD,
)

CONFIGS = {
    "BASELINE": np.array([0.20, 0.20, 0.35, 0.15, 0.10], dtype=np.float64),
    "REG_1.00": np.array([0.2367, 0.3192, 0.2173, 0.1115, 0.1154], dtype=np.float64),
    "REG_HN_2.00": np.array([0.2755, 0.5014, 0.0782, 0.1449, 0.0000], dtype=np.float64),
}


def run_stress_evaluation():
    print("=== STEP 6 & 7: EXECUTING INDEPENDENT STRESS EVALUATION ===")

    stress_csv = Path("data/evaluation/stress_test_dataset.csv")
    stress_df = pd.read_csv(stress_csv)
    print(f"Loaded stress dataset ({len(stress_df)} pairs). Extracting production features...")

    # Check if features are already cached
    feats_csv = Path("data/evaluation/features/stress_test_features.csv")
    feats_csv.parent.mkdir(parents=True, exist_ok=True)

    if feats_csv.exists():
        print(f"Loading cached features from {feats_csv}...")
        df_feats = pd.read_csv(feats_csv)
    else:
        print("Extracting production features with embeddings...")
        df_feats = extract_features_for_dataframe(
            stress_df,
            desc_a_col="description_a",
            desc_b_col="description_b",
            category_col="category",
        )
        df_feats.to_csv(feats_csv, index=False)
        print(f"Saved extracted features to {feats_csv}")

    X = df_feats[FEATURE_NAMES].to_numpy(dtype=np.float64)
    y = df_feats["label"].to_numpy(dtype=np.int64)

    # Compute scores and production decisions for each config
    for cfg_name, weights in CONFIGS.items():
        scores = X @ weights
        df_feats[f"score_{cfg_name}"] = scores

        # Decision simulation
        decisions = []
        for idx, s in enumerate(scores):
            critical_checks_json = df_feats.iloc[idx].get("critical_checks_json")
            if isinstance(critical_checks_json, str):
                try:
                    checks = json.loads(critical_checks_json)
                except Exception:
                    checks = []
            else:
                checks = []

            has_unknown = any(c.get("status") == "UNKNOWN" for c in checks)
            has_conflict = any(c.get("status") == "CONFLICT" for c in checks)
            gates_pass = bool(checks) and all(c.get("status") == "PASS" for c in checks)

            if s >= HIGH_CONFIDENCE_THRESHOLD and gates_pass:
                dec = "HIGH_CONFIDENCE"
            elif has_unknown or has_conflict:
                dec = "REVIEW"
            elif s > DIFFERENT_THRESHOLD:
                dec = "REVIEW"
            else:
                dec = "DIFFERENT"
            decisions.append(dec)

        df_feats[f"decision_{cfg_name}"] = decisions

    # Compile comprehensive metrics report
    report: Dict[str, Any] = {
        "configurations": {k: [round(float(w), 4) for w in v] for k, v in CONFIGS.items()},
        "total_pairs": len(df_feats),
        "overall_metrics": {},
        "per_population_metrics": {},
        "tier_transition_analysis": {},
        "critical_field_breakdown": {},
    }

    # 1. Overall & Per-Population Performance
    populations = ["OVERALL"] + sorted(df_feats["stress_population"].unique().tolist())

    for pop in populations:
        if pop == "OVERALL":
            pop_df = df_feats
            sub_X = X
            sub_y = y
        else:
            pop_df = df_feats[df_feats["stress_population"] == pop].reset_index(drop=True)
            sub_X = pop_df[FEATURE_NAMES].to_numpy(dtype=np.float64)
            sub_y = pop_df["label"].to_numpy(dtype=np.int64)

        pop_stats = {
            "total_count": len(pop_df),
            "positive_count": int(np.sum(sub_y == 1)),
            "negative_count": int(np.sum(sub_y == 0)),
            "configs": {},
        }

        for cfg_name, weights in CONFIGS.items():
            scores = pop_df[f"score_{cfg_name}"].to_numpy(dtype=np.float64)
            decisions = pop_df[f"decision_{cfg_name}"].to_numpy()

            has_both = len(np.unique(sub_y)) > 1
            roc_auc = float(roc_auc_score(sub_y, scores)) if has_both else None
            pr_auc = float(average_precision_score(sub_y, scores)) if has_both else None

            preds_50 = (scores >= 0.50).astype(int)
            if has_both:
                prec, rec, f1, _ = precision_recall_fscore_support(sub_y, preds_50, average="binary", zero_division=0)
            else:
                prec, rec, f1 = None, None, None

            pos_mask = (sub_y == 1)
            neg_mask = (sub_y == 0)

            pos_scores = scores[pos_mask]
            neg_scores = scores[neg_mask]

            pos_dec = decisions[pos_mask] if len(pos_scores) > 0 else []
            neg_dec = decisions[neg_mask] if len(neg_scores) > 0 else []

            # Separation
            sep = float(np.mean(pos_scores) - np.mean(neg_scores)) if (len(pos_scores) and len(neg_scores)) else None

            # False High Confidence Rate
            false_hc = int(np.sum(neg_dec == "HIGH_CONFIDENCE")) if len(neg_dec) else 0
            false_hc_pct = round(false_hc / len(neg_dec) * 100, 2) if len(neg_dec) else 0.0

            cfg_res = {
                "weights": [round(float(w), 4) for w in weights],
                "roc_auc": round(roc_auc, 4) if roc_auc is not None else None,
                "pr_auc": round(pr_auc, 4) if pr_auc is not None else None,
                "f1_at_0.50": round(float(f1), 4) if f1 is not None else None,
                "score_separation": round(sep, 4) if sep is not None else None,
                "false_high_confidence_count": false_hc,
                "false_high_confidence_rate_pct": false_hc_pct,
                "overall_score": {
                    "mean": round(float(np.mean(scores)), 4),
                    "median": round(float(np.median(scores)), 4),
                    "std": round(float(np.std(scores)), 4),
                },
                "positive_population": {
                    "count": len(pos_scores),
                    "HIGH_CONFIDENCE": int(np.sum(pos_dec == "HIGH_CONFIDENCE")),
                    "HIGH_CONFIDENCE_pct": round(float(np.mean(pos_dec == "HIGH_CONFIDENCE") * 100), 2) if len(pos_scores) else 0.0,
                    "REVIEW": int(np.sum(pos_dec == "REVIEW")),
                    "REVIEW_pct": round(float(np.mean(pos_dec == "REVIEW") * 100), 2) if len(pos_scores) else 0.0,
                    "DIFFERENT": int(np.sum(pos_dec == "DIFFERENT")),
                    "DIFFERENT_pct": round(float(np.mean(pos_dec == "DIFFERENT") * 100), 2) if len(pos_scores) else 0.0,
                    "mean_score": round(float(np.mean(pos_scores)), 4) if len(pos_scores) else None,
                    "median_score": round(float(np.median(pos_scores)), 4) if len(pos_scores) else None,
                },
                "negative_population": {
                    "count": len(neg_scores),
                    "HIGH_CONFIDENCE": int(np.sum(neg_dec == "HIGH_CONFIDENCE")),
                    "HIGH_CONFIDENCE_pct": round(float(np.mean(neg_dec == "HIGH_CONFIDENCE") * 100), 2) if len(neg_scores) else 0.0,
                    "REVIEW": int(np.sum(neg_dec == "REVIEW")),
                    "REVIEW_pct": round(float(np.mean(neg_dec == "REVIEW") * 100), 2) if len(neg_scores) else 0.0,
                    "DIFFERENT": int(np.sum(neg_dec == "DIFFERENT")),
                    "DIFFERENT_pct": round(float(np.mean(neg_dec == "DIFFERENT") * 100), 2) if len(neg_scores) else 0.0,
                    "mean_score": round(float(np.mean(neg_scores)), 4) if len(neg_scores) else None,
                    "median_score": round(float(np.median(neg_scores)), 4) if len(neg_scores) else None,
                }
            }
            pop_stats["configs"][cfg_name] = cfg_res

        if pop == "OVERALL":
            report["overall_metrics"] = pop_stats
        else:
            report["per_population_metrics"][pop] = pop_stats

    # 2. Tier Transitions (Rescues vs Regressions)
    for cand_name in ["REG_1.00", "REG_HN_2.00"]:
        base_dec = df_feats["decision_BASELINE"].to_numpy()
        cand_dec = df_feats[f"decision_{cand_name}"].to_numpy()
        labels = df_feats["label"].to_numpy()

        pos_mask = (labels == 1)
        neg_mask = (labels == 0)

        # Positives
        pos_diff_to_rev = int(np.sum(pos_mask & (base_dec == "DIFFERENT") & (cand_dec == "REVIEW")))
        pos_diff_to_hc = int(np.sum(pos_mask & (base_dec == "DIFFERENT") & (cand_dec == "HIGH_CONFIDENCE")))
        pos_rev_to_diff = int(np.sum(pos_mask & (base_dec == "REVIEW") & (cand_dec == "DIFFERENT")))
        pos_hc_to_rev = int(np.sum(pos_mask & (base_dec == "HIGH_CONFIDENCE") & (cand_dec == "REVIEW")))

        # Negatives
        neg_rev_to_diff = int(np.sum(neg_mask & (base_dec == "REVIEW") & (cand_dec == "DIFFERENT")))
        neg_diff_to_rev = int(np.sum(neg_mask & (base_dec == "DIFFERENT") & (cand_dec == "REVIEW")))
        neg_to_hc = int(np.sum(neg_mask & (cand_dec == "HIGH_CONFIDENCE")))

        report["tier_transition_analysis"][cand_name] = {
            "positive_rescues": {
                "DIFFERENT_to_REVIEW": pos_diff_to_rev,
                "DIFFERENT_to_HIGH_CONFIDENCE": pos_diff_to_hc,
                "total_positive_rescues": pos_diff_to_rev + pos_diff_to_hc,
            },
            "positive_regressions": {
                "REVIEW_to_DIFFERENT": pos_rev_to_diff,
                "HIGH_CONFIDENCE_to_REVIEW": pos_hc_to_rev,
                "total_positive_regressions": pos_rev_to_diff + pos_hc_to_rev,
            },
            "negative_improvements": {
                "REVIEW_to_DIFFERENT": neg_rev_to_diff,
            },
            "negative_regressions": {
                "DIFFERENT_to_REVIEW": neg_diff_to_rev,
            },
            "safety_failures": {
                "negative_to_HIGH_CONFIDENCE": neg_to_hc,
            },
        }

    # 3. Per-Field Hard Negative Analysis (Section 8)
    crit_df = df_feats[df_feats["stress_population"] == "CRITICAL_HARD_NEGATIVE"].reset_index(drop=True)
    field_summary = {}

    for field, grp in crit_df.groupby("critical_field"):
        f_count = len(grp)
        base_diff = int(np.sum(grp["decision_BASELINE"] == "DIFFERENT"))
        reg1_diff = int(np.sum(grp["decision_REG_1.00"] == "DIFFERENT"))
        reghn_diff = int(np.sum(grp["decision_REG_HN_2.00"] == "DIFFERENT"))

        base_mean = float(np.mean(grp["score_BASELINE"]))
        reg1_mean = float(np.mean(grp["score_REG_1.00"]))
        reghn_mean = float(np.mean(grp["score_REG_HN_2.00"]))

        field_summary[str(field)] = {
            "count": f_count,
            "baseline_DIFFERENT_count": base_diff,
            "baseline_DIFFERENT_pct": round(base_diff / f_count * 100, 2),
            "REG_1.00_DIFFERENT_count": reg1_diff,
            "REG_1.00_DIFFERENT_pct": round(reg1_diff / f_count * 100, 2),
            "REG_HN_2.00_DIFFERENT_count": reghn_diff,
            "REG_HN_2.00_DIFFERENT_pct": round(reghn_diff / f_count * 100, 2),
            "mean_composite_score": {
                "BASELINE": round(base_mean, 4),
                "REG_1.00": round(reg1_mean, 4),
                "REG_HN_2.00": round(reghn_mean, 4),
            },
        }

    report["critical_field_breakdown"] = field_summary

    class NpEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (np.integer, np.int64, np.int32)):
                return int(obj)
            elif isinstance(obj, (np.floating, np.float64, np.float32)):
                return float(obj)
            elif isinstance(obj, (np.ndarray,)):
                return obj.tolist()
            return super(NpEncoder, self).default(obj)

    out_json = Path("data/evaluation/stress_test_evaluation_report.json")
    with open(out_json, "w") as f:
        json.dump(report, f, indent=2, cls=NpEncoder)
    print(f"\nSaved stress evaluation report to {out_json}")

    return report, df_feats


if __name__ == "__main__":
    run_stress_evaluation()
