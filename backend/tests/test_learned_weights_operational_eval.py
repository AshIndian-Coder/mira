"""
Unit tests for Learned Weights Operational Evaluation Framework (Track 1 — Step 5).
"""

import json
import numpy as np
import pandas as pd
import pytest

from app.services.evaluation.learned_weights_operational_eval import (
    CONFIGS,
    compute_scores_and_decisions,
    evaluate_positive_coverage,
    evaluate_negative_handling,
    evaluate_review_load_and_efficiency,
    evaluate_controlled_hard_negatives,
)
from app.services.matching.scoring import (
    TEXT_WEIGHT,
    SEMANTIC_WEIGHT,
    SPECIFICATION_WEIGHT,
    GRADE_WEIGHT,
    OTHER_ATTRIBUTES_WEIGHT,
)


def test_production_scoring_constants_unchanged():
    """Verify that active production weights and constants match frozen production weights."""
    assert TEXT_WEIGHT == 0.175
    assert SEMANTIC_WEIGHT == 0.400
    assert SPECIFICATION_WEIGHT == 0.250
    assert GRADE_WEIGHT == 0.125
    assert OTHER_ATTRIBUTES_WEIGHT == 0.050


def test_positive_coverage_calculation():
    """Test positive coverage, rescue, and regression calculation."""
    df = pd.DataFrame({
        "label": [1, 1, 1],
        "decision_BASELINE": ["DIFFERENT", "REVIEW", "REVIEW"],
        "decision_CANDIDATE": ["REVIEW", "REVIEW", "DIFFERENT"],
    })
    cov = evaluate_positive_coverage(df, "CANDIDATE", base_cfg="BASELINE")

    assert cov["total_positive_pairs"] == 3
    assert cov["count_REVIEW"] == 2
    assert cov["count_DIFFERENT"] == 1
    assert cov["positive_rescue_count"] == 1  # 1st pair rescued from DIFFERENT to REVIEW
    assert cov["positive_regression_count"] == 1  # 3rd pair dropped from REVIEW to DIFFERENT
    assert cov["overall_positive_coverage_count"] == 2
    assert pytest.approx(cov["overall_positive_coverage_pct"], 0.1) == 66.67


def test_negative_handling_per_pair_type():
    """Test negative handling breakdown."""
    df = pd.DataFrame({
        "label": [0, 0, 0],
        "pair_type": ["NEG_EASY", "NEG_EASY", "HN_SIBLING"],
        "decision_CANDIDATE": ["DIFFERENT", "DIFFERENT", "REVIEW"],
    })
    res = evaluate_negative_handling(df, "CANDIDATE")

    assert res["overall"]["total_negative_pairs"] == 3
    assert res["overall"]["count_DIFFERENT"] == 2
    assert res["overall"]["count_REVIEW"] == 1
    assert res["by_pair_type"]["NEG_EASY"]["count_DIFFERENT"] == 2
    assert res["by_pair_type"]["HN_SIBLING"]["count_REVIEW"] == 1


def test_review_load_and_efficiency():
    """Test incremental review efficiency ratio and review composition."""
    df = pd.DataFrame({
        "label": [1, 1, 0, 0],
        "decision_BASELINE": ["DIFFERENT", "REVIEW", "DIFFERENT", "DIFFERENT"],
        "decision_CANDIDATE": ["REVIEW", "REVIEW", "REVIEW", "DIFFERENT"],
    })
    res = evaluate_review_load_and_efficiency(df, "CANDIDATE", base_cfg="BASELINE")

    # Baseline REVIEW count = 1 (1 positive, 0 negative)
    # Candidate REVIEW count = 3 (2 positive, 1 negative)
    # Added positive reviews = 1, Added negative reviews = 1, Rescues = 1
    # Efficiency ratio = 1 / 1 = 1.0
    assert res["total_REVIEW_count"] == 3
    assert res["delta_REVIEW_count_vs_baseline"] == 2
    assert res["review_queue_composition"]["positive_count_in_REVIEW"] == 2
    assert res["review_queue_composition"]["negative_count_in_REVIEW"] == 1
    assert res["incremental_efficiency"]["positive_rescues"] == 1
    assert res["incremental_efficiency"]["added_negative_reviews"] == 1
    assert res["incremental_efficiency"]["incremental_efficiency_ratio (rescues/added_neg_rev)"] == 1.0


def test_controlled_hard_negatives_critical_gate_authority():
    """Verify that conflict gate blocks HIGH_CONFIDENCE even if score is high."""
    conflict_gate = json.dumps([{"field": "thread", "status": "CONFLICT"}])
    df = pd.DataFrame({
        "pair_id": ["HN_TEST"],
        "text_similarity": [1.0],
        "semantic_similarity": [1.0],
        "specification_similarity": [1.0],
        "material_grade_similarity": [1.0],
        "other_attributes_similarity": [1.0],
        "critical_checks_json": [conflict_gate],
        "conflicting_fields": ["metric_thread"],
    })
    res = evaluate_controlled_hard_negatives(df, CONFIGS)

    for cfg_name in CONFIGS.keys():
        assert res["overall_summary"][cfg_name]["count_HIGH_CONFIDENCE"] == 0
        assert res["overall_summary"][cfg_name]["count_REVIEW"] == 1
