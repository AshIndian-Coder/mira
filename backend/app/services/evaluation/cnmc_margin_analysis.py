"""
CNMC Best-vs-Second-Best Margin Analysis & Evaluation Suite.

Evaluates candidate margin distributions, top-1 correctness, margin buckets,
score-vs-margin interaction, and hard-negative discrimination on held-out data.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.services.harmonization.service import build_common_material_record
from app.services.matching.cnmc_matcher import (
    build_cnmc_block_index,
    compute_cnmc_candidate_margin,
    find_cnmc_candidates_for_material,
)
from app.services.matching.embeddings import EmbeddingCache, precompute_embeddings
from app.services.normalization.service import normalize_material_description
from app.services.parsing.service import parse_specifications


DATA_DIR = Path("data/evaluation")
OUTPUT_QUERY_CSV = DATA_DIR / "cnmc_margin_query_results.csv"
OUTPUT_SUMMARY_CSV = DATA_DIR / "cnmc_margin_summary.csv"
OUTPUT_REPORT_JSON = DATA_DIR / "cnmc_margin_report.json"

DEFAULT_MARGIN_BUCKETS: List[Tuple[float, float, str]] = [
    (0.00, 0.01, "[0.00, 0.01)"),
    (0.01, 0.02, "[0.01, 0.02)"),
    (0.02, 0.05, "[0.02, 0.05)"),
    (0.05, 0.10, "[0.05, 0.10)"),
    (0.10, 0.20, "[0.10, 0.20)"),
    (0.20, 1.01, "[0.20, 1.00]"),
]

SCORE_RANGES: List[Tuple[float, float, str]] = [
    (0.85, 1.01, ">=0.85 (High)"),
    (0.65, 0.85, "[0.65, 0.85) (Med)"),
    (0.50, 0.65, "[0.50, 0.65) (Low)"),
    (0.00, 0.50, "<0.50 (Diff)"),
]

MARGIN_RANGES: List[Tuple[float, float, str]] = [
    (0.00, 0.02, "<0.02 (Tight)"),
    (0.02, 0.10, "[0.02, 0.10) (Mod)"),
    (0.10, 1.01, ">=0.10 (Wide)"),
]


def calculate_distribution_stats(values: List[float]) -> Dict[str, Optional[float]]:
    """Compute standard summary percentiles and moments for a list of floats."""
    if not values:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "std": None,
            "p10": None,
            "p25": None,
            "p50": None,
            "p75": None,
            "p90": None,
            "p95": None,
            "min": None,
            "max": None,
        }

    arr = np.array(values, dtype=float)
    return {
        "count": int(len(arr)),
        "mean": round(float(np.mean(arr)), 4),
        "median": round(float(np.median(arr)), 4),
        "std": round(float(np.std(arr)), 4),
        "p10": round(float(np.percentile(arr, 10)), 4),
        "p25": round(float(np.percentile(arr, 25)), 4),
        "p50": round(float(np.percentile(arr, 50)), 4),
        "p75": round(float(np.percentile(arr, 75)), 4),
        "p90": round(float(np.percentile(arr, 90)), 4),
        "p95": round(float(np.percentile(arr, 95)), 4),
        "min": round(float(np.min(arr)), 4),
        "max": round(float(np.max(arr)), 4),
    }


def compute_margin_bucket_breakdown(
    records: List[Dict[str, Any]],
    buckets: Optional[List[Tuple[float, float, str]]] = None,
) -> List[Dict[str, Any]]:
    """
    Compute query count, correctness, and accuracy across descriptive margin buckets.
    Only queries with >=2 candidates (where score_margin is not None) are bucketed.
    """
    if buckets is None:
        buckets = DEFAULT_MARGIN_BUCKETS

    bucket_results = []
    for low, high, label in buckets:
        matching = [
            r for r in records
            if r.get("score_margin") is not None and low <= r["score_margin"] < high
        ]
        total = len(matching)
        correct = sum(1 for r in matching if r.get("top_1_correct") is True)
        incorrect = sum(1 for r in matching if r.get("top_1_correct") is False)
        accuracy = round(correct / total, 4) if total > 0 else None

        bucket_results.append({
            "bucket": label,
            "low": low,
            "high": high,
            "total_queries": total,
            "correct_top_1": correct,
            "incorrect_top_1": incorrect,
            "top_1_accuracy": accuracy,
        })
    return bucket_results


def compute_score_vs_margin_matrix(
    records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Cross-tabulate top candidate score range vs margin range.
    """
    matrix_rows = []
    for s_low, s_high, s_label in SCORE_RANGES:
        for m_low, m_high, m_label in MARGIN_RANGES:
            matching = [
                r for r in records
                if r.get("best_score") is not None
                and s_low <= r["best_score"] < s_high
                and r.get("score_margin") is not None
                and m_low <= r["score_margin"] < m_high
            ]
            total = len(matching)
            correct = sum(1 for r in matching if r.get("top_1_correct") is True)
            high_conf = sum(1 for r in matching if r.get("engine_decision") == "HIGH_CONFIDENCE")
            review = sum(1 for r in matching if r.get("engine_decision") == "REVIEW")
            diff = sum(1 for r in matching if r.get("engine_decision") == "DIFFERENT")
            acc = round(correct / total, 4) if total > 0 else None

            matrix_rows.append({
                "score_range": s_label,
                "margin_range": m_label,
                "total": total,
                "correct": correct,
                "top_1_accuracy": acc,
                "HIGH_CONFIDENCE": high_conf,
                "REVIEW": review,
                "DIFFERENT": diff,
            })
    return matrix_rows


def setup_heldout_cnmc_universe(
    master_df: pd.DataFrame,
    heldout_tmks: List[str],
    max_seeds_per_cluster: int = 2,
    max_queries_per_cluster: int = 10,
    random_seed: int = 42,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[int, Dict[str, Any]], List[Dict[str, Any]], Dict[str, str]]:
    """
    Construct established CNMC registry and partitioned test queries from held-out TMK clusters.
    """
    heldout_master = master_df[master_df["true_match_key"].isin(heldout_tmks)].copy()
    tmk_groups = heldout_master.groupby("true_match_key")

    cnmc_records: List[Dict[str, Any]] = []
    mappings: List[Dict[str, Any]] = []
    materials_index: Dict[int, Dict[str, Any]] = {}
    positive_queries: List[Dict[str, Any]] = []
    tmk_to_cnmc: Dict[str, str] = {}
    mat_id_counter = 1

    for idx, (tmk, group) in enumerate(tmk_groups, 1):
        clean_records = group[group["quality_flag"] == "CLEAN"]
        if len(clean_records) < max_seeds_per_cluster:
            clean_records = group

        seeds = clean_records.iloc[:max_seeds_per_cluster]
        tests = group.iloc[max_seeds_per_cluster:]

        prepared_seeds = []
        for _, row in seeds.iterrows():
            mid = mat_id_counter
            mat_id_counter += 1
            raw_attrs = row.get("attributes")
            attrs = json.loads(raw_attrs) if isinstance(raw_attrs, str) and raw_attrs else {}
            desc = str(row["description"])
            m_dict = {
                "id": mid,
                "cpse": row["cpse_code"],
                "material_code": str(row["material_code"]),
                "description": desc,
                "normalized_description": normalize_material_description(desc),
                "category": row["category"],
                "material_grade": attrs.get("material_grade"),
                "parsed_specifications": parse_specifications(desc),
                "other_attributes": attrs,
                "tmk": tmk,
            }
            for k in ["pressure_rating", "material_grade", "dimensions", "voltage_class"]:
                if attrs.get(k) and not m_dict["parsed_specifications"].get(k):
                    m_dict["parsed_specifications"][k] = attrs[k]
            prepared_seeds.append(m_dict)
            materials_index[mid] = m_dict

        cmr = build_common_material_record(prepared_seeds)
        canon_desc = (
            seeds.iloc[0].get("canonical_description")
            or cmr.get("canonical_description")
            or seeds.iloc[0]["description"]
        )
        cnmc_code = f"CNMC-{idx:03d}"
        tmk_to_cnmc[tmk] = cnmc_code

        cnmc_rec = {
            "id": idx,
            "cnmc_code": cnmc_code,
            "material_type": "GEN",
            "category": seeds.iloc[0]["category"],
            "standardized_description": canon_desc,
            "canonical_material_record": cmr,
            "tmk": tmk,
        }
        cnmc_records.append(cnmc_rec)

        mappings.append({
            "id": idx,
            "nmc": cnmc_code,
            "cpse_mappings": prepared_seeds,
            "cluster_size": len(prepared_seeds),
            "status": "APPROVED",
            "common_material_record": cmr,
            "tmk": tmk,
        })

        if not tests.empty:
            sample_tests = (
                tests.sample(n=min(max_queries_per_cluster, len(tests)), random_state=random_seed)
                if max_queries_per_cluster and len(tests) > max_queries_per_cluster
                else tests
            )
            for _, row in sample_tests.iterrows():
                mid = mat_id_counter
                mat_id_counter += 1
                raw_attrs = row.get("attributes")
                attrs = json.loads(raw_attrs) if isinstance(raw_attrs, str) and raw_attrs else {}
                desc = str(row["description"])
                q_dict = {
                    "id": mid,
                    "query_id": f"Q_POS_{mid}",
                    "query_type": "POSITIVE_HELDOUT",
                    "cpse": row["cpse_code"],
                    "material_code": str(row["material_code"]),
                    "description": desc,
                    "normalized_description": normalize_material_description(desc),
                    "category": row["category"],
                    "material_grade": attrs.get("material_grade"),
                    "parsed_specifications": parse_specifications(desc),
                    "other_attributes": attrs,
                    "tmk": tmk,
                    "expected_cnmc": cnmc_code,
                    "quality_flag": row.get("quality_flag", "CLEAN"),
                }
                for k in ["pressure_rating", "material_grade", "dimensions", "voltage_class"]:
                    if attrs.get(k) and not q_dict["parsed_specifications"].get(k):
                        q_dict["parsed_specifications"][k] = attrs[k]
                positive_queries.append(q_dict)

    return cnmc_records, mappings, materials_index, positive_queries, tmk_to_cnmc


def evaluate_query_item(
    query_material: Dict[str, Any],
    cnmc_records: List[Dict[str, Any]],
    mappings: List[Dict[str, Any]],
    materials_index: Dict[int, Dict[str, Any]],
    block_index: Dict[str, List[str]],
    embedding_cache: EmbeddingCache,
    min_score: float = 0.30,
    max_candidates: int = 10,
) -> Dict[str, Any]:
    """
    Execute existing-CNMC matching for a single query material and compute structured margin evidence.
    """
    proposals = find_cnmc_candidates_for_material(
        query_material,
        max_candidates=max_candidates,
        min_score=min_score,
        embedding_cache=embedding_cache,
        block_index=block_index,
        cnmc_records=cnmc_records,
        mappings=mappings,
        materials_index=materials_index,
    )
    margin_info = compute_cnmc_candidate_margin(proposals)

    n_cands = len(proposals)
    top_cnmc = proposals[0]["cnmc_code"] if proposals else None
    second_cnmc = proposals[1]["cnmc_code"] if len(proposals) >= 2 else None
    top_score = margin_info["best_score"]
    second_score = margin_info["second_best_score"]
    score_margin = margin_info["score_margin"]

    expected_cnmc = query_material.get("expected_cnmc")
    top_1_correct = (top_cnmc == expected_cnmc) if expected_cnmc and top_cnmc else (False if expected_cnmc else None)
    top_decision = proposals[0]["engine_decision"] if proposals else "NO_CANDIDATE"

    has_conflict = False
    if proposals:
        has_conflict = any(c.get("status") == "CONFLICT" for c in proposals[0].get("critical_checks", []))

    return {
        "query_id": query_material.get("query_id") or str(query_material.get("id")),
        "query_type": query_material.get("query_type", "UNKNOWN"),
        "source_cpse": query_material.get("cpse"),
        "source_code": query_material.get("material_code"),
        "source_description": query_material.get("description"),
        "category": query_material.get("category"),
        "expected_cnmc": expected_cnmc,
        "n_candidates": n_cands,
        "top_cnmc": top_cnmc,
        "second_cnmc": second_cnmc,
        "best_score": top_score,
        "second_best_score": second_score,
        "score_margin": score_margin,
        "top_1_correct": top_1_correct,
        "engine_decision": top_decision,
        "has_critical_conflict": has_conflict,
    }


def run_full_evaluation(
    master_csv_path: str = "Final_Master_Material_Records.csv",
    pairs_csv_path: str = "Training_Pairs_MIRA_FINAL.csv",
    min_score: float = 0.30,
) -> Dict[str, Any]:
    """
    Run complete CNMC margin evaluation across held-out positive clusters and hard negatives.
    """
    master_df = pd.read_csv(master_csv_path, low_memory=False)
    pairs_df = pd.read_csv(pairs_csv_path, low_memory=False)

    heldout_pairs = pairs_df[pairs_df["split"] == "heldout"]
    pos_pairs = heldout_pairs[heldout_pairs["label"] == 1]
    hn_corrupt_pairs = heldout_pairs[heldout_pairs["pair_type"] == "HN_CORRUPT"]
    hn_sibling_pairs = heldout_pairs[heldout_pairs["pair_type"] == "HN_SIBLING"]

    heldout_tmks = sorted(list(set(pos_pairs["tmk_a"])))

    # 1. Setup established CNMC universe and positive queries
    cnmc_records, mappings, materials_index, positive_queries, tmk_to_cnmc = setup_heldout_cnmc_universe(
        master_df=master_df,
        heldout_tmks=heldout_tmks,
        max_seeds_per_cluster=2,
        max_queries_per_cluster=10,
    )

    # 2. Setup hard-negative queries
    hn_queries: List[Dict[str, Any]] = []
    mat_id_counter = 100000

    for _, row in hn_corrupt_pairs.iterrows():
        mid = mat_id_counter
        mat_id_counter += 1
        base_tmk = row["tmk_a"]
        desc = str(row["desc_b"])
        hn_queries.append({
            "id": mid,
            "query_id": f"HN_CORRUPT_{mid}",
            "query_type": "HN_CORRUPT",
            "cpse": row["cpse_b"],
            "material_code": str(row["material_code_b"]),
            "description": desc,
            "normalized_description": normalize_material_description(desc),
            "category": row["category"],
            "parsed_specifications": parse_specifications(desc),
            "base_tmk": base_tmk,
            "expected_cnmc": None,
            "base_cnmc": tmk_to_cnmc.get(base_tmk),
        })

    for _, row in hn_sibling_pairs.iterrows():
        mid = mat_id_counter
        mat_id_counter += 1
        base_tmk = row["tmk_a"]
        desc = str(row["desc_b"])
        hn_queries.append({
            "id": mid,
            "query_id": f"HN_SIBLING_{mid}",
            "query_type": "HN_SIBLING",
            "cpse": row["cpse_b"],
            "material_code": str(row["material_code_b"]),
            "description": desc,
            "normalized_description": normalize_material_description(desc),
            "category": row["category"],
            "parsed_specifications": parse_specifications(desc),
            "base_tmk": base_tmk,
            "expected_cnmc": None,
            "base_cnmc": tmk_to_cnmc.get(base_tmk),
        })

    # 3. Precompute Embedding Cache & Build Inverted Index
    all_descs: set[str] = set()
    for c in cnmc_records:
        all_descs.add(normalize_material_description(c["standardized_description"]))
    for m in materials_index.values():
        all_descs.add(normalize_material_description(m["description"]))
    for q in positive_queries:
        all_descs.add(normalize_material_description(q["description"]))
    for q in hn_queries:
        all_descs.add(normalize_material_description(q["description"]))

    embedding_cache = precompute_embeddings(all_descs)
    block_index = build_cnmc_block_index(
        cnmc_records=cnmc_records,
        mappings=mappings,
        materials_index=materials_index,
    )

    # 4. Execute Positive Queries
    pos_eval_records = []
    for q in positive_queries:
        res = evaluate_query_item(
            query_material=q,
            cnmc_records=cnmc_records,
            mappings=mappings,
            materials_index=materials_index,
            block_index=block_index,
            embedding_cache=embedding_cache,
            min_score=min_score,
        )
        pos_eval_records.append(res)

    # 5. Execute Hard Negative Queries
    hn_eval_records = []
    for q in hn_queries:
        res = evaluate_query_item(
            query_material=q,
            cnmc_records=cnmc_records,
            mappings=mappings,
            materials_index=materials_index,
            block_index=block_index,
            embedding_cache=embedding_cache,
            min_score=min_score,
        )
        hn_eval_records.append(res)

    # 6. Compute Positive Aggregate Statistics
    total_pos = len(pos_eval_records)
    zero_cands = [r for r in pos_eval_records if r["n_candidates"] == 0]
    one_cands = [r for r in pos_eval_records if r["n_candidates"] == 1]
    multi_cands = [r for r in pos_eval_records if r["n_candidates"] >= 2]

    correct_multi = [r for r in multi_cands if r["top_1_correct"] is True]
    incorrect_multi = [r for r in multi_cands if r["top_1_correct"] is False]

    all_margins = [r["score_margin"] for r in multi_cands if r["score_margin"] is not None]
    correct_margins = [r["score_margin"] for r in correct_multi if r["score_margin"] is not None]
    incorrect_margins = [r["score_margin"] for r in incorrect_multi if r["score_margin"] is not None]

    pos_stats_all = calculate_distribution_stats(all_margins)
    pos_stats_correct = calculate_distribution_stats(correct_margins)
    pos_stats_incorrect = calculate_distribution_stats(incorrect_margins)

    overall_acc = sum(1 for r in pos_eval_records if r["top_1_correct"] is True) / total_pos if total_pos else 0.0
    cands_ge_1 = [r for r in pos_eval_records if r["n_candidates"] >= 1]
    acc_ge_1 = sum(1 for r in cands_ge_1 if r["top_1_correct"] is True) / len(cands_ge_1) if cands_ge_1 else 0.0
    acc_1_cand = sum(1 for r in one_cands if r["top_1_correct"] is True) / len(one_cands) if one_cands else 0.0
    acc_multi = sum(1 for r in multi_cands if r["top_1_correct"] is True) / len(multi_cands) if multi_cands else 0.0

    # 7. Compute Margin Buckets & Score Matrix
    margin_buckets = compute_margin_bucket_breakdown(pos_eval_records)
    score_margin_matrix = compute_score_vs_margin_matrix(pos_eval_records)

    # 8. Compute Hard Negative Statistics
    hn_total = len(hn_eval_records)
    hn_multi = [r for r in hn_eval_records if r["n_candidates"] >= 2]
    hn_margins = [r["score_margin"] for r in hn_multi if r["score_margin"] is not None]
    hn_stats = calculate_distribution_stats(hn_margins)

    hn_decisions: Dict[str, int] = {}
    for r in hn_eval_records:
        d = r["engine_decision"]
        hn_decisions[d] = hn_decisions.get(d, 0) + 1

    false_high_conf_hn = hn_decisions.get("HIGH_CONFIDENCE", 0)

    # 9. Save Artifacts
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    all_query_records = pos_eval_records + hn_eval_records

    # Query level CSV
    df_queries = pd.DataFrame(all_query_records)
    df_queries.to_csv(OUTPUT_QUERY_CSV, index=False)

    # Summary JSON
    summary_data = {
        "dataset_metadata": {
            "source_master_records": master_csv_path,
            "source_pair_manifest": pairs_csv_path,
            "split": "heldout",
            "established_cnmcs": len(cnmc_records),
            "seed_materials": len(materials_index),
        },
        "query_counts": {
            "total_positive_queries": total_pos,
            "zero_candidates": len(zero_cands),
            "one_candidate": len(one_cands),
            "two_or_more_candidates": len(multi_cands),
            "percentage_ge_2_candidates": round(len(multi_cands) / total_pos * 100, 2) if total_pos else 0.0,
            "total_hard_negative_queries": hn_total,
        },
        "accuracy_metrics": {
            "overall_top_1_accuracy": round(overall_acc, 4),
            "top_1_accuracy_ge_1_candidate": round(acc_ge_1, 4),
            "top_1_accuracy_single_candidate": round(acc_1_cand, 4),
            "top_1_accuracy_multi_candidate": round(acc_multi, 4),
        },
        "margin_statistics": {
            "all_multi_candidate_queries": pos_stats_all,
            "correct_top_1_queries": pos_stats_correct,
            "incorrect_top_1_queries": pos_stats_incorrect,
        },
        "margin_buckets": margin_buckets,
        "score_vs_margin_matrix": score_margin_matrix,
        "hard_negative_analysis": {
            "total_hard_negatives": hn_total,
            "decision_distribution": hn_decisions,
            "false_high_confidence_count": false_high_conf_hn,
            "false_high_confidence_rate": round(false_high_conf_hn / hn_total, 4) if hn_total else 0.0,
            "margin_statistics": hn_stats,
        },
    }

    with open(OUTPUT_REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    # Summary CSV (flattened tables)
    summary_rows = []
    # Buckets
    for b in margin_buckets:
        summary_rows.append({
            "section": "margin_bucket",
            "key": b["bucket"],
            "total": b["total_queries"],
            "correct": b["correct_top_1"],
            "incorrect": b["incorrect_top_1"],
            "accuracy": b["top_1_accuracy"],
            "extra": "",
        })
    # Score Matrix
    for m in score_margin_matrix:
        summary_rows.append({
            "section": "score_vs_margin_matrix",
            "key": f"{m['score_range']} x {m['margin_range']}",
            "total": m["total"],
            "correct": m["correct"],
            "incorrect": m["total"] - m["correct"],
            "accuracy": m["top_1_accuracy"],
            "extra": f"HIGH:{m['HIGH_CONFIDENCE']}, REV:{m['REVIEW']}, DIFF:{m['DIFFERENT']}",
        })
    pd.DataFrame(summary_rows).to_csv(OUTPUT_SUMMARY_CSV, index=False)

    return summary_data


if __name__ == "__main__":
    import sys
    print("Executing CNMC Best-vs-Second-Best Margin Evaluation...")
    summary = run_full_evaluation()
    print("\nEvaluation complete! Summary:")
    print(json.dumps(summary, indent=2))
    sys.exit(0)
