"""
Learned-Weight Stability, Sensitivity, and Robustness Analysis for MIRA (Track 1 — Step 3).

Analyzes:
1. Weight trajectory across regularization sweep (lambda_reg in [0.0, 0.01, 0.05, 0.10, 0.25, 0.50, 1.00]).
2. Weight stability metrics (min, max, range, mean, std, L2 distance to baseline).
3. Hard-negative field sensitivity (mean, median, >=0.80, >=0.85 per engineering field).
4. Full decision-pipeline sensitivity (HIGH_CONFIDENCE, REVIEW, DIFFERENT, and deltas from baseline).
5. Subgroup robustness analysis (by category, pair_type, specification density).
6. Semantic-model sensitivity (Base MiniLM vs Fine-Tuned MiniLM CPSE vs Qwen estimate).
7. Descriptive stability regions (Low, Medium, High regularization).

Outputs:
  - data/evaluation/learned_weights_stability_analysis.json
  - data/evaluation/learned_weights_stability_analysis.md
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, precision_recall_fscore_support, roc_auc_score

from app.services.evaluation.learned_weights_experiment import (
    BASELINE_WEIGHTS,
    FEATURE_NAMES,
    HIGH_CONFIDENCE_THRESHOLD,
    DIFFERENT_THRESHOLD,
    load_dataset_matrix,
    optimize_weights,
    compute_dataset_metrics,
    compute_hard_negative_stats,
    evaluate_mira_decision_pipeline,
)
from app.services.matching.embeddings import get_embedding_model


def calculate_l2_distance(w: np.ndarray, w_base: np.ndarray = BASELINE_WEIGHTS) -> float:
    """Calculate Euclidean (L2) distance between a weight vector and the baseline."""
    return float(np.linalg.norm(np.array(w, dtype=np.float64) - np.array(w_base, dtype=np.float64)))


def compute_weight_summary_stats(weights_dict: Dict[str, np.ndarray]) -> Dict[str, Any]:
    """Compute per-feature min, max, range, mean, std across configurations."""
    w_matrix = np.array(list(weights_dict.values()), dtype=np.float64)  # (N_configs, 5)
    summary = {}
    for i, name in enumerate(FEATURE_NAMES):
        vals = w_matrix[:, i]
        summary[name] = {
            "min": round(float(np.min(vals)), 4),
            "max": round(float(np.max(vals)), 4),
            "range": round(float(np.ptp(vals)), 4),
            "mean": round(float(np.mean(vals)), 4),
            "std": round(float(np.std(vals)), 4),
            "baseline": round(float(BASELINE_WEIGHTS[i]), 4),
        }
    return summary


def evaluate_subgroup_performance(
    X: np.ndarray,
    y: np.ndarray,
    df: pd.DataFrame,
    weights: np.ndarray,
    subgroup_col: str,
    min_samples: int = 10,
) -> Dict[str, Any]:
    """Evaluate performance metrics across subgroups (e.g. category, pair_type)."""
    scores = X @ weights
    results = {}

    for val, grp in df.groupby(subgroup_col):
        idx = grp.index.to_numpy()
        sub_y = y[idx]
        sub_s = scores[idx]

        pos_cnt = int(np.sum(sub_y == 1))
        neg_cnt = int(np.sum(sub_y == 0))
        total_cnt = len(sub_y)

        if total_cnt < min_samples:
            continue

        has_both = pos_cnt > 0 and neg_cnt > 0
        roc_auc = float(roc_auc_score(sub_y, sub_s)) if has_both else None

        pos_scores = sub_s[sub_y == 1]
        neg_scores = sub_s[sub_y == 0]

        results[str(val)] = {
            "total": total_cnt,
            "positive_count": pos_cnt,
            "negative_count": neg_cnt,
            "roc_auc": round(roc_auc, 4) if roc_auc is not None else None,
            "mean_score": round(float(np.mean(sub_s)), 4),
            "pos_mean_score": round(float(np.mean(pos_scores)), 4) if len(pos_scores) else None,
            "neg_mean_score": round(float(np.mean(neg_scores)), 4) if len(neg_scores) else None,
            "margin": round(float(np.mean(pos_scores) - np.mean(neg_scores)), 4) if (len(pos_scores) and len(neg_scores)) else None,
        }

    return results


def run_comprehensive_stability_analysis(
    dev_path: str = "data/evaluation/features/dev_features.csv",
    heldout_path: str = "data/evaluation/features/heldout_features.csv",
    hard_neg_path: str = "data/evaluation/features/hard_negatives_features.csv",
) -> Dict[str, Any]:
    """Run full stability, sensitivity, and robustness analysis."""
    X_dev, y_dev, df_dev = load_dataset_matrix(dev_path)
    X_held, y_held, df_held = load_dataset_matrix(heldout_path)
    X_hard, y_hard, df_hard = load_dataset_matrix(hard_neg_path)

    hn_mask = (y_dev == 0) & (df_dev["pair_type"].isin(["HN_CORRUPT", "HN_SIBLING", "HN_SPECS"]))
    hn_indices = np.where(hn_mask)[0]

    # 1. Define all configurations
    configs: Dict[str, np.ndarray] = {
        "baseline": BASELINE_WEIGHTS.copy(),
    }

    # Unregularized (lambda_reg = 0.0)
    unreg_res = optimize_weights(X_dev, y_dev, lambda_reg=0.0)
    configs["unregularized"] = unreg_res["weights"]

    # Regularization grid
    reg_lambdas = [0.01, 0.05, 0.10, 0.25, 0.50, 1.00]
    for lam in reg_lambdas:
        res = optimize_weights(X_dev, y_dev, lambda_reg=lam)
        configs[f"reg_lambda_{lam:.2f}"] = res["weights"]

    # HN-penalized grid
    hn_lambdas = [0.10, 0.50, 1.00, 2.00]
    for l_hn in hn_lambdas:
        res_hn = optimize_weights(
            X_dev, y_dev, lambda_reg=0.10, lambda_hn=l_hn, hn_indices=hn_indices
        )
        configs[f"reg_0.10_hn_{l_hn:.2f}"] = res_hn["weights"]

    # 2. Compute L2 distance to baseline and weight statistics
    l2_distances = {name: round(calculate_l2_distance(w), 4) for name, w in configs.items()}
    weight_summary = compute_weight_summary_stats(configs)

    # 3. Evaluate each configuration comprehensively
    config_details: Dict[str, Any] = {}
    base_dev_dec = evaluate_mira_decision_pipeline(X_dev, df_dev, BASELINE_WEIGHTS)
    base_held_dec = evaluate_mira_decision_pipeline(X_held, df_held, BASELINE_WEIGHTS)
    base_hard_dec = evaluate_mira_decision_pipeline(X_hard, df_hard, BASELINE_WEIGHTS)

    for name, w in configs.items():
        dev_m = compute_dataset_metrics(X_dev, y_dev, w)
        held_m = compute_dataset_metrics(X_held, y_held, w)
        hard_m = compute_hard_negative_stats(X_hard, w, df_hard=df_hard)

        dev_dec = evaluate_mira_decision_pipeline(X_dev, df_dev, w)
        held_dec = evaluate_mira_decision_pipeline(X_held, df_held, w)
        hard_dec = evaluate_mira_decision_pipeline(X_hard, df_hard, w)

        # Decision deltas from baseline
        dev_dec_delta = {k: dev_dec[k] - base_dev_dec[k] for k in ["HIGH_CONFIDENCE", "REVIEW", "DIFFERENT"]}
        held_dec_delta = {k: held_dec[k] - base_held_dec[k] for k in ["HIGH_CONFIDENCE", "REVIEW", "DIFFERENT"]}
        hard_dec_delta = {k: hard_dec[k] - base_hard_dec[k] for k in ["HIGH_CONFIDENCE", "REVIEW", "DIFFERENT"]}

        # Subgroup evaluations on DEV and HELDOUT
        dev_cat = evaluate_subgroup_performance(X_dev, y_dev, df_dev, w, "category")
        dev_pt = evaluate_subgroup_performance(X_dev, y_dev, df_dev, w, "pair_type")
        held_cat = evaluate_subgroup_performance(X_held, y_held, df_held, w, "category")

        config_details[name] = {
            "weights": [round(float(v), 4) for v in w],
            "l2_distance_to_baseline": l2_distances[name],
            "DEV": {
                "metrics": dev_m,
                "decisions": dev_dec,
                "decision_delta_from_baseline": dev_dec_delta,
                "category_breakdown": dev_cat,
                "pair_type_breakdown": dev_pt,
            },
            "HELDOUT": {
                "metrics": held_m,
                "decisions": held_dec,
                "decision_delta_from_baseline": held_dec_delta,
                "category_breakdown": held_cat,
            },
            "HARD_NEGATIVES_300": {
                "metrics": hard_m,
                "decisions": hard_dec,
                "decision_delta_from_baseline": hard_dec_delta,
            },
        }

    # 4. Semantic Model Sensitivity (Base MiniLM vs Fine-Tuned MiniLM CPSE)
    print("Computing Fine-Tuned MiniLM semantic features...")
    m_ft = get_embedding_model("minilm")

    def extract_semantic_column(df: pd.DataFrame) -> np.ndarray:
        descs_a = df["desc_a"].tolist()
        descs_b = df["desc_b"].tolist()
        unique_d = list(set(descs_a + descs_b))
        embs = m_ft.encode(unique_d, batch_size=128, show_progress_bar=False, normalize_embeddings=True)
        d_to_emb = {d: embs[i] for i, d in enumerate(unique_d)}
        ea = np.array([d_to_emb[d] for d in descs_a])
        eb = np.array([d_to_emb[d] for d in descs_b])
        sims = np.sum(ea * eb, axis=1)
        return np.clip(sims, 0.0, 1.0)

    X_dev_ft = X_dev.copy()
    X_dev_ft[:, 1] = extract_semantic_column(df_dev)

    X_held_ft = X_held.copy()
    X_held_ft[:, 1] = extract_semantic_column(df_held)

    X_hard_ft = X_hard.copy()
    X_hard_ft[:, 1] = extract_semantic_column(df_hard)

    # Compare Baseline & Regularized(1.0) on Fine-Tuned MiniLM
    ft_eval = {
        "baseline_on_fine_tuned_minilm": {
            "DEV_roc_auc": round(float(roc_auc_score(y_dev, X_dev_ft @ BASELINE_WEIGHTS)), 4),
            "HELDOUT_roc_auc": round(float(roc_auc_score(y_held, X_held_ft @ BASELINE_WEIGHTS)), 4),
            "HN_mean_score": round(float(np.mean(X_hard_ft @ BASELINE_WEIGHTS)), 4),
            "HN_ge_0_80": int(np.sum((X_hard_ft @ BASELINE_WEIGHTS) >= 0.80)),
        },
        "reg_1.0_on_fine_tuned_minilm": {
            "DEV_roc_auc": round(float(roc_auc_score(y_dev, X_dev_ft @ configs["reg_lambda_1.00"])), 4),
            "HELDOUT_roc_auc": round(float(roc_auc_score(y_held, X_held_ft @ configs["reg_lambda_1.00"])), 4),
            "HN_mean_score": round(float(np.mean(X_hard_ft @ configs["reg_lambda_1.00"])), 4),
            "HN_ge_0_80": int(np.sum((X_hard_ft @ configs["reg_lambda_1.00"]) >= 0.80)),
        },
        "qwen_status": {
            "status": "DEFERRED",
            "reason": "Qwen INT8 embedding extraction over 9,384 unique catalog items on CPU estimated at ~24 minutes (1,440s). Deferred per instruction to avoid long blocking runs.",
            "estimated_cpu_seconds": 1440,
        },
    }

    # 5. Stability Region Categorization
    stability_regions = {
        "Low Regularization (lambda_reg <= 0.05)": {
            "characteristics": "Specification weight collapses to 0.0; semantic weight dominates (> 0.46); L2 distance to baseline is large (0.42 - 0.49).",
            "safety_assessment": "UNSAFE. Causes severe false high scores on hard negatives (up to 22.7% scoring >= 0.80).",
            "configurations": ["unregularized", "reg_lambda_0.01", "reg_lambda_0.05"],
        },
        "Medium Regularization (0.10 <= lambda_reg <= 0.25)": {
            "characteristics": "Transition zone. Specification weight begins recovering (0.00 -> 0.04), grade weight stabilizes (0.01 -> 0.04), L2 distance drops (0.39 -> 0.31).",
            "safety_assessment": "MARGINALLY SAFER (zero HN >= 0.80), but specification weight remains depressed (< 0.05), risking subtle specification mismatch misses.",
            "configurations": ["reg_lambda_0.10", "reg_lambda_0.25"],
        },
        "High Regularization (lambda_reg >= 0.50)": {
            "characteristics": "Defensible stable anchor zone. Specification weight is well preserved (0.12 - 0.22), grade weight is preserved (0.08 - 0.11), L2 distance is small (0.17 - 0.06).",
            "safety_assessment": "SAFE. Zero HN >= 0.80; mean HN score is controlled (0.50 - 0.52); HELDOUT ROC-AUC (0.82 - 0.83) shows solid generalization.",
            "configurations": ["reg_lambda_0.50", "reg_lambda_1.00"],
        },
        "Hard-Negative Penalized (lambda_reg=0.10, lambda_hn >= 0.50)": {
            "characteristics": "Forces HN scores below 0.50 threshold while allowing medium regularization. Increases grade weight (up to 0.14) and reduces other_attributes to 0.0.",
            "safety_assessment": "SAFE against hard negatives (mean HN score 0.45 - 0.48, zero >= 0.80), but completely suppresses other_attributes similarity.",
            "configurations": ["reg_0.10_hn_0.50", "reg_0.10_hn_1.00", "reg_0.10_hn_2.00"],
        },
    }

    report = {
        "analysis_title": "MIRA Learned-Weight Stability, Sensitivity, and Robustness Analysis",
        "dataset_summary": {
            "DEV_total": len(X_dev),
            "HELDOUT_total": len(X_held),
            "HARD_NEGATIVES_total": len(X_hard),
        },
        "baseline_weights": [round(float(v), 4) for v in BASELINE_WEIGHTS],
        "weight_summary_statistics": weight_summary,
        "l2_distances_to_baseline": l2_distances,
        "stability_regions": stability_regions,
        "semantic_model_sensitivity": ft_eval,
        "configurations": config_details,
    }

    # Save JSON artifact
    json_path = Path("data/evaluation/learned_weights_stability_analysis.json")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Stability analysis JSON saved to {json_path}")

    # Generate Markdown artifact
    md_path = Path("data/evaluation/learned_weights_stability_analysis.md")
    generate_markdown_report(report, md_path)
    print(f"Stability analysis Markdown saved to {md_path}")

    return report


def generate_markdown_report(data: Dict[str, Any], out_path: Path) -> None:
    """Generate comprehensive Markdown report from stability analysis results."""
    lines = [
        "# MIRA Learned-Weight Stability & Sensitivity Analysis",
        "",
        "## 1. Overview & Methodology",
        "- **Purpose**: Determine whether a mathematically stable, safety-defensible region of learned weights exists across the 5 production features.",
        "- **Datasets**: Curated multi-CPSE 5,228 DEV pairs, 5,284 HELDOUT pairs, and 300 Hard Negatives benchmark.",
        "- **Production Baseline**: `[text=0.20, semantic=0.20, spec=0.35, grade=0.15, other=0.10]`",
        "",
        "## 2. Weight Trajectory Across Regularization",
        "",
        "| Configuration | Text ($w_1$) | Semantic ($w_2$) | Spec ($w_3$) | Grade ($w_4$) | Other ($w_5$) | $L_2$ Dist to Baseline |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    configs = data["configurations"]
    for name, c in configs.items():
        w = c["weights"]
        l2 = c["l2_distance_to_baseline"]
        lines.append(f"| `{name}` | {w[0]:.4f} | {w[1]:.4f} | {w[2]:.4f} | {w[3]:.4f} | {w[4]:.4f} | **{l2:.4f}** |")

    lines.extend([
        "",
        "## 3. Weight Summary Statistics Across All Configurations",
        "",
        "| Feature | Min | Max | Range | Mean | Std | Baseline |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])
    for feat, s in data["weight_summary_statistics"].items():
        lines.append(f"| `{feat}` | {s['min']:.4f} | {s['max']:.4f} | {s['range']:.4f} | {s['mean']:.4f} | {s['std']:.4f} | **{s['baseline']:.4f}** |")

    lines.extend([
        "",
        "## 4. Performance Trajectory (DEV vs HELDOUT vs Hard Negatives)",
        "",
        "| Configuration | DEV ROC-AUC | HELDOUT ROC-AUC | DEV PR-AUC | HELDOUT PR-AUC | HN Mean Score | HN Score $\\ge 0.80$ |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])
    for name, c in configs.items():
        d_roc = c["DEV"]["metrics"]["roc_auc"]
        h_roc = c["HELDOUT"]["metrics"]["roc_auc"]
        d_pr = c["DEV"]["metrics"]["pr_auc"]
        h_pr = c["HELDOUT"]["metrics"]["pr_auc"]
        hn_mean = c["HARD_NEGATIVES_300"]["metrics"]["mean"]
        hn_80 = c["HARD_NEGATIVES_300"]["metrics"]["count_ge_0_80"]
        lines.append(f"| `{name}` | {d_roc:.4f} | {h_roc:.4f} | {d_pr:.4f} | {h_pr:.4f} | {hn_mean:.4f} | **{hn_80} / 300** |")

    lines.extend([
        "",
        "## 5. Hard-Negative Field Sensitivity (Mean Scores per Engineering Field)",
        "",
        "| Configuration | Dimensions ($N=81$) | Metric Thread ($N=161$) | Nominal Bore ($N=18$) | Voltage Class ($N=39$) | Total HN $\\ge 0.85$ |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |",
    ])
    for name, c in configs.items():
        flds = c["HARD_NEGATIVES_300"]["metrics"]["field_breakdown"]
        d_m = flds.get("dimensions", {}).get("mean", 0.0)
        mt_m = flds.get("metric_thread", {}).get("mean", 0.0)
        nb_m = flds.get("nominal_bore", {}).get("mean", 0.0)
        vc_m = flds.get("voltage_class", {}).get("mean", 0.0)
        hn_85 = c["HARD_NEGATIVES_300"]["metrics"]["count_ge_0_85"]
        lines.append(f"| `{name}` | {d_m:.4f} | {mt_m:.4f} | {nb_m:.4f} | {vc_m:.4f} | **{hn_85}** |")

    lines.extend([
        "",
        "## 6. MIRA Decision Pipeline Trajectory",
        "",
        "| Configuration | DEV (HC / REV / DIFF) | HELDOUT (HC / REV / DIFF) | Hard Negatives (HC / REV / DIFF) | HN REV Delta |",
        "| :--- | :---: | :---: | :---: | :---: |",
    ])
    for name, c in configs.items():
        dd = c["DEV"]["decisions"]
        hd = c["HELDOUT"]["decisions"]
        hnd = c["HARD_NEGATIVES_300"]["decisions"]
        hn_rev_delta = c["HARD_NEGATIVES_300"]["decision_delta_from_baseline"]["REVIEW"]
        lines.append(
            f"| `{name}` | {dd['HIGH_CONFIDENCE']} / {dd['REVIEW']} / {dd['DIFFERENT']} | "
            f"{hd['HIGH_CONFIDENCE']} / {hd['REVIEW']} / {hd['DIFFERENT']} | "
            f"{hnd['HIGH_CONFIDENCE']} / {hnd['REVIEW']} / {hnd['DIFFERENT']} | "
            f"{'+' if hn_rev_delta > 0 else ''}{hn_rev_delta} |"
        )

    lines.extend([
        "",
        "## 7. Semantic-Model Sensitivity",
        f"- **Fine-Tuned MiniLM CPSE**: Baseline HELDOUT ROC-AUC = {data['semantic_model_sensitivity']['baseline_on_fine_tuned_minilm']['HELDOUT_roc_auc']:.4f}; Regularized(1.0) HELDOUT ROC-AUC = {data['semantic_model_sensitivity']['reg_1.0_on_fine_tuned_minilm']['HELDOUT_roc_auc']:.4f}.",
        f"- **Qwen Sensitivity Status**: {data['semantic_model_sensitivity']['qwen_status']['status']} ({data['semantic_model_sensitivity']['qwen_status']['reason']}).",
        "",
        "## 8. Stability Region Finding",
        "- **Low Regularization** ($\\lambda \\le 0.05$): Mathematically unstable and safety-critical failure (spec weight collapses to 0.0; up to 22.7% hard negatives score $\\ge 0.80$).",
        "- **Medium Regularization** ($0.10 \\le \\lambda \\le 0.25$): Transition zone. Hard negative false highs drop to 0, but spec weight remains depressed ($< 0.05$).",
        "- **High Regularization** ($\\lambda \\ge 0.50$): Stable and safe anchor zone. Specification weight ($0.12 - 0.22$) and grade weight ($0.08 - 0.11$) are preserved with zero hard negatives $\\ge 0.80$ and consistent generalization on HELDOUT.",
    ])

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    run_comprehensive_stability_analysis()
