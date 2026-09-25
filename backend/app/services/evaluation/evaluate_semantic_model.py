"""
Semantic Model Evaluator for MIRA.

Evaluates baseline vs fine-tuned SentenceTransformer models on:
1. DEV split from Training_Pairs_MIRA_FINAL.csv (5,228 pairs)
2. HELDOUT split from Training_Pairs_MIRA_FINAL.csv (5,284 pairs)
3. Hard Negatives dataset (300 pairs)
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.metrics import average_precision_score, roc_auc_score


def evaluate_split(
    model: SentenceTransformer,
    df: pd.DataFrame,
    desc_a_col: str = "desc_a",
    desc_b_col: str = "desc_b",
    label_col: str = "label",
    pair_type_col: str = "pair_type",
    batch_size: int = 256,
) -> Dict[str, Any]:
    texts_a = df[desc_a_col].fillna("").astype(str).tolist()
    texts_b = df[desc_b_col].fillna("").astype(str).tolist()
    labels = df[label_col].astype(int).to_numpy()

    # Pre-encode all unique texts for efficiency
    unique_texts = list(set(texts_a + texts_b))
    embeddings = model.encode(
        unique_texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    emb_dict = {t: e for t, e in zip(unique_texts, embeddings)}

    # Compute cosine similarities (normalized dot product)
    embs_a = np.array([emb_dict[t] for t in texts_a])
    embs_b = np.array([emb_dict[t] for t in texts_b])
    similarities = np.clip(np.sum(embs_a * embs_b, axis=1), 0.0, 1.0)

    pos_mask = labels == 1
    neg_mask = labels == 0

    pos_sims = similarities[pos_mask]
    neg_sims = similarities[neg_mask]

    pos_mean = float(np.mean(pos_sims)) if len(pos_sims) > 0 else 0.0
    neg_mean = float(np.mean(neg_sims)) if len(neg_sims) > 0 else 0.0
    margin = pos_mean - neg_mean

    roc_auc = float(roc_auc_score(labels, similarities)) if len(np.unique(labels)) > 1 else 0.0
    pr_auc = float(average_precision_score(labels, similarities)) if len(np.unique(labels)) > 1 else 0.0

    # False high confidence: fraction of negatives with similarity > 0.85
    fhc_count = int(np.sum(neg_sims > 0.85))
    fhc_rate = float(fhc_count / len(neg_sims)) if len(neg_sims) > 0 else 0.0

    # Breakdown by pair_type if available
    breakdown = {}
    if pair_type_col in df.columns:
        for ptype, group_df in df.groupby(pair_type_col):
            group_indices = group_df.index
            group_sims = similarities[df.index.isin(group_indices)]
            breakdown[str(ptype)] = {
                "count": len(group_df),
                "mean_sim": round(float(np.mean(group_sims)), 4),
                "median_sim": round(float(np.median(group_sims)), 4),
                "std_sim": round(float(np.std(group_sims)), 4),
                "fhc_count (>0.85)": int(np.sum(group_sims > 0.85)) if group_df[label_col].iloc[0] == 0 else 0,
            }

    return {
        "total_pairs": len(df),
        "pos_count": int(np.sum(pos_mask)),
        "neg_count": int(np.sum(neg_mask)),
        "pos_mean_sim": round(pos_mean, 4),
        "neg_mean_sim": round(neg_mean, 4),
        "margin": round(margin, 4),
        "roc_auc": round(roc_auc, 4),
        "pr_auc": round(pr_auc, 4),
        "fhc_count_gt_0_85": fhc_count,
        "fhc_rate": round(fhc_rate, 4),
        "pair_type_breakdown": breakdown,
    }


def evaluate_hard_negatives_300(
    model: SentenceTransformer,
    csv_path: Path = Path("data/evaluation/dataset_a_hard_negatives.csv"),
    batch_size: int = 128,
) -> Dict[str, Any]:
    df = pd.read_csv(csv_path)
    texts_a = df["source_description"].fillna("").astype(str).tolist()
    texts_b = df["target_description"].fillna("").astype(str).tolist()

    unique_texts = list(set(texts_a + texts_b))
    embeddings = model.encode(
        unique_texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    emb_dict = {t: e for t, e in zip(unique_texts, embeddings)}

    embs_a = np.array([emb_dict[t] for t in texts_a])
    embs_b = np.array([emb_dict[t] for t in texts_b])
    similarities = np.clip(np.sum(embs_a * embs_b, axis=1), 0.0, 1.0)

    # All 300 are ground_truth == DIFFERENT (negatives with small text edits)
    mean_sim = float(np.mean(similarities))
    median_sim = float(np.median(similarities))
    fhc_count = int(np.sum(similarities > 0.85))
    fhc_rate = float(fhc_count / len(similarities))

    # Field-level breakdown
    field_breakdown = {}
    if "conflicting_fields" in df.columns:
        for field, group_df in df.groupby("conflicting_fields"):
            idx = df.index.isin(group_df.index)
            field_sims = similarities[idx]
            field_breakdown[str(field)] = {
                "count": len(group_df),
                "mean_sim": round(float(np.mean(field_sims)), 4),
                "median_sim": round(float(np.median(field_sims)), 4),
                "fhc_count (>0.85)": int(np.sum(field_sims > 0.85)),
            }

    return {
        "total_pairs": len(df),
        "mean_similarity": round(mean_sim, 4),
        "median_similarity": round(median_sim, 4),
        "fhc_count_gt_0_85": fhc_count,
        "fhc_rate": round(fhc_rate, 4),
        "field_breakdown": field_breakdown,
    }


def run_full_evaluation(model_name_or_path: str) -> Dict[str, Any]:
    print(f"Loading model: {model_name_or_path}...")
    model = SentenceTransformer(model_name_or_path, device="cpu")

    print("Loading Training_Pairs_MIRA_FINAL.csv...")
    df_all = pd.read_csv("Training_Pairs_MIRA_FINAL.csv", low_memory=False)

    df_dev = df_all[df_all["split"] == "dev"].reset_index(drop=True)
    df_heldout = df_all[df_all["split"] == "heldout"].reset_index(drop=True)

    print(f"Evaluating DEV set ({len(df_dev)} pairs)...")
    dev_results = evaluate_split(model, df_dev)

    print(f"Evaluating HELDOUT set ({len(df_heldout)} pairs)...")
    heldout_results = evaluate_split(model, df_heldout)

    print("Evaluating 300 Hard Negatives...")
    hn_results = evaluate_hard_negatives_300(model)

    results = {
        "model": model_name_or_path,
        "dev": dev_results,
        "heldout": heldout_results,
        "hard_negatives_300": hn_results,
    }

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="all-MiniLM-L6-v2")
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    results = run_full_evaluation(args.model)
    print("\n" + "=" * 60)
    print(f"EVALUATION SUMMARY: {args.model}")
    print("=" * 60)
    print(f"DEV     - ROC-AUC: {results['dev']['roc_auc']}, PR-AUC: {results['dev']['pr_auc']}, Margin: {results['dev']['margin']} (Pos: {results['dev']['pos_mean_sim']}, Neg: {results['dev']['neg_mean_sim']})")
    print(f"HELDOUT - ROC-AUC: {results['heldout']['roc_auc']}, PR-AUC: {results['heldout']['pr_auc']}, Margin: {results['heldout']['margin']} (Pos: {results['heldout']['pos_mean_sim']}, Neg: {results['heldout']['neg_mean_sim']})")
    print(f"HN 300  - Mean Sim: {results['hard_negatives_300']['mean_similarity']}, FHC (>0.85): {results['hard_negatives_300']['fhc_count_gt_0_85']}/{results['hard_negatives_300']['total_pairs']} ({results['hard_negatives_300']['fhc_rate']*100:.1f}%)")
    print("=" * 60)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"Saved results to {args.output}")
