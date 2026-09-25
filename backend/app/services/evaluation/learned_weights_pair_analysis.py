"""
Pair-Level Comparative Analysis for MIRA Learned Weights (Track 1 — Step 4).

Compares:
1. Baseline: [0.20, 0.20, 0.35, 0.15, 0.10]
2. Stable Learned (lambda_reg = 1.00): [0.2367, 0.3192, 0.2173, 0.1115, 0.1154]
3. Reg+HN Candidate (lambda_reg = 0.10, lambda_HN = 2.00): [0.2755, 0.5014, 0.0782, 0.1449, 0.0000]

Analyzes:
- Pair-level score deltas and decision transitions through MIRA critical gates.
- Breakdown by pair type (POS, HN_CORRUPT, HN_SIBLING, NEG_EASY, NEG_SAME_CAT).
- Breakdown by category (FASTENERS, VALVES, PIPING, ELECTRICAL, BEARINGS, PUMPS, etc.).
- Positive pair deep dive (rescued vs regressed, largest improvements vs drops).
- Negative pair deep dive (escalated vs safely filtered).
- 300 Hard Negatives benchmark by engineering field.
- Feature contribution decomposition: contribution_i = weight_i * feature_i.
- Structured vs sparse positive analysis.

Outputs:
- data/evaluation/learned_weights_pair_analysis.json
- data/evaluation/learned_weights_pair_analysis.md
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

FEATURE_NAMES = [
    "text_similarity",
    "semantic_similarity",
    "specification_similarity",
    "material_grade_similarity",
    "other_attributes_similarity",
]

BASELINE_WEIGHTS = np.array([0.20, 0.20, 0.35, 0.15, 0.10], dtype=np.float64)
STABLE_LAMBDA1_WEIGHTS = np.array([0.2367, 0.3192, 0.2173, 0.1115, 0.1154], dtype=np.float64)
REG_HN_WEIGHTS = np.array([0.2755, 0.5014, 0.0782, 0.1449, 0.0000], dtype=np.float64)

HIGH_CONFIDENCE_THRESHOLD = 0.85
DIFFERENT_THRESHOLD = 0.45


def classify_pair_decision(
    score: float,
    critical_checks_json: Optional[str],
) -> str:
    """Classify a single pair into HIGH_CONFIDENCE, REVIEW, or DIFFERENT based on MIRA rules."""
    if isinstance(critical_checks_json, str) and critical_checks_json.strip():
        try:
            checks = json.loads(critical_checks_json)
        except Exception:
            checks = []
    else:
        checks = []

    has_unknown = any(c.get("status") == "UNKNOWN" for c in checks)
    has_conflict = any(c.get("status") == "CONFLICT" for c in checks)
    gates_pass = bool(checks) and all(c.get("status") == "PASS" for c in checks)

    if score >= HIGH_CONFIDENCE_THRESHOLD and gates_pass:
        return "HIGH_CONFIDENCE"
    elif has_unknown or has_conflict:
        return "REVIEW"
    elif score > DIFFERENT_THRESHOLD:
        return "REVIEW"
    else:
        return "DIFFERENT"


def compute_pair_transitions(
    df: pd.DataFrame,
    weights_base: np.ndarray = BASELINE_WEIGHTS,
    weights_l1: np.ndarray = STABLE_LAMBDA1_WEIGHTS,
    weights_hn: np.ndarray = REG_HN_WEIGHTS,
) -> pd.DataFrame:
    """Add score, delta, decision, and transition columns to the dataframe."""
    df = df.copy()
    X = df[FEATURE_NAMES].to_numpy(dtype=np.float64)

    df["score_baseline"] = np.round(X @ weights_base, 4)
    df["score_lambda1"] = np.round(X @ weights_l1, 4)
    df["score_hn"] = np.round(X @ weights_hn, 4)

    df["delta_lambda1"] = np.round(df["score_lambda1"] - df["score_baseline"], 4)
    df["delta_hn"] = np.round(df["score_hn"] - df["score_baseline"], 4)

    # Classify decisions
    dec_base = []
    dec_l1 = []
    dec_hn = []
    for idx, row in df.iterrows():
        chk = row.get("critical_checks_json")
        dec_base.append(classify_pair_decision(row["score_baseline"], chk))
        dec_l1.append(classify_pair_decision(row["score_lambda1"], chk))
        dec_hn.append(classify_pair_decision(row["score_hn"], chk))

    df["decision_baseline"] = dec_base
    df["decision_lambda1"] = dec_l1
    df["decision_hn"] = dec_hn

    # Transitions
    def get_trans(d1: str, d2: str) -> str:
        return "SAME_DECISION" if d1 == d2 else f"{d1} -> {d2}"

    df["transition_lambda1"] = [get_trans(b, l) for b, l in zip(dec_base, dec_l1)]
    df["transition_hn"] = [get_trans(b, h) for b, h in zip(dec_base, dec_hn)]

    return df


def calculate_feature_contributions(
    features: List[float],
    weights: np.ndarray,
) -> Dict[str, float]:
    """Compute contribution_i = weight_i * feature_i."""
    return {
        FEATURE_NAMES[i]: round(float(weights[i] * features[i]), 4)
        for i in range(len(FEATURE_NAMES))
    }


def summarize_transitions(series: pd.Series) -> Dict[str, int]:
    """Return dictionary of transition frequencies."""
    return {str(k): int(v) for k, v in series.value_counts().to_dict().items()}


def analyze_pair_types(df: pd.DataFrame) -> Dict[str, Any]:
    """Analyze breakdown by pair_type."""
    res = {}
    for pt, grp in df.groupby("pair_type"):
        res[str(pt)] = {
            "count": len(grp),
            "positive_count": int(np.sum(grp["label"] == 1)),
            "negative_count": int(np.sum(grp["label"] == 0)),
            "mean_baseline": round(float(grp["score_baseline"].mean()), 4),
            "mean_lambda1": round(float(grp["score_lambda1"].mean()), 4),
            "mean_delta_lambda1": round(float(grp["delta_lambda1"].mean()), 4),
            "median_delta_lambda1": round(float(grp["delta_lambda1"].median()), 4),
            "mean_hn": round(float(grp["score_hn"].mean()), 4),
            "mean_delta_hn": round(float(grp["delta_hn"].mean()), 4),
            "transitions_lambda1": summarize_transitions(grp["transition_lambda1"]),
            "transitions_hn": summarize_transitions(grp["transition_hn"]),
        }
    return res


def analyze_categories(df: pd.DataFrame) -> Dict[str, Any]:
    """Analyze breakdown by category with ROC-AUC where available."""
    res = {}
    for cat, grp in df.groupby("category"):
        y = grp["label"].to_numpy()
        has_both = len(np.unique(y)) > 1
        roc_base = round(float(roc_auc_score(y, grp["score_baseline"])), 4) if has_both else None
        roc_l1 = round(float(roc_auc_score(y, grp["score_lambda1"])), 4) if has_both else None
        roc_hn = round(float(roc_auc_score(y, grp["score_hn"])), 4) if has_both else None

        res[str(cat)] = {
            "count": len(grp),
            "positive_count": int(np.sum(y == 1)),
            "negative_count": int(np.sum(y == 0)),
            "mean_baseline": round(float(grp["score_baseline"].mean()), 4),
            "mean_lambda1": round(float(grp["score_lambda1"].mean()), 4),
            "mean_delta_lambda1": round(float(grp["delta_lambda1"].mean()), 4),
            "mean_hn": round(float(grp["score_hn"].mean()), 4),
            "roc_auc_baseline": roc_base,
            "roc_auc_lambda1": roc_l1,
            "roc_auc_hn": roc_hn,
            "transitions_lambda1": summarize_transitions(grp["transition_lambda1"]),
            "transitions_hn": summarize_transitions(grp["transition_hn"]),
        }
    return res


def extract_representative_examples(
    df: pd.DataFrame,
    condition: pd.Series,
    sort_by: str,
    ascending: bool = False,
    n: int = 3,
) -> List[Dict[str, Any]]:
    """Select representative examples deterministically."""
    subset = df[condition].sort_values(by=sort_by, ascending=ascending).head(n)
    examples = []
    for _, row in subset.iterrows():
        feats = [float(row[fn]) for fn in FEATURE_NAMES]
        ex = {
            "pair_id": str(row.get("pair_id", "")),
            "category": str(row.get("category", "")),
            "pair_type": str(row.get("pair_type", "")),
            "cpse_a": str(row.get("cpse_a", "")),
            "cpse_b": str(row.get("cpse_b", "")),
            "material_code_a": str(row.get("material_code_a", "")),
            "material_code_b": str(row.get("material_code_b", "")),
            "desc_a": str(row.get("desc_a", "")),
            "desc_b": str(row.get("desc_b", "")),
            "features": {fn: round(feats[i], 4) for i, fn in enumerate(FEATURE_NAMES)},
            "baseline_contributions": calculate_feature_contributions(feats, BASELINE_WEIGHTS),
            "lambda1_contributions": calculate_feature_contributions(feats, STABLE_LAMBDA1_WEIGHTS),
            "score_baseline": float(row["score_baseline"]),
            "score_lambda1": float(row["score_lambda1"]),
            "delta_lambda1": float(row["delta_lambda1"]),
            "decision_baseline": str(row["decision_baseline"]),
            "decision_lambda1": str(row["decision_lambda1"]),
            "transition": str(row["transition_lambda1"]),
        }
        examples.append(ex)
    return examples


def analyze_structured_vs_sparse_positives(df_pos: pd.DataFrame) -> Dict[str, Any]:
    """Analyze structured (spec > 0) vs sparse (spec == 0) positive pairs."""
    struct_mask = df_pos["specification_similarity"] > 0
    sparse_mask = df_pos["specification_similarity"] == 0

    df_struct = df_pos[struct_mask]
    df_sparse = df_pos[sparse_mask]
    df_sparse_ht = df_sparse[df_sparse["text_similarity"] >= 0.70]
    df_sparse_lt = df_sparse[df_sparse["text_similarity"] < 0.70]

    def pack_grp(grp: pd.DataFrame) -> Dict[str, Any]:
        return {
            "count": len(grp),
            "mean_text": round(float(grp["text_similarity"].mean()), 4) if len(grp) else None,
            "mean_semantic": round(float(grp["semantic_similarity"].mean()), 4) if len(grp) else None,
            "mean_spec": round(float(grp["specification_similarity"].mean()), 4) if len(grp) else None,
            "mean_baseline": round(float(grp["score_baseline"].mean()), 4) if len(grp) else None,
            "mean_lambda1": round(float(grp["score_lambda1"].mean()), 4) if len(grp) else None,
            "mean_delta_lambda1": round(float(grp["delta_lambda1"].mean()), 4) if len(grp) else None,
            "transitions_lambda1": summarize_transitions(grp["transition_lambda1"]),
        }

    return {
        "structured_positives": pack_grp(df_struct),
        "sparse_positives_all": pack_grp(df_sparse),
        "sparse_high_text (text >= 0.70)": pack_grp(df_sparse_ht),
        "sparse_low_text (text < 0.70)": pack_grp(df_sparse_lt),
    }


def analyze_hard_negatives_benchmark(
    df_hard: pd.DataFrame,
) -> Dict[str, Any]:
    """Analyze 300 hard negatives benchmark across fields."""
    field_col = "conflicting_fields" if "conflicting_fields" in df_hard.columns else "category"
    res = {}
    for fld, grp in df_hard.groupby(field_col):
        s_b = grp["score_baseline"]
        s_l1 = grp["score_lambda1"]
        s_hn = grp["score_hn"]
        res[str(fld)] = {
            "count": len(grp),
            "mean_baseline": round(float(s_b.mean()), 4),
            "mean_lambda1": round(float(s_l1.mean()), 4),
            "mean_hn": round(float(s_hn.mean()), 4),
            "baseline_ge_0_80": int(np.sum(s_b >= 0.80)),
            "lambda1_ge_0_80": int(np.sum(s_l1 >= 0.80)),
            "hn_ge_0_80": int(np.sum(s_hn >= 0.80)),
            "baseline_ge_0_85": int(np.sum(s_b >= 0.85)),
            "lambda1_ge_0_85": int(np.sum(s_l1 >= 0.85)),
            "hn_ge_0_85": int(np.sum(s_hn >= 0.85)),
            "transitions_lambda1": summarize_transitions(grp["transition_lambda1"]),
            "transitions_hn": summarize_transitions(grp["transition_hn"]),
        }

    # Largest hard negative increases and decreases
    largest_inc = extract_representative_examples(df_hard, pd.Series(True, index=df_hard.index), "delta_lambda1", ascending=False, n=3)
    largest_dec = extract_representative_examples(df_hard, pd.Series(True, index=df_hard.index), "delta_lambda1", ascending=True, n=3)

    return {
        "fields": res,
        "largest_hn_increases": largest_inc,
        "largest_hn_decreases": largest_dec,
    }


def run_pair_level_analysis(
    dev_path: str = "data/evaluation/features/dev_features.csv",
    heldout_path: str = "data/evaluation/features/heldout_features.csv",
    hard_neg_path: str = "data/evaluation/features/hard_negatives_features.csv",
) -> Dict[str, Any]:
    """Execute complete pair-level comparison."""
    df_dev_raw = pd.read_csv(dev_path, low_memory=False)
    df_held_raw = pd.read_csv(heldout_path, low_memory=False)
    df_hard_raw = pd.read_csv(hard_neg_path, low_memory=False)

    df_dev = compute_pair_transitions(df_dev_raw)
    df_held = compute_pair_transitions(df_held_raw)
    df_hard = compute_pair_transitions(df_hard_raw)

    # 1. Pair-Type Analysis
    pt_dev = analyze_pair_types(df_dev)
    pt_held = analyze_pair_types(df_held)

    # 2. Category Analysis
    cat_dev = analyze_categories(df_dev)
    cat_held = analyze_categories(df_held)

    # 3. Positive Pair Analysis (DEV)
    df_pos_dev = df_dev[df_dev["label"] == 1]
    pos_rescued = extract_representative_examples(
        df_dev, (df_dev["label"] == 1) & (df_dev["transition_lambda1"] == "DIFFERENT -> REVIEW"), "delta_lambda1", ascending=False, n=3
    )
    pos_regressed = extract_representative_examples(
        df_dev, (df_dev["label"] == 1) & (df_dev["transition_lambda1"] == "REVIEW -> DIFFERENT"), "delta_lambda1", ascending=True, n=3
    )
    pos_largest_inc = extract_representative_examples(
        df_dev, (df_dev["label"] == 1), "delta_lambda1", ascending=False, n=3
    )
    pos_largest_dec = extract_representative_examples(
        df_dev, (df_dev["label"] == 1), "delta_lambda1", ascending=True, n=3
    )

    # 4. Negative Pair Analysis (DEV)
    df_neg_dev = df_dev[df_dev["label"] == 0]
    neg_escalated = extract_representative_examples(
        df_dev, (df_dev["label"] == 0) & (df_dev["transition_lambda1"] == "DIFFERENT -> REVIEW"), "delta_lambda1", ascending=False, n=3
    )
    neg_improved = extract_representative_examples(
        df_dev, (df_dev["label"] == 0) & (df_dev["transition_lambda1"] == "REVIEW -> DIFFERENT"), "delta_lambda1", ascending=True, n=3
    )
    neg_largest_inc = extract_representative_examples(
        df_dev, (df_dev["label"] == 0), "delta_lambda1", ascending=False, n=3
    )
    neg_largest_dec = extract_representative_examples(
        df_dev, (df_dev["label"] == 0), "delta_lambda1", ascending=True, n=3
    )

    # 5. Hard Negatives Benchmark
    hard_analysis = analyze_hard_negatives_benchmark(df_hard)

    # 6. Structured vs Sparse Positives
    struct_sparse_dev = analyze_structured_vs_sparse_positives(df_pos_dev)
    struct_sparse_held = analyze_structured_vs_sparse_positives(df_held[df_held["label"] == 1])

    # 7. Overall Decision Transitions
    overall_dev_trans = summarize_transitions(df_dev["transition_lambda1"])
    overall_held_trans = summarize_transitions(df_held["transition_lambda1"])
    overall_hard_trans = summarize_transitions(df_hard["transition_lambda1"])

    report = {
        "analysis_title": "MIRA Pair-Level Comparative Analysis (Baseline vs Stable Learned lambda=1.00 vs Reg+HN)",
        "weights": {
            "baseline": [round(float(v), 4) for v in BASELINE_WEIGHTS],
            "stable_lambda1": [round(float(v), 4) for v in STABLE_LAMBDA1_WEIGHTS],
            "reg_hn": [round(float(v), 4) for v in REG_HN_WEIGHTS],
        },
        "overall_transitions": {
            "DEV": overall_dev_trans,
            "HELDOUT": overall_held_trans,
            "HARD_NEGATIVES_300": overall_hard_trans,
        },
        "pair_type_analysis": {
            "DEV": pt_dev,
            "HELDOUT": pt_held,
        },
        "category_analysis": {
            "DEV": cat_dev,
            "HELDOUT": cat_held,
        },
        "positive_pairs": {
            "rescued_positives (DIFFERENT -> REVIEW)": pos_rescued,
            "regressed_positives (REVIEW -> DIFFERENT)": pos_regressed,
            "largest_score_improvements": pos_largest_inc,
            "largest_score_regressions": pos_largest_dec,
        },
        "negative_pairs": {
            "escalated_negatives (DIFFERENT -> REVIEW)": neg_escalated,
            "improved_negatives (REVIEW -> DIFFERENT)": neg_improved,
            "largest_score_increases": neg_largest_inc,
            "largest_score_decreases": neg_largest_dec,
        },
        "hard_negatives_benchmark": hard_analysis,
        "structured_vs_sparse_positives": {
            "DEV": struct_sparse_dev,
            "HELDOUT": struct_sparse_held,
        },
    }

    # Save JSON
    json_path = Path("data/evaluation/learned_weights_pair_analysis.json")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Pair-level analysis JSON saved to {json_path}")

    # Generate Markdown
    md_path = Path("data/evaluation/learned_weights_pair_analysis.md")
    generate_markdown_pair_report(report, md_path)
    print(f"Pair-level analysis Markdown saved to {md_path}")

    return report


def generate_markdown_pair_report(data: Dict[str, Any], out_path: Path) -> None:
    """Write human-readable markdown report for pair-level analysis."""
    lines = [
        "# MIRA Pair-Level Learned-Weight Analysis",
        "",
        "## 1. Overview & Weight Configurations",
        "- **Baseline Weights**: `[0.20, 0.20, 0.35, 0.15, 0.10]`",
        "- **Stable Learned (λ=1.00)**: `[0.2367, 0.3192, 0.2173, 0.1115, 0.1154]`",
        "- **Reg+HN Candidate (λ_reg=0.10, λ_HN=2.00)**: `[0.2755, 0.5014, 0.0782, 0.1449, 0.0000]`",
        "",
        "## 2. Overall Decision Transitions (Baseline → λ=1.00)",
        "",
        "| Dataset | SAME_DECISION | DIFFERENT → REVIEW | REVIEW → DIFFERENT |",
        "| :--- | :---: | :---: | :---: |",
    ]

    for ds in ["DEV", "HELDOUT", "HARD_NEGATIVES_300"]:
        tr = data["overall_transitions"][ds]
        same = tr.get("SAME_DECISION", 0)
        d_to_r = tr.get("DIFFERENT -> REVIEW", 0)
        r_to_d = tr.get("REVIEW -> DIFFERENT", 0)
        lines.append(f"| `{ds}` | {same} | {d_to_r} | {r_to_d} |")

    lines.extend([
        "",
        "## 3. Pair-Type Breakdown (DEV Dataset)",
        "",
        "| Pair Type | Count | Pos/Neg | Base Mean | λ=1 Mean | Mean Delta | Median Delta | Transitions (λ=1) |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |",
    ])
    for pt, s in data["pair_type_analysis"]["DEV"].items():
        tr_str = ", ".join([f"{k}: {v}" for k, v in s["transitions_lambda1"].items()])
        lines.append(
            f"| `{pt}` | {s['count']} | {s['positive_count']}/{s['negative_count']} | "
            f"{s['mean_baseline']:.4f} | {s['mean_lambda1']:.4f} | {s['mean_delta_lambda1']:+.4f} | "
            f"{s['median_delta_lambda1']:+.4f} | {tr_str} |"
        )

    lines.extend([
        "",
        "## 4. Category Breakdown (DEV Dataset)",
        "",
        "| Category | Count | Pos/Neg | Base Mean | λ=1 Mean | Mean Delta | Base ROC | λ=1 ROC |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])
    for cat, s in data["category_analysis"]["DEV"].items():
        b_roc = f"{s['roc_auc_baseline']:.4f}" if s['roc_auc_baseline'] is not None else "N/A"
        l_roc = f"{s['roc_auc_lambda1']:.4f}" if s['roc_auc_lambda1'] is not None else "N/A"
        lines.append(
            f"| `{cat}` | {s['count']} | {s['positive_count']}/{s['negative_count']} | "
            f"{s['mean_baseline']:.4f} | {s['mean_lambda1']:.4f} | {s['mean_delta_lambda1']:+.4f} | "
            f"{b_roc} | {l_roc} |"
        )

    lines.extend([
        "",
        "## 5. Hard Negatives Benchmark Breakdown (300 Pairs by Field)",
        "",
        "| Field | Count | Base Mean | λ=1 Mean | Reg+HN Mean | Base $\\ge 0.80$ | λ=1 $\\ge 0.80$ | Reg+HN $\\ge 0.80$ | Transitions (λ=1) |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |",
    ])
    for fld, s in data["hard_negatives_benchmark"]["fields"].items():
        tr_str = ", ".join([f"{k}: {v}" for k, v in s["transitions_lambda1"].items()])
        lines.append(
            f"| `{fld}` | {s['count']} | {s['mean_baseline']:.4f} | {s['mean_lambda1']:.4f} | "
            f"{s['mean_hn']:.4f} | {s['baseline_ge_0_80']} | {s['lambda1_ge_0_80']} | "
            f"{s['hn_ge_0_80']} | {tr_str} |"
        )

    lines.extend([
        "",
        "## 6. Structured vs Sparse Positives (DEV Dataset)",
        "",
        "| Group | Count | Mean Text | Mean Semantic | Mean Spec | Base Mean | λ=1 Mean | Mean Delta | Transitions (λ=1) |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |",
    ])
    for grp_name, s in data["structured_vs_sparse_positives"]["DEV"].items():
        tr_str = ", ".join([f"{k}: {v}" for k, v in s["transitions_lambda1"].items()])
        mt = f"{s['mean_text']:.4f}" if s['mean_text'] is not None else "-"
        ms = f"{s['mean_semantic']:.4f}" if s['mean_semantic'] is not None else "-"
        msp = f"{s['mean_spec']:.4f}" if s['mean_spec'] is not None else "-"
        lines.append(
            f"| `{grp_name}` | {s['count']} | {mt} | {ms} | {msp} | "
            f"{s['mean_baseline']:.4f} | {s['mean_lambda1']:.4f} | {s['mean_delta_lambda1']:+.4f} | {tr_str} |"
        )

    lines.extend([
        "",
        "## 7. Representative Feature-Contribution Examples",
        "",
        "### A. Rescued Positive Pair (Baseline DIFFERENT → λ=1 REVIEW)",
    ])
    for ex in data["positive_pairs"]["rescued_positives (DIFFERENT -> REVIEW)"]:
        lines.extend([
            f"- **Pair ID**: `{ex['pair_id']}` | **Category**: `{ex['category']}`",
            f"  - **Desc A**: \"{ex['desc_a']}\"",
            f"  - **Desc B**: \"{ex['desc_b']}\"",
            f"  - **Features**: Text={ex['features']['text_similarity']:.2f}, Sem={ex['features']['semantic_similarity']:.2f}, Spec={ex['features']['specification_similarity']:.2f}, Grade={ex['features']['material_grade_similarity']:.2f}, Other={ex['features']['other_attributes_similarity']:.2f}",
            f"  - **Score**: Baseline = `{ex['score_baseline']:.4f}` ({ex['decision_baseline']}) → λ=1 = `{ex['score_lambda1']:.4f}` ({ex['decision_lambda1']}) [Delta: `{ex['delta_lambda1']:+.4f}`]",
            f"  - **Why it moved**: Semantic boost (+{(ex['lambda1_contributions']['semantic_similarity'] - ex['baseline_contributions']['semantic_similarity']):+.4f}) and Text boost (+{(ex['lambda1_contributions']['text_similarity'] - ex['baseline_contributions']['text_similarity']):+.4f}) compensated for sparse specification match.",
            "",
        ])

    lines.append("### B. Escalated Negative Pair (Baseline DIFFERENT → λ=1 REVIEW)")
    for ex in data["negative_pairs"]["escalated_negatives (DIFFERENT -> REVIEW)"]:
        lines.extend([
            f"- **Pair ID**: `{ex['pair_id']}` | **Category**: `{ex['category']}` | **Type**: `{ex['pair_type']}`",
            f"  - **Desc A**: \"{ex['desc_a']}\"",
            f"  - **Desc B**: \"{ex['desc_b']}\"",
            f"  - **Features**: Text={ex['features']['text_similarity']:.2f}, Sem={ex['features']['semantic_similarity']:.2f}, Spec={ex['features']['specification_similarity']:.2f}, Grade={ex['features']['material_grade_similarity']:.2f}, Other={ex['features']['other_attributes_similarity']:.2f}",
            f"  - **Score**: Baseline = `{ex['score_baseline']:.4f}` ({ex['decision_baseline']}) → λ=1 = `{ex['score_lambda1']:.4f}` ({ex['decision_lambda1']}) [Delta: `{ex['delta_lambda1']:+.4f}`]",
            f"  - **Why it moved**: Reduced specification weight (0.35 → 0.22) softened the penalty on specification mismatch, lifting the score above the 0.45 DIFFERENT threshold into REVIEW.",
            "",
        ])

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    run_pair_level_analysis()
