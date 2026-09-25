"""
Offline Learned-Weight Experiment for MIRA Hybrid Candidate Scoring (Corrected & Production-Parity).

Audits and evaluates whether learned non-negative weight vectors (summing to 1.0)
trained on curated DEV (5,228 pairs) improve upon the hand-designed production baseline:
    [0.20, 0.20, 0.35, 0.15, 0.10]
when evaluated on HELDOUT (5,284 pairs) and the 300 Hard Negatives benchmark.

Features (exact production parity):
0: text_similarity
1: semantic_similarity
2: specification_similarity
3: material_grade_similarity
4: other_attributes_similarity
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.metrics import (
    average_precision_score,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold

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


def load_dataset_matrix(path: Path | str) -> Tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    """Load feature matrix X, label vector y, and dataframe from CSV."""
    df = pd.read_csv(path, low_memory=False)
    X = df[FEATURE_NAMES].to_numpy(dtype=np.float64)
    y = df["label"].to_numpy(dtype=np.int64)
    return X, y, df


def optimize_weights(
    X: np.ndarray,
    y: np.ndarray,
    lambda_reg: float = 0.0,
    lambda_hn: float = 0.0,
    hn_indices: Optional[np.ndarray] = None,
    hn_threshold: float = 0.50,
    w0: np.ndarray = BASELINE_WEIGHTS,
    initial_w: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """
    Fit non-negative weights summing to 1.0 using calibrated logistic loss:
    p = sigmoid(scale * (w^T x - bias)).

    Supports:
      - Simplex constraint (w_i >= 0, sum w_i = 1)
      - L2 regularization prior toward w0: lambda_reg * ||w - w0||^2
      - Hard negative penalty: lambda_hn * mean(max(0, w^T x_hn - hn_threshold)^2)
    """
    if initial_w is None:
        init_w = np.array([0.20, 0.20, 0.20, 0.20, 0.20], dtype=np.float64)
    else:
        init_w = np.array(initial_w, dtype=np.float64)

    init_params = np.concatenate([init_w, [10.0, 0.5]])

    def obj(params: np.ndarray) -> float:
        w = params[:5]
        scale = params[5]
        bias = params[6]
        s = X @ w
        logits = np.clip(scale * (s - bias), -30.0, 30.0)
        p = 1.0 / (1.0 + np.exp(-logits))
        eps = 1e-12
        p = np.clip(p, eps, 1.0 - eps)
        base_loss = -np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p))

        # L2 prior toward baseline w0
        reg_loss = 0.0
        if lambda_reg > 0.0:
            reg_loss = lambda_reg * float(np.sum((w - w0) ** 2))

        # Hard negative penalty
        hn_loss = 0.0
        if lambda_hn > 0.0 and hn_indices is not None and len(hn_indices) > 0:
            s_hn = X[hn_indices] @ w
            excess = np.maximum(0.0, s_hn - hn_threshold)
            hn_loss = lambda_hn * float(np.mean(excess ** 2))

        return float(base_loss + reg_loss + hn_loss)

    bounds = [(0.0, 1.0)] * 5 + [(0.1, 100.0), (0.0, 1.0)]
    constraints = [{"type": "eq", "fun": lambda p: np.sum(p[:5]) - 1.0}]

    res = minimize(
        obj,
        init_params,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 500, "ftol": 1e-9},
    )

    learned_w = np.clip(res.x[:5], 0.0, 1.0)
    learned_w = learned_w / np.sum(learned_w)

    return {
        "weights": learned_w,
        "scale": float(res.x[5]),
        "bias": float(res.x[6]),
        "loss": float(res.fun),
        "success": bool(res.success),
        "message": str(res.message),
        "nit": int(res.nit),
        "lambda_reg": lambda_reg,
        "lambda_hn": lambda_hn,
    }


def compute_dataset_metrics(
    X: np.ndarray,
    y: np.ndarray,
    weights: np.ndarray,
    neutral_threshold: float = 0.50,
) -> Dict[str, Any]:
    """Calculate continuous ranking and classification metrics on a dataset given weights."""
    scores = X @ weights
    has_both_classes = len(np.unique(y)) > 1

    if has_both_classes:
        roc_auc = float(roc_auc_score(y, scores))
        pr_auc = float(average_precision_score(y, scores))
    else:
        roc_auc = None
        pr_auc = None

    preds_neutral = (scores >= neutral_threshold).astype(int)
    if has_both_classes:
        prec_n, rec_n, f1_n, _ = precision_recall_fscore_support(
            y, preds_neutral, average="binary", zero_division=0
        )
        acc_n = float(np.mean(preds_neutral == y))
    else:
        prec_n, rec_n, f1_n, acc_n = None, None, None, None

    same_scores = scores[y == 1]
    diff_scores = scores[y == 0]

    return {
        "roc_auc": round(roc_auc, 4) if roc_auc is not None else None,
        "pr_auc": round(pr_auc, 4) if pr_auc is not None else None,
        "neutral_threshold": neutral_threshold,
        "neutral_accuracy": round(acc_n, 4) if acc_n is not None else None,
        "neutral_precision": round(prec_n, 4) if prec_n is not None else None,
        "neutral_recall": round(rec_n, 4) if rec_n is not None else None,
        "neutral_f1": round(f1_n, 4) if f1_n is not None else None,
        "score_distribution": {
            "mean": round(float(np.mean(scores)), 4),
            "median": round(float(np.median(scores)), 4),
            "std": round(float(np.std(scores)), 4),
            "min": round(float(np.min(scores)), 4),
            "max": round(float(np.max(scores)), 4),
        },
        "same_distribution": {
            "count": int(len(same_scores)),
            "mean": round(float(np.mean(same_scores)), 4) if len(same_scores) else None,
            "median": round(float(np.median(same_scores)), 4) if len(same_scores) else None,
            "std": round(float(np.std(same_scores)), 4) if len(same_scores) else None,
            "min": round(float(np.min(same_scores)), 4) if len(same_scores) else None,
            "max": round(float(np.max(same_scores)), 4) if len(same_scores) else None,
        },
        "different_distribution": {
            "count": int(len(diff_scores)),
            "mean": round(float(np.mean(diff_scores)), 4) if len(diff_scores) else None,
            "median": round(float(np.median(diff_scores)), 4) if len(diff_scores) else None,
            "std": round(float(np.std(diff_scores)), 4) if len(diff_scores) else None,
            "min": round(float(np.min(diff_scores)), 4) if len(diff_scores) else None,
            "max": round(float(np.max(diff_scores)), 4) if len(diff_scores) else None,
        },
    }


def compute_hard_negative_stats(
    X_hard: np.ndarray,
    weights: np.ndarray,
    df_hard: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Evaluate continuous scores on hard negatives with threshold counts and field breakdown."""
    scores = X_hard @ weights
    thresholds = [0.45, 0.60, 0.70, 0.80, 0.85, 0.90]
    thresh_counts = {}
    for t in thresholds:
        cnt = int(np.sum(scores >= t))
        pct = round(cnt / len(scores) * 100, 2)
        thresh_counts[str(t)] = {"count": cnt, "percentage": pct}

    field_breakdown = {}
    if df_hard is not None and "conflicting_fields" in df_hard.columns:
        for f, group in df_hard.groupby("conflicting_fields"):
            idx = group.index.to_numpy()
            f_scores = scores[idx]
            field_breakdown[str(f)] = {
                "count": len(group),
                "mean": round(float(np.mean(f_scores)), 4),
                "median": round(float(np.median(f_scores)), 4),
                "count_ge_0_80": int(np.sum(f_scores >= 0.80)),
                "count_ge_0_85": int(np.sum(f_scores >= 0.85)),
            }

    return {
        "count": len(scores),
        "min": round(float(np.min(scores)), 4),
        "max": round(float(np.max(scores)), 4),
        "mean": round(float(np.mean(scores)), 4),
        "median": round(float(np.median(scores)), 4),
        "std": round(float(np.std(scores)), 4),
        "count_ge_0_80": int(np.sum(scores >= 0.80)),
        "count_ge_0_85": int(np.sum(scores >= 0.85)),
        "threshold_breakdown": thresh_counts,
        "field_breakdown": field_breakdown,
    }


def evaluate_mira_decision_pipeline(
    X: np.ndarray,
    df: pd.DataFrame,
    weights: np.ndarray,
) -> Dict[str, Any]:
    """
    Simulate full MIRA production decision path (scores + critical gates):
      - HIGH_CONFIDENCE: score >= 0.85 AND all critical gates PASS
      - REVIEW: score > 0.45 OR has UNKNOWN/CONFLICT gate
      - DIFFERENT: score <= 0.45 AND no critical conflict
    """
    scores = X @ weights
    decisions: List[str] = []

    for idx, s in enumerate(scores):
        critical_checks_json = df.iloc[idx].get("critical_checks_json")
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

    dec_counts = pd.Series(decisions).value_counts().to_dict()
    return {
        "HIGH_CONFIDENCE": dec_counts.get("HIGH_CONFIDENCE", 0),
        "REVIEW": dec_counts.get("REVIEW", 0),
        "DIFFERENT": dec_counts.get("DIFFERENT", 0),
        "total": len(decisions),
    }


def run_full_experiment(
    dev_path: str = "data/evaluation/features/dev_features.csv",
    heldout_path: str = "data/evaluation/features/heldout_features.csv",
    hard_neg_path: str = "data/evaluation/features/hard_negatives_features.csv",
) -> Dict[str, Any]:
    """Execute corrected, regularized learned-weight experiment on 5,228 DEV and 5,284 HELDOUT."""
    X_dev, y_dev, df_dev = load_dataset_matrix(dev_path)
    X_held, y_held, df_held = load_dataset_matrix(heldout_path)
    X_hard, y_hard, df_hard = load_dataset_matrix(hard_neg_path)

    # Identify DEV hard negatives for the HN-aware penalty
    hn_mask = (y_dev == 0) & (df_dev["pair_type"].isin(["HN_CORRUPT", "HN_SIBLING", "HN_SPECS"]))
    hn_indices = np.where(hn_mask)[0]

    # 1. Baseline
    configs: Dict[str, np.ndarray] = {
        "baseline": BASELINE_WEIGHTS.copy(),
    }

    # 2. Unregularized Learned
    unreg_res = optimize_weights(X_dev, y_dev, lambda_reg=0.0)
    configs["unregularized"] = unreg_res["weights"]

    # 3. Regularization Grid
    reg_grid_lambdas = [0.01, 0.05, 0.10, 0.25, 0.50, 1.00]
    reg_results: Dict[str, Any] = {}
    for lam in reg_grid_lambdas:
        res = optimize_weights(X_dev, y_dev, lambda_reg=lam)
        key = f"regularized_lambda_{lam:.2f}"
        configs[key] = res["weights"]
        reg_results[key] = {
            "lambda_reg": lam,
            "weights": [round(float(v), 4) for v in res["weights"]],
            "loss": round(float(res["loss"]), 6),
            "converged": res["success"],
        }

    # 4. Regularized + Hard-Negative Penalty Grid
    hn_penalty_lambdas = [0.10, 0.50, 1.00, 2.00]
    hn_results: Dict[str, Any] = {}
    for l_hn in hn_penalty_lambdas:
        res_hn = optimize_weights(
            X_dev, y_dev, lambda_reg=0.10, lambda_hn=l_hn, hn_indices=hn_indices
        )
        key = f"reg_0.10_hn_{l_hn:.2f}"
        configs[key] = res_hn["weights"]
        hn_results[key] = {
            "lambda_reg": 0.10,
            "lambda_hn": l_hn,
            "weights": [round(float(v), 4) for v in res_hn["weights"]],
            "loss": round(float(res_hn["loss"]), 6),
            "converged": res_hn["success"],
        }

    # Evaluate each configuration across DEV, HELDOUT, and 300 Hard Negatives
    eval_results: Dict[str, Any] = {}
    for name, w in configs.items():
        dev_m = compute_dataset_metrics(X_dev, y_dev, w)
        held_m = compute_dataset_metrics(X_held, y_held, w)
        hard_m = compute_hard_negative_stats(X_hard, w, df_hard=df_hard)

        dev_dec = evaluate_mira_decision_pipeline(X_dev, df_dev, w)
        held_dec = evaluate_mira_decision_pipeline(X_held, df_held, w)
        hard_dec = evaluate_mira_decision_pipeline(X_hard, df_hard, w)

        eval_results[name] = {
            "weights": [round(float(v), 4) for v in w],
            "DEV": {
                "metrics": dev_m,
                "decisions": dev_dec,
            },
            "HELDOUT": {
                "metrics": held_m,
                "decisions": held_dec,
            },
            "HARD_NEGATIVES_300": {
                "metrics": hard_m,
                "decisions": hard_dec,
            },
        }

    report = {
        "experiment_name": "Corrected MIRA Learned-Weight Experiment (Production-Parity 5,228 DEV / 5,284 HELDOUT)",
        "dataset_summary": {
            "DEV": {
                "total": len(X_dev),
                "positive_count": int(np.sum(y_dev == 1)),
                "negative_count": int(np.sum(y_dev == 0)),
                "hard_negative_count": int(len(hn_indices)),
            },
            "HELDOUT": {
                "total": len(X_held),
                "positive_count": int(np.sum(y_held == 1)),
                "negative_count": int(np.sum(y_held == 0)),
            },
            "HARD_NEGATIVES_300": {
                "total": len(X_hard),
                "positive_count": 0,
                "negative_count": len(X_hard),
            },
        },
        "baseline_weights": [round(float(v), 4) for v in BASELINE_WEIGHTS],
        "regularization_grid": reg_results,
        "hn_penalty_grid": hn_results,
        "configurations_evaluated": eval_results,
    }

    # Save to report artifact
    out_json = Path("data/evaluation/learned_weights_experiment_report.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Report successfully written to {out_json}")

    return report


if __name__ == "__main__":
    rep = run_full_experiment()
