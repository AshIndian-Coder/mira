"""
Tests for Learned-Weight Stability, Sensitivity, and Robustness Analysis (Step 3).
"""

import numpy as np
import pandas as pd
import pytest

from app.services.evaluation.learned_weights_stability import (
    calculate_l2_distance,
    compute_weight_summary_stats,
    evaluate_subgroup_performance,
)
from app.services.evaluation.learned_weights_experiment import (
    BASELINE_WEIGHTS,
    FEATURE_NAMES,
    HIGH_CONFIDENCE_THRESHOLD,
    DIFFERENT_THRESHOLD,
)
from app.services.matching.scoring import (
    TEXT_WEIGHT,
    SEMANTIC_WEIGHT,
    SPECIFICATION_WEIGHT,
    GRADE_WEIGHT,
    OTHER_ATTRIBUTES_WEIGHT,
)


def test_production_constants_untouched():
    """Verify that production scoring weights match frozen production weights."""
    assert TEXT_WEIGHT == 0.175
    assert SEMANTIC_WEIGHT == 0.400
    assert SPECIFICATION_WEIGHT == 0.250
    assert GRADE_WEIGHT == 0.125
    assert OTHER_ATTRIBUTES_WEIGHT == 0.050
    assert HIGH_CONFIDENCE_THRESHOLD == 0.85
    assert DIFFERENT_THRESHOLD == 0.45


def test_l2_distance_calculation():
    """Test L2 distance computation against baseline."""
    # Distance from baseline to itself is 0.0
    assert calculate_l2_distance(BASELINE_WEIGHTS, BASELINE_WEIGHTS) == 0.0

    # Distance to a shifted vector
    shifted = BASELINE_WEIGHTS + np.array([0.1, -0.1, 0.0, 0.0, 0.0])
    expected_dist = float(np.linalg.norm(np.array([0.1, -0.1, 0.0, 0.0, 0.0])))
    assert pytest.approx(calculate_l2_distance(shifted, BASELINE_WEIGHTS), 1e-6) == expected_dist


def test_weight_summary_stats():
    """Test min, max, range, mean, std computation across configurations."""
    test_configs = {
        "cfg1": np.array([0.2, 0.2, 0.35, 0.15, 0.1]),
        "cfg2": np.array([0.3, 0.4, 0.1, 0.1, 0.1]),
    }
    stats = compute_weight_summary_stats(test_configs)
    assert len(stats) == 5
    assert "text_similarity" in stats
    assert stats["text_similarity"]["min"] == 0.2
    assert stats["text_similarity"]["max"] == 0.3
    assert stats["text_similarity"]["range"] == 0.1
    assert stats["text_similarity"]["mean"] == 0.25


def test_evaluate_subgroup_performance():
    """Test subgroup metric evaluator."""
    X = np.array([
        [0.8, 0.8, 0.8, 0.8, 0.8],
        [0.7, 0.7, 0.7, 0.7, 0.7],
        [0.2, 0.2, 0.2, 0.2, 0.2],
        [0.1, 0.1, 0.1, 0.1, 0.1],
    ])
    y = np.array([1, 1, 0, 0])
    df = pd.DataFrame({
        "category": ["FASTENERS", "FASTENERS", "FASTENERS", "FASTENERS"],
    })
    w = np.array([0.2, 0.2, 0.2, 0.2, 0.2])

    res = evaluate_subgroup_performance(X, y, df, w, "category", min_samples=2)
    assert "FASTENERS" in res
    assert res["FASTENERS"]["total"] == 4
    assert res["FASTENERS"]["positive_count"] == 2
    assert res["FASTENERS"]["negative_count"] == 2
    assert res["FASTENERS"]["roc_auc"] == 1.0
    assert res["FASTENERS"]["margin"] > 0
