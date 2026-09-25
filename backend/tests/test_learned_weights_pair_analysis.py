"""
Tests for Pair-Level Comparative Analysis (Step 4).
"""

import json
import numpy as np
import pandas as pd
import pytest

from app.services.evaluation.learned_weights_pair_analysis import (
    BASELINE_WEIGHTS,
    STABLE_LAMBDA1_WEIGHTS,
    REG_HN_WEIGHTS,
    classify_pair_decision,
    compute_pair_transitions,
    calculate_feature_contributions,
    summarize_transitions,
)
from app.services.matching.scoring import (
    TEXT_WEIGHT,
    SEMANTIC_WEIGHT,
    SPECIFICATION_WEIGHT,
    GRADE_WEIGHT,
    OTHER_ATTRIBUTES_WEIGHT,
)


def test_production_constants_invariant():
    """Verify that production scoring weights match frozen production weights."""
    assert TEXT_WEIGHT == 0.175
    assert SEMANTIC_WEIGHT == 0.400
    assert SPECIFICATION_WEIGHT == 0.250
    assert GRADE_WEIGHT == 0.125
    assert OTHER_ATTRIBUTES_WEIGHT == 0.050


def test_classify_pair_decision_logic():
    """Test decision categorization with scores and critical gate checks."""
    # 1. High score with all gates passing -> HIGH_CONFIDENCE
    pass_gates = json.dumps([{"field": "thread", "status": "PASS"}])
    assert classify_pair_decision(0.90, pass_gates) == "HIGH_CONFIDENCE"

    # 2. High score with UNKNOWN gate -> REVIEW
    unknown_gates = json.dumps([{"field": "thread", "status": "UNKNOWN"}])
    assert classify_pair_decision(0.90, unknown_gates) == "REVIEW"

    # 3. High score with CONFLICT gate -> REVIEW (blocked from HIGH_CONFIDENCE)
    conflict_gates = json.dumps([{"field": "thread", "status": "CONFLICT"}])
    assert classify_pair_decision(0.90, conflict_gates) == "REVIEW"

    # 4. Moderate score (> 0.45, <= 0.85) -> REVIEW
    assert classify_pair_decision(0.60, pass_gates) == "REVIEW"

    # 5. Low score (<= 0.45) with no conflicts -> DIFFERENT
    assert classify_pair_decision(0.40, pass_gates) == "DIFFERENT"

    # 6. Low score with CONFLICT -> REVIEW (conflict forces manual verification)
    assert classify_pair_decision(0.30, conflict_gates) == "REVIEW"


def test_feature_contributions_sum():
    """Test that feature contributions sum to the total score."""
    feats = [0.8, 0.9, 0.7, 0.6, 0.5]
    contribs = calculate_feature_contributions(feats, BASELINE_WEIGHTS)
    expected_sum = float(np.dot(feats, BASELINE_WEIGHTS))
    actual_sum = sum(contribs.values())
    assert pytest.approx(actual_sum, 1e-4) == expected_sum


def test_compute_pair_transitions():
    """Test dataframe transition calculations."""
    df = pd.DataFrame({
        "pair_id": ["P1", "P2"],
        "text_similarity": [0.8, 0.2],
        "semantic_similarity": [0.9, 0.2],
        "specification_similarity": [0.0, 0.0],
        "material_grade_similarity": [0.0, 0.0],
        "other_attributes_similarity": [1.0, 0.0],
        "critical_checks_json": [None, None],
        "label": [1, 0],
    })

    res = compute_pair_transitions(df)
    assert "score_baseline" in res.columns
    assert "score_lambda1" in res.columns
    assert "delta_lambda1" in res.columns
    assert "transition_lambda1" in res.columns

    # P1: Base score = 0.2*0.8 + 0.2*0.9 + 0.1*1.0 = 0.16 + 0.18 + 0.10 = 0.44 -> DIFFERENT
    # P1: L1 score = 0.2367*0.8 + 0.3192*0.9 + 0.1154*1.0 = 0.18936 + 0.28728 + 0.1154 = 0.592 -> REVIEW
    assert res.iloc[0]["decision_baseline"] == "DIFFERENT"
    assert res.iloc[0]["decision_lambda1"] == "REVIEW"
    assert res.iloc[0]["transition_lambda1"] == "DIFFERENT -> REVIEW"
