import numpy as np
import pytest

from app.services.evaluation.learned_weights_experiment import (
    BASELINE_WEIGHTS,
    FEATURE_NAMES,
    compute_dataset_metrics,
    compute_hard_negative_stats,
    evaluate_mira_decision_pipeline,
    optimize_weights,
    run_full_experiment,
)
from app.services.matching.scoring import (
    TEXT_WEIGHT,
    SEMANTIC_WEIGHT,
    SPECIFICATION_WEIGHT,
    GRADE_WEIGHT,
    OTHER_ATTRIBUTES_WEIGHT,
    calculate_match_score,
)


def test_frozen_feature_contract_and_baseline_invariants():
    """Verify frozen feature order and baseline production weights."""
    assert FEATURE_NAMES == [
        "text_similarity",
        "semantic_similarity",
        "specification_similarity",
        "material_grade_similarity",
        "other_attributes_similarity",
    ]
    np.testing.assert_allclose(
        BASELINE_WEIGHTS,
        np.array([0.20, 0.20, 0.35, 0.15, 0.10]),
        atol=1e-7,
    )
    assert abs(np.sum(BASELINE_WEIGHTS) - 1.0) < 1e-7

    # Verify production constants match frozen production weights (CAND_0678)
    assert TEXT_WEIGHT == 0.175
    assert SEMANTIC_WEIGHT == 0.400
    assert SPECIFICATION_WEIGHT == 0.250
    assert GRADE_WEIGHT == 0.125
    assert OTHER_ATTRIBUTES_WEIGHT == 0.050


def test_constrained_optimization_simplex_and_regularization():
    """Verify simplex constraints, non-negativity, and regularization behavior."""
    X_synthetic = np.array([
        [1.0, 0.9, 0.8, 1.0, 1.0],
        [0.9, 0.8, 0.7, 0.0, 1.0],
        [0.2, 0.3, 0.0, 0.0, 1.0],
        [0.1, 0.1, 0.1, 0.0, 1.0],
    ])
    y_synthetic = np.array([1, 1, 0, 0])

    # Unregularized
    res_unreg = optimize_weights(X_synthetic, y_synthetic, lambda_reg=0.0)
    w_unreg = res_unreg["weights"]
    assert len(w_unreg) == 5
    assert np.all(w_unreg >= 0.0)
    assert abs(np.sum(w_unreg) - 1.0) < 1e-6
    assert res_unreg["success"] is True

    # Heavy regularization pulls weights toward BASELINE_WEIGHTS
    res_reg = optimize_weights(X_synthetic, y_synthetic, lambda_reg=10.0)
    w_reg = res_reg["weights"]
    assert len(w_reg) == 5
    assert np.all(w_reg >= 0.0)
    assert abs(np.sum(w_reg) - 1.0) < 1e-6
    # Regularized weights should be closer to baseline than unregularized
    dist_unreg = np.sum((w_unreg - BASELINE_WEIGHTS) ** 2)
    dist_reg = np.sum((w_reg - BASELINE_WEIGHTS) ** 2)
    assert dist_reg < dist_unreg


def test_hard_negative_penalty_behavior():
    """Verify that hard-negative penalty suppresses scores on conflicting negative pairs."""
    X = np.array([
        [0.9, 0.9, 0.8, 0.5, 1.0],  # pos
        [0.85, 0.85, 0.75, 0.5, 1.0], # pos
        [0.95, 0.95, 0.0, 0.0, 1.0],  # HN with high text/semantic but 0 spec
        [0.2, 0.1, 0.0, 0.0, 1.0],    # easy neg
    ])
    y = np.array([1, 1, 0, 0])
    hn_indices = np.array([2])

    res_no_hn = optimize_weights(X, y, lambda_reg=0.0, lambda_hn=0.0)
    res_with_hn = optimize_weights(X, y, lambda_reg=0.0, lambda_hn=5.0, hn_indices=hn_indices)

    score_hn_before = X[2] @ res_no_hn["weights"]
    score_hn_after = X[2] @ res_with_hn["weights"]
    assert score_hn_after < score_hn_before


def test_metrics_and_decision_pipeline():
    """Verify dataset metrics computation and MIRA decision pipeline simulation."""
    X = np.array([
        [0.9, 0.9, 0.8, 0.5, 1.0],
        [0.8, 0.8, 0.7, 0.0, 1.0],
        [0.4, 0.3, 0.2, 0.0, 1.0],
        [0.2, 0.1, 0.0, 0.0, 1.0],
    ])
    y = np.array([1, 1, 0, 0])

    metrics = compute_dataset_metrics(X, y, BASELINE_WEIGHTS)
    assert metrics["roc_auc"] is not None
    assert 0.0 <= metrics["roc_auc"] <= 1.0
    assert metrics["same_distribution"]["count"] == 2
    assert metrics["different_distribution"]["count"] == 2

    hn_stats = compute_hard_negative_stats(X[:2], BASELINE_WEIGHTS)
    assert hn_stats["count"] == 2
    assert "0.85" in hn_stats["threshold_breakdown"]


def test_production_scoring_invariants_unchanged():
    """Verify that production scoring function calculate_match_score is unchanged."""
    source = {
        "normalized_description": "GATE VALVE CS 150 LB 2 IN",
        "parsed_specifications": {"dimensions": "2 IN", "pressure_rating": "150 LB"},
        "category": "VALVE",
        "material_grade": "CS",
        "other_attributes": {},
    }
    target = {
        "normalized_description": "GATE VALVE CS 150 LB 2 IN",
        "parsed_specifications": {"dimensions": "2 IN", "pressure_rating": "150 LB"},
        "category": "VALVE",
        "material_grade": "CS",
        "other_attributes": {},
    }
    res = calculate_match_score(source, target)
    assert res["final_score"] >= 0.99
    assert res["text_similarity"] == 1.0
    assert res["semantic_similarity"] >= 0.99
    assert res["specification_similarity"] == 1.0
    assert res["material_grade_similarity"] == 1.0
    assert res["other_attributes_similarity"] == 1.0


def test_full_experiment_report_structure():
    """Verify full experiment execution and resulting report schema."""
    report = run_full_experiment()
    assert "dataset_summary" in report
    assert report["dataset_summary"]["DEV"]["total"] == 5228
    assert report["dataset_summary"]["HELDOUT"]["total"] == 5284
    assert report["dataset_summary"]["HARD_NEGATIVES_300"]["total"] == 300
    assert len(report["baseline_weights"]) == 5
    assert "regularization_grid" in report
    assert "hn_penalty_grid" in report
    assert "configurations_evaluated" in report
    assert "baseline" in report["configurations_evaluated"]
    assert "unregularized" in report["configurations_evaluated"]
