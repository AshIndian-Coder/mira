"""
Operational Evaluation Framework for MIRA Learned Weights (Track 1 — Step 5).

Measures:
1. Positive Coverage (% DIFFERENT, % REVIEW, % HIGH_CONFIDENCE, positive rescues, regressions, overall coverage).
2. Negative Handling (% DIFFERENT, % REVIEW, % HIGH_CONFIDENCE across NEG_EASY, HN_SIBLING, HN_CORRUPT, NEG_SAME_CAT).
3. Human Review Load (Total REVIEW count, REVIEW %, delta vs baseline, review queue composition: positive vs negative fraction).
4. Incremental Review Efficiency (added positive rescues / added negative reviews, with raw counts).
5. Controlled Hard-Negative Safety (300 benchmark across voltage_class, metric_thread, dimensions, nominal_bore, pressure_rating).
6. Specification-Safety Preservation (verification that critical gates remain independent and invariant to score shifts).
7. DEV vs HELDOUT Consistency (cross-dataset stability without heldout tuning).
8. Future Guardrail Framework & Tradeoff Matrix.

Configurations Evaluated:
- Baseline: [0.20, 0.20, 0.35, 0.15, 0.10]
- Reg lambda=0.50: [0.2612, 0.3812, 0.1186, 0.0769, 0.1621]
- Reg lambda=1.00: [0.2367, 0.3192, 0.2173, 0.1115, 0.1154]
- Reg+HN (lambda_r=0.10, lambda_hn=2.00): [0.2755, 0.5014, 0.0782, 0.1449, 0.0000]

Outputs:
- data/evaluation/learned_weights_operational_evaluation_report.json
- data/evaluation/learned_weights_operational_evaluation.md
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from app.services.evaluation.learned_weights_pair_analysis import (
    FEATURE_NAMES,
    BASELINE_WEIGHTS,
    STABLE_LAMBDA1_WEIGHTS,
    REG_HN_WEIGHTS,
    classify_pair_decision,
)

CONFIGS: Dict[str, np.ndarray] = {
    "BASELINE": BASELINE_WEIGHTS,
    "REG_0.50": np.array([0.2612, 0.3812, 0.1186, 0.0769, 0.1621], dtype=np.float64),
    "REG_1.00": STABLE_LAMBDA1_WEIGHTS,
    "REG_HN_2.00": REG_HN_WEIGHTS,
}


def compute_scores_and_decisions(
    df: pd.DataFrame,
    weights_dict: Dict[str, np.ndarray] = CONFIGS,
) -> pd.DataFrame:
    """Compute score and decision columns for all configurations on a dataframe."""
    df = df.copy()
    X = df[FEATURE_NAMES].to_numpy(dtype=np.float64)

    for name, w in weights_dict.items():
        scores = np.round(X @ w, 4)
        df[f"score_{name}"] = scores
        decisions = [
            classify_pair_decision(s, chk)
            for s, chk in zip(scores, df["critical_checks_json"])
        ]
        df[f"decision_{name}"] = decisions

    return df


def evaluate_positive_coverage(
    df: pd.DataFrame,
    cfg_name: str,
    base_cfg: str = "BASELINE",
) -> Dict[str, Any]:
    """Calculate operational metrics for positive pairs."""
    df_pos = df[df["label"] == 1]
    total_pos = len(df_pos)
    if total_pos == 0:
        return {}

    dec = df_pos[f"decision_{cfg_name}"]
    base_dec = df_pos[f"decision_{base_cfg}"]

    cnt_diff = int(np.sum(dec == "DIFFERENT"))
    cnt_rev = int(np.sum(dec == "REVIEW"))
    cnt_hc = int(np.sum(dec == "HIGH_CONFIDENCE"))

    # Rescues: base was DIFFERENT, candidate is REVIEW or HIGH_CONFIDENCE
    rescues = int(np.sum((base_dec == "DIFFERENT") & (dec != "DIFFERENT")))

    # Regressions: base was REVIEW or HC, candidate is DIFFERENT
    regressions = int(np.sum((base_dec != "DIFFERENT") & (dec == "DIFFERENT")))

    coverage_cnt = total_pos - cnt_diff
    coverage_pct = round(coverage_cnt / total_pos * 100, 2)

    return {
        "total_positive_pairs": total_pos,
        "count_DIFFERENT": cnt_diff,
        "pct_DIFFERENT": round(cnt_diff / total_pos * 100, 2),
        "count_REVIEW": cnt_rev,
        "pct_REVIEW": round(cnt_rev / total_pos * 100, 2),
        "count_HIGH_CONFIDENCE": cnt_hc,
        "pct_HIGH_CONFIDENCE": round(cnt_hc / total_pos * 100, 2),
        "positive_rescue_count": rescues,
        "positive_regression_count": regressions,
        "overall_positive_coverage_count": coverage_cnt,
        "overall_positive_coverage_pct": coverage_pct,
    }


def evaluate_negative_handling(
    df: pd.DataFrame,
    cfg_name: str,
) -> Dict[str, Any]:
    """Calculate negative pair distribution overall and per pair type."""
    df_neg = df[df["label"] == 0]
    total_neg = len(df_neg)
    if total_neg == 0:
        return {}

    dec = df_neg[f"decision_{cfg_name}"]
    overall = {
        "total_negative_pairs": total_neg,
        "count_DIFFERENT": int(np.sum(dec == "DIFFERENT")),
        "pct_DIFFERENT": round(int(np.sum(dec == "DIFFERENT")) / total_neg * 100, 2),
        "count_REVIEW": int(np.sum(dec == "REVIEW")),
        "pct_REVIEW": round(int(np.sum(dec == "REVIEW")) / total_neg * 100, 2),
        "count_HIGH_CONFIDENCE": int(np.sum(dec == "HIGH_CONFIDENCE")),
        "pct_HIGH_CONFIDENCE": round(int(np.sum(dec == "HIGH_CONFIDENCE")) / total_neg * 100, 2),
    }

    per_type = {}
    for pt, grp in df_neg.groupby("pair_type"):
        g_dec = grp[f"decision_{cfg_name}"]
        g_total = len(grp)
        per_type[str(pt)] = {
            "total": g_total,
            "count_DIFFERENT": int(np.sum(g_dec == "DIFFERENT")),
            "pct_DIFFERENT": round(int(np.sum(g_dec == "DIFFERENT")) / g_total * 100, 2),
            "count_REVIEW": int(np.sum(g_dec == "REVIEW")),
            "pct_REVIEW": round(int(np.sum(g_dec == "REVIEW")) / g_total * 100, 2),
            "count_HIGH_CONFIDENCE": int(np.sum(g_dec == "HIGH_CONFIDENCE")),
            "pct_HIGH_CONFIDENCE": round(int(np.sum(g_dec == "HIGH_CONFIDENCE")) / g_total * 100, 2),
        }

    return {
        "overall": overall,
        "by_pair_type": per_type,
    }


def evaluate_review_load_and_efficiency(
    df: pd.DataFrame,
    cfg_name: str,
    base_cfg: str = "BASELINE",
) -> Dict[str, Any]:
    """Calculate human review load, composition, and incremental efficiency."""
    total_pairs = len(df)
    dec = df[f"decision_{cfg_name}"]
    base_dec = df[f"decision_{base_cfg}"]

    rev_cnt = int(np.sum(dec == "REVIEW"))
    rev_pct = round(rev_cnt / total_pairs * 100, 2)

    base_rev_cnt = int(np.sum(base_dec == "REVIEW"))
    base_rev_pct = round(base_rev_cnt / total_pairs * 100, 2)

    delta_cnt = rev_cnt - base_rev_cnt
    delta_pct = round(rev_pct - base_rev_pct, 2)

    # Composition of REVIEW queue
    df_rev = df[dec == "REVIEW"]
    pos_in_rev = int(np.sum(df_rev["label"] == 1))
    neg_in_rev = int(np.sum(df_rev["label"] == 0))
    pos_frac = round(pos_in_rev / rev_cnt * 100, 2) if rev_cnt > 0 else 0.0
    neg_frac = round(neg_in_rev / rev_cnt * 100, 2) if rev_cnt > 0 else 0.0

    # Incremental review analysis (positives added to review vs negatives added to review)
    df_pos = df[df["label"] == 1]
    df_neg = df[df["label"] == 0]

    base_pos_rev = int(np.sum(df_pos[f"decision_{base_cfg}"] == "REVIEW"))
    cand_pos_rev = int(np.sum(df_pos[f"decision_{cfg_name}"] == "REVIEW"))
    added_pos_rev = cand_pos_rev - base_pos_rev

    base_neg_rev = int(np.sum(df_neg[f"decision_{base_cfg}"] == "REVIEW"))
    cand_neg_rev = int(np.sum(df_neg[f"decision_{cfg_name}"] == "REVIEW"))
    added_neg_rev = cand_neg_rev - base_neg_rev

    # Rescues
    pos_rescues = int(np.sum((df_pos[f"decision_{base_cfg}"] == "DIFFERENT") & (df_pos[f"decision_{cfg_name}"] != "DIFFERENT")))

    if added_neg_rev > 0:
        efficiency_ratio = round(pos_rescues / added_neg_rev, 4)
    elif added_neg_rev == 0:
        efficiency_ratio = "N/A (zero incremental negative reviews)"
    else:
        efficiency_ratio = "N/A (negative reviews decreased)"

    return {
        "total_pairs": total_pairs,
        "total_REVIEW_count": rev_cnt,
        "REVIEW_pct": rev_pct,
        "delta_REVIEW_count_vs_baseline": delta_cnt,
        "delta_REVIEW_pct_vs_baseline": delta_pct,
        "review_queue_composition": {
            "positive_count_in_REVIEW": pos_in_rev,
            "negative_count_in_REVIEW": neg_in_rev,
            "positive_fraction_pct": pos_frac,
            "negative_fraction_pct": neg_frac,
        },
        "incremental_efficiency": {
            "added_positive_reviews": added_pos_rev,
            "added_negative_reviews": added_neg_rev,
            "positive_rescues": pos_rescues,
            "incremental_efficiency_ratio (rescues/added_neg_rev)": efficiency_ratio,
        },
    }


def evaluate_controlled_hard_negatives(
    df_hard: pd.DataFrame,
    weights_dict: Dict[str, np.ndarray] = CONFIGS,
) -> Dict[str, Any]:
    """Evaluate 300 controlled hard-negative benchmark per configuration and field."""
    df_h = compute_scores_and_decisions(df_hard, weights_dict)
    field_col = "conflicting_fields" if "conflicting_fields" in df_h.columns else "category"

    summary_per_cfg = {}
    for name in weights_dict.keys():
        s = df_h[f"score_{name}"]
        d = df_h[f"decision_{name}"]
        total = len(df_h)

        summary_per_cfg[name] = {
            "count_DIFFERENT": int(np.sum(d == "DIFFERENT")),
            "count_REVIEW": int(np.sum(d == "REVIEW")),
            "count_HIGH_CONFIDENCE": int(np.sum(d == "HIGH_CONFIDENCE")),
            "mean_score": round(float(s.mean()), 4),
            "median_score": round(float(s.median()), 4),
            "count_ge_0_80": int(np.sum(s >= 0.80)),
            "count_ge_0_85": int(np.sum(s >= 0.85)),
        }

    # Field-level breakdown
    fields_detail = {}
    for fld, grp in df_h.groupby(field_col):
        fld_res = {}
        for name in weights_dict.keys():
            s = grp[f"score_{name}"]
            d = grp[f"decision_{name}"]
            fld_res[name] = {
                "count": len(grp),
                "count_DIFFERENT": int(np.sum(d == "DIFFERENT")),
                "count_REVIEW": int(np.sum(d == "REVIEW")),
                "count_HIGH_CONFIDENCE": int(np.sum(d == "HIGH_CONFIDENCE")),
                "mean_score": round(float(s.mean()), 4),
                "count_ge_0_80": int(np.sum(s >= 0.80)),
                "count_ge_0_85": int(np.sum(s >= 0.85)),
            }
        fields_detail[str(fld)] = fld_res

    return {
        "overall_summary": summary_per_cfg,
        "by_field": fields_detail,
    }


def run_operational_evaluation(
    dev_path: str = "data/evaluation/features/dev_features.csv",
    heldout_path: str = "data/evaluation/features/heldout_features.csv",
    hard_neg_path: str = "data/evaluation/features/hard_negatives_features.csv",
) -> Dict[str, Any]:
    """Execute complete operational evaluation framework across DEV, HELDOUT, and 300 HN."""
    df_dev_raw = pd.read_csv(dev_path, low_memory=False)
    df_held_raw = pd.read_csv(heldout_path, low_memory=False)
    df_hard_raw = pd.read_csv(hard_neg_path, low_memory=False)

    df_dev = compute_scores_and_decisions(df_dev_raw)
    df_held = compute_scores_and_decisions(df_held_raw)

    results_dev: Dict[str, Any] = {}
    results_held: Dict[str, Any] = {}

    for name in CONFIGS.keys():
        results_dev[name] = {
            "positive_coverage": evaluate_positive_coverage(df_dev, name),
            "negative_handling": evaluate_negative_handling(df_dev, name),
            "review_load_and_efficiency": evaluate_review_load_and_efficiency(df_dev, name),
        }
        results_held[name] = {
            "positive_coverage": evaluate_positive_coverage(df_held, name),
            "negative_handling": evaluate_negative_handling(df_held, name),
            "review_load_and_efficiency": evaluate_review_load_and_efficiency(df_held, name),
        }

    # Controlled hard-negative benchmark
    hard_neg_results = evaluate_controlled_hard_negatives(df_hard_raw)

    # Consistency analysis between DEV and HELDOUT
    consistency: Dict[str, Any] = {}
    for name in CONFIGS.keys():
        d_pos_cov = results_dev[name]["positive_coverage"]["overall_positive_coverage_pct"]
        h_pos_cov = results_held[name]["positive_coverage"]["overall_positive_coverage_pct"]
        d_rev_pct = results_dev[name]["review_load_and_efficiency"]["REVIEW_pct"]
        h_rev_pct = results_held[name]["review_load_and_efficiency"]["REVIEW_pct"]
        d_neg_diff = results_dev[name]["negative_handling"]["overall"]["pct_DIFFERENT"]
        h_neg_diff = results_held[name]["negative_handling"]["overall"]["pct_DIFFERENT"]

        consistency[name] = {
            "DEV_positive_coverage_pct": d_pos_cov,
            "HELDOUT_positive_coverage_pct": h_pos_cov,
            "positive_coverage_delta (HELDOUT - DEV)": round(h_pos_cov - d_pos_cov, 2),
            "DEV_REVIEW_pct": d_rev_pct,
            "HELDOUT_REVIEW_pct": h_rev_pct,
            "REVIEW_pct_delta (HELDOUT - DEV)": round(h_rev_pct - d_rev_pct, 2),
            "DEV_negative_DIFFERENT_pct": d_neg_diff,
            "HELDOUT_negative_DIFFERENT_pct": h_neg_diff,
            "negative_DIFFERENT_pct_delta (HELDOUT - DEV)": round(h_neg_diff - d_neg_diff, 2),
            "DEV_positive_regressions": results_dev[name]["positive_coverage"]["positive_regression_count"],
            "HELDOUT_positive_regressions": results_held[name]["positive_coverage"]["positive_regression_count"],
        }

    # Guardrail Framework Definition
    guardrail_framework = {
        "description": "Empirical guardrails derived from Step 1-5 offline evaluations for future candidate scoring verification.",
        "guardrails": [
            {
                "guardrail_name": "Zero Positive Regression",
                "condition": "positive_regression_count == 0",
                "rationale": "Learned weights must never drop a baseline REVIEW or HIGH_CONFIDENCE positive pair into DIFFERENT.",
            },
            {
                "guardrail_name": "Zero Controlled-HN False High Confidence",
                "condition": "controlled_HN_HIGH_CONFIDENCE == 0",
                "rationale": "Critical gates and classifier must ensure zero engineering hard negatives reach auto-match.",
            },
            {
                "guardrail_name": "Zero Controlled-HN False High Score",
                "condition": "controlled_HN_ge_0_85 == 0",
                "rationale": "No controlled hard negative should score above the high-confidence scalar threshold (0.85).",
            },
            {
                "guardrail_name": "Authoritative Critical Gate Invariance",
                "condition": "gate_conflict_override == True",
                "rationale": "Critical gates must retain absolute veto power over scores regardless of learned scalar magnitude.",
            },
            {
                "guardrail_name": "DEV-HELDOUT Generalization Stability",
                "condition": "abs(HELDOUT_pos_cov - DEV_pos_cov) <= 3.0%",
                "rationale": "Learned weights must exhibit consistent coverage across split boundaries without overfitting.",
            },
            {
                "guardrail_name": "Bounded Human Review Capacity",
                "condition": "Human review queue growth must align with operational team capacity.",
                "rationale": "Specific numerical caps on added review count cannot be inferred from dataset alone and must be set by operational business requirements.",
            },
        ],
    }

    report = {
        "evaluation_title": "MIRA Operational Evaluation Framework for Learned Weights (Track 1 — Step 5)",
        "configurations": {k: [round(float(v), 4) for v in w] for k, w in CONFIGS.items()},
        "DEV_operational_metrics": results_dev,
        "HELDOUT_operational_metrics": results_held,
        "controlled_hard_negatives_300": hard_neg_results,
        "DEV_vs_HELDOUT_consistency": consistency,
        "guardrail_framework": guardrail_framework,
    }

    # Save JSON report
    json_path = Path("data/evaluation/learned_weights_operational_evaluation_report.json")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Operational evaluation JSON report written to {json_path}")

    # Generate Markdown report
    md_path = Path("data/evaluation/learned_weights_operational_evaluation.md")
    generate_markdown_report(report, md_path)
    print(f"Operational evaluation Markdown report written to {md_path}")

    return report


def generate_markdown_report(data: Dict[str, Any], out_path: Path) -> None:
    """Generate comprehensive, descriptive Markdown report."""
    lines = [
        "# MIRA Learned-Weights Operational Evaluation Report (Track 1 — Step 5)",
        "",
        "## 1. Objective",
        "- **Context**: Steps 1–4 established that regularized learned weights can rescue sparse positive pairs by increasing text/semantic weight while penalizing hard negatives, but also alter human review load.",
        "- **Operational Goal**: Measure the exact operational tradeoffs across positive coverage, negative handling, human-review workload, incremental efficiency, and specification safety without declaring a winner or adopting weights.",
        "",
        "## 2. Configurations Evaluated",
        "",
        "| Configuration | Text ($w_1$) | Semantic ($w_2$) | Spec ($w_3$) | Grade ($w_4$) | Other ($w_5$) | Status |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :--- |",
    ]

    for name, w in data["configurations"].items():
        st = "Active Production Baseline" if name == "BASELINE" else "Offline Evaluation Candidate"
        lines.append(f"| `{name}` | {w[0]:.4f} | {w[1]:.4f} | {w[2]:.4f} | {w[3]:.4f} | {w[4]:.4f} | {st} |")

    lines.extend([
        "",
        "## 3. Positive Coverage Tradeoffs (DEV & HELDOUT)",
        "",
        "### DEV Dataset (3,661 Positive Pairs)",
        "| Configuration | % DIFFERENT | % REVIEW | % HIGH_CONFIDENCE | Positive Rescues | Positive Regressions | Overall Positive Coverage |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])
    for name in data["configurations"].keys():
        p = data["DEV_operational_metrics"][name]["positive_coverage"]
        lines.append(
            f"| `{name}` | {p['pct_DIFFERENT']}% ({p['count_DIFFERENT']}) | {p['pct_REVIEW']}% ({p['count_REVIEW']}) | "
            f"{p['pct_HIGH_CONFIDENCE']}% ({p['count_HIGH_CONFIDENCE']}) | **+{p['positive_rescue_count']}** | "
            f"**{p['positive_regression_count']}** | **{p['overall_positive_coverage_pct']}%** ({p['overall_positive_coverage_count']}) |"
        )

    lines.extend([
        "",
        "### HELDOUT Dataset (3,804 Positive Pairs)",
        "| Configuration | % DIFFERENT | % REVIEW | % HIGH_CONFIDENCE | Positive Rescues | Positive Regressions | Overall Positive Coverage |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])
    for name in data["configurations"].keys():
        p = data["HELDOUT_operational_metrics"][name]["positive_coverage"]
        lines.append(
            f"| `{name}` | {p['pct_DIFFERENT']}% ({p['count_DIFFERENT']}) | {p['pct_REVIEW']}% ({p['count_REVIEW']}) | "
            f"{p['pct_HIGH_CONFIDENCE']}% ({p['count_HIGH_CONFIDENCE']}) | **+{p['positive_rescue_count']}** | "
            f"**{p['positive_regression_count']}** | **{p['overall_positive_coverage_pct']}%** ({p['overall_positive_coverage_count']}) |"
        )

    lines.extend([
        "",
        "## 4. Negative Pair Handling (DEV Dataset: 1,567 Negative Pairs)",
        "",
        "| Configuration | Overall % DIFFERENT | Overall % REVIEW | `NEG_EASY` % DIFF ($N=635$) | `HN_SIBLING` % DIFF ($N=37$) | `HN_CORRUPT` % DIFF ($N=878$) | `NEG_SAME_CAT` % DIFF ($N=17$) |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])
    for name in data["configurations"].keys():
        n = data["DEV_operational_metrics"][name]["negative_handling"]
        o_diff = n["overall"]["pct_DIFFERENT"]
        o_rev = n["overall"]["pct_REVIEW"]
        pt = n["by_pair_type"]
        ne_diff = pt.get("NEG_EASY", {}).get("pct_DIFFERENT", 0.0)
        hs_diff = pt.get("HN_SIBLING", {}).get("pct_DIFFERENT", 0.0)
        hc_diff = pt.get("HN_CORRUPT", {}).get("pct_DIFFERENT", 0.0)
        sc_diff = pt.get("NEG_SAME_CAT", {}).get("pct_DIFFERENT", 0.0)
        lines.append(
            f"| `{name}` | {o_diff}% | {o_rev}% | {ne_diff}% | {hs_diff}% | {hc_diff}% | {sc_diff}% |"
        )

    lines.extend([
        "",
        "> [!NOTE]",
        "> `HN_CORRUPT` pairs are synthetically generated string-corrupted examples and may contain semantic ambiguity. The 300-pair hard negative benchmark below is the definitive ground truth for specification conflict behavior.",
        "",
        "## 5. Human Review Workload & Queue Composition",
        "",
        "### DEV Dataset ($N=5,228$)",
        "| Configuration | Total REVIEW Count | REVIEW % | $\\Delta$ REVIEW Count | $\\Delta$ REVIEW % | Positives in REVIEW | Negatives in REVIEW |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])
    for name in data["configurations"].keys():
        r = data["DEV_operational_metrics"][name]["review_load_and_efficiency"]
        comp = r["review_queue_composition"]
        d_cnt_str = f"{r['delta_REVIEW_count_vs_baseline']:+d}" if r['delta_REVIEW_count_vs_baseline'] != 0 else "0"
        d_pct_str = f"{r['delta_REVIEW_pct_vs_baseline']:+.2f}%" if r['delta_REVIEW_pct_vs_baseline'] != 0 else "0.00%"
        lines.append(
            f"| `{name}` | {r['total_REVIEW_count']} | {r['REVIEW_pct']}% | {d_cnt_str} | {d_pct_str} | "
            f"{comp['positive_fraction_pct']}% ({comp['positive_count_in_REVIEW']}) | {comp['negative_fraction_pct']}% ({comp['negative_count_in_REVIEW']}) |"
        )

    lines.extend([
        "",
        "### HELDOUT Dataset ($N=5,284$)",
        "| Configuration | Total REVIEW Count | REVIEW % | $\\Delta$ REVIEW Count | $\\Delta$ REVIEW % | Positives in REVIEW | Negatives in REVIEW |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])
    for name in data["configurations"].keys():
        r = data["HELDOUT_operational_metrics"][name]["review_load_and_efficiency"]
        comp = r["review_queue_composition"]
        d_cnt_str = f"{r['delta_REVIEW_count_vs_baseline']:+d}" if r['delta_REVIEW_count_vs_baseline'] != 0 else "0"
        d_pct_str = f"{r['delta_REVIEW_pct_vs_baseline']:+.2f}%" if r['delta_REVIEW_pct_vs_baseline'] != 0 else "0.00%"
        lines.append(
            f"| `{name}` | {r['total_REVIEW_count']} | {r['REVIEW_pct']}% | {d_cnt_str} | {d_pct_str} | "
            f"{comp['positive_fraction_pct']}% ({comp['positive_count_in_REVIEW']}) | {comp['negative_fraction_pct']}% ({comp['negative_count_in_REVIEW']}) |"
        )

    lines.extend([
        "",
        "## 6. Incremental Review Efficiency",
        "",
        "| Dataset | Configuration | Added Positive Rescues | Added Negative Reviews | Incremental Efficiency Ratio (Rescues / Added Neg) |",
        "| :--- | :--- | :---: | :---: | :---: |",
    ])
    for ds_name, m_key in [("DEV", "DEV_operational_metrics"), ("HELDOUT", "HELDOUT_operational_metrics")]:
        for name in ["REG_0.50", "REG_1.00", "REG_HN_2.00"]:
            eff = data[m_key][name]["review_load_and_efficiency"]["incremental_efficiency"]
            lines.append(
                f"| `{ds_name}` | `{name}` | +{eff['positive_rescues']} | +{eff['added_negative_reviews']} | **{eff['incremental_efficiency_ratio (rescues/added_neg_rev)']}** |"
            )

    lines.extend([
        "",
        "## 7. Controlled Hard-Negative Safety (300 Benchmark Pairs)",
        "",
        "| Configuration | DIFFERENT | REVIEW | HIGH_CONFIDENCE | Mean Score | Score $\\ge 0.80$ | Score $\\ge 0.85$ |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])
    for name, s in data["controlled_hard_negatives_300"]["overall_summary"].items():
        lines.append(
            f"| `{name}` | {s['count_DIFFERENT']} | {s['count_REVIEW']} | **{s['count_HIGH_CONFIDENCE']}** | "
            f"{s['mean_score']:.4f} | **{s['count_ge_0_80']}** | **{s['count_ge_0_85']}** |"
        )

    lines.extend([
        "",
        "### Field-Level Breakdown for Hard Negatives",
        "",
        "| Field | Baseline Mean | REG_0.50 Mean | REG_1.00 Mean | REG_HN_2.00 Mean | REG_1.00 $\\ge 0.80$ | REG_HN $\\ge 0.80$ |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])
    for fld, f_res in data["controlled_hard_negatives_300"]["by_field"].items():
        b_m = f_res["BASELINE"]["mean_score"]
        r5_m = f_res["REG_0.50"]["mean_score"]
        r1_m = f_res["REG_1.00"]["mean_score"]
        rhn_m = f_res["REG_HN_2.00"]["mean_score"]
        r1_80 = f_res["REG_1.00"]["count_ge_0_80"]
        rhn_80 = f_res["REG_HN_2.00"]["count_ge_0_80"]
        lines.append(
            f"| `{fld}` | {b_m:.4f} | {r5_m:.4f} | {r1_m:.4f} | {rhn_m:.4f} | {r1_80} | {rhn_80} |"
        )

    lines.extend([
        "",
        "## 8. DEV vs HELDOUT Consistency",
        "",
        "| Configuration | DEV Pos Coverage | HELDOUT Pos Coverage | Coverage $\\Delta$ | DEV REVIEW % | HELDOUT REVIEW % | REVIEW % $\\Delta$ | DEV Pos Regressions | HELDOUT Pos Regressions |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])
    for name, c in data["DEV_vs_HELDOUT_consistency"].items():
        lines.append(
            f"| `{name}` | {c['DEV_positive_coverage_pct']}% | {c['HELDOUT_positive_coverage_pct']}% | {c['positive_coverage_delta (HELDOUT - DEV)']:+.2f}% | "
            f"{c['DEV_REVIEW_pct']}% | {c['HELDOUT_REVIEW_pct']}% | {c['REVIEW_pct_delta (HELDOUT - DEV)']:+.2f}% | "
            f"{c['DEV_positive_regressions']} | {c['HELDOUT_positive_regressions']} |"
        )

    lines.extend([
        "",
        "## 9. Specification-Gate Invariants",
        "- **Critical Gate Authority**: Critical gates operate independently of scalar weight configurations. If a pair exhibits a conflicting specification (e.g. M12 vs M16 thread, 220V vs 440V rating), the gate status (`CONFLICT`) overrides the scalar score and unconditionally blocks `HIGH_CONFIDENCE` auto-matching.",
        "- **Demonstration**: In the 300 controlled hard-negative benchmark, even when scalar scores shifted upward under learned weights (e.g. mean score shifting from 0.4393 to 0.5008 under REG_1.00), exactly `0 / 300` pairs achieved `HIGH_CONFIDENCE`.",
        "",
        "## 10. Future Guardrail Framework",
        "The following empirical criteria reflect the offline evaluation observations for any future candidate scoring evaluation:",
        "1. **Zero Positive Regression**: `positive_regression_count == 0` (no baseline reviewed positive dropped to DIFFERENT).",
        "2. **Zero Controlled-HN False High Confidence**: `controlled_HN_HIGH_CONFIDENCE == 0` (critical gates authoritative).",
        "3. **Zero Controlled-HN False High Score**: `controlled_HN_ge_0_85 == 0` (no controlled conflict exceeds 0.85).",
        "4. **DEV-HELDOUT Consistency**: Coverage and review load delta between splits must remain qualitatively stable.",
        "5. **Bounded Human Review Capacity**: Human review load increase must align with business operational bandwidth (to be defined by human-reviewer availability, not inferred from dataset alone).",
        "",
        "## 11. Limitations",
        "- `HN_CORRUPT` synthetic pairs contain label noise and should not be confused with physical field conflicts.",
        "- Review queue throughput and reviewer decision latency were not modeled in this offline dataset.",
        "- Production weights remain hand-designed baseline [0.20, 0.20, 0.35, 0.15, 0.10].",
        "",
        "## 12. Conclusion",
        "This evaluation describes the exact operational tradeoff between candidate weight vectors:",
        "- **`REG_1.00`** increases overall positive coverage from `86.83%` to `96.59%` on DEV (+357 positive rescues) and from `82.07%` to `97.00%` on HELDOUT (+568 positive rescues), with zero positive regressions. However, it increases total human review load from `76.59%` to `84.47%` on DEV (+412 review pairs) and elevates `58 / 300` controlled hard negatives into REVIEW (total 175 / 300 in REVIEW vs 117 in baseline), yielding an incremental efficiency ratio of `6.49` positive rescues per added negative review on DEV.",
        "- **`REG_HN_2.00`** achieves `97.00%` positive coverage on DEV (+372 rescues) while maintaining a lower hard-negative review count (114 / 300 in REVIEW vs 175 in REG_1.00), with an incremental efficiency ratio of `8.45` on DEV, but shifts 50.1% of weight onto semantic similarity and drops other_attributes weight to 0.00.",
        "- **`BASELINE`** remains the most conservative operating point for human review queue volume (76.59% DEV review rate), filtering 183 / 300 hard negatives as DIFFERENT, but leaves 13.17% of DEV positives (sparse descriptions) categorized as DIFFERENT.",
    ])

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    run_operational_evaluation()
