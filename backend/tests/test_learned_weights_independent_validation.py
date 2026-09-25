"""
Unit tests for Learned Weights Independent Validation (Track 1 — Step 6).
"""

import json
import numpy as np
import pandas as pd
import pytest

from app.services.evaluation.learned_weights_independent_validation import (
    CONFIGS,
    audit_dataset_independence,
    evaluate_operational_metrics,
    analyze_sparsity_on_validation,
)
from app.services.matching.scoring import (
    TEXT_WEIGHT,
    SEMANTIC_WEIGHT,
    SPECIFICATION_WEIGHT,
    GRADE_WEIGHT,
    OTHER_ATTRIBUTES_WEIGHT,
)


def test_production_constants_invariant_step6():
    """Verify that production weights and thresholds match frozen production weights."""
    assert TEXT_WEIGHT == 0.175
    assert SEMANTIC_WEIGHT == 0.400
    assert SPECIFICATION_WEIGHT == 0.250
    assert GRADE_WEIGHT == 0.125
    assert OTHER_ATTRIBUTES_WEIGHT == 0.050


def test_audit_dataset_independence():
    """Test independence overlap calculations."""
    val_df = pd.DataFrame({
        "desc_a": ["motor 15kw", "pipe 50mm"],
        "desc_b": ["motor 15kw", "pipe 50mm"],
        "pair_id": ["P1", "P2"],
        "label": [1, 0],
        "source_material_code": ["M1", "M2"],
        "target_material_code": ["M1", "M2"],
    })
    dev_df = pd.DataFrame({
        "desc_a": ["valve 25mm"],
        "desc_b": ["valve 25mm"],
        "pair_id": ["P3"],
        "material_code_a": ["M3"],
        "material_code_b": ["M4"],
    })
    held_df = pd.DataFrame({
        "desc_a": ["bearing 6205"],
        "desc_b": ["bearing 6205"],
        "pair_id": ["P4"],
        "material_code_a": ["M5"],
        "material_code_b": ["M6"],
    })

    audit = audit_dataset_independence(val_df, dev_df, held_df)
    assert audit["validation_total_records"] == 2
    assert audit["overlap_with_DEV_5228"]["pair_id_overlap"] == 0
    assert audit["overlap_with_DEV_5228"]["exact_description_pair_overlap"] == 0
    assert audit["overlap_with_DEV_5228"]["material_code_overlap"] == 0
    assert audit["independence_classification"] == "LIMITED INDEPENDENT VALIDATION"


def test_evaluate_operational_metrics_validation():
    """Test operational metric computation on a test dataframe."""
    df = pd.DataFrame({
        "label": [1, 1, 0],
        "decision_BASELINE": ["DIFFERENT", "REVIEW", "DIFFERENT"],
        "decision_CANDIDATE": ["REVIEW", "REVIEW", "REVIEW"],
    })
    res = evaluate_operational_metrics(df, "CANDIDATE", base_cfg="BASELINE")

    pos = res["positive_coverage"]
    assert pos["total_positive"] == 2
    assert pos["count_REVIEW"] == 2
    assert pos["positive_rescue_count"] == 1
    assert pos["positive_regression_count"] == 0
    assert pos["overall_positive_coverage_pct"] == 100.0

    neg = res["negative_handling"]
    assert neg["total_negative"] == 1
    assert neg["count_REVIEW"] == 1

    rev = res["review_load"]
    assert rev["total_REVIEW_count"] == 3
    assert rev["delta_REVIEW_count_vs_baseline"] == 2
    assert rev["incremental_efficiency"]["efficiency_ratio"] == 1.0


def test_analyze_sparsity_on_validation():
    """Test sparsity slice analysis."""
    df = pd.DataFrame({
        "label": [1, 1],
        "text_similarity": [0.8, 0.9],
        "semantic_similarity": [0.85, 0.95],
        "specification_similarity": [0.8, 0.0],
        "score_BASELINE": [0.75, 0.50],
        "score_REG_1.00": [0.80, 0.65],
        "decision_BASELINE": ["REVIEW", "REVIEW"],
        "decision_REG_1.00": ["REVIEW", "REVIEW"],
    })
    sparsity = analyze_sparsity_on_validation(df)
    assert sparsity["structured_positives"]["count"] == 1
    assert sparsity["sparse_positives_all"]["count"] == 1
    assert sparsity["structured_positives"]["mean_score_REG_1.00"] == 0.80
    assert sparsity["sparse_positives_all"]["mean_score_REG_1.00"] == 0.65
