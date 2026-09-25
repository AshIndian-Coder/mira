import json
from pathlib import Path
import numpy as np
import pytest

from app.services.evaluation.qwen_controlled_ab import (
    ARMS,
    FEATURE_NAMES,
    compute_confusion_matrix_at_50,
    evaluate_decisions_vectorized,
    evaluate_dataset,
    evaluate_hard_negatives,
    run_qwen_controlled_ab,
)
from app.services.matching.scoring import (
    TEXT_WEIGHT,
    SEMANTIC_WEIGHT,
    SPECIFICATION_WEIGHT,
    GRADE_WEIGHT,
    OTHER_ATTRIBUTES_WEIGHT,
)


def test_qwen_controlled_ab_arm_invariants():
    """Verify weight vector constraints across all experimental arms."""
    assert "Arm_A_CONTROL" in ARMS
    assert "Arm_B_CAND_0804" in ARMS
    assert "Arm_C_CAND_0678" in ARMS

    for arm_id, arm_info in ARMS.items():
        w = arm_info["weights"]
        assert len(w) == 5, f"{arm_id} must have 5 weights"
        assert np.all(w >= 0.0), f"{arm_id} has negative weights: {w}"
        assert abs(np.sum(w) - 1.0) < 1e-6, f"{arm_id} weights do not sum to 1.0: sum={np.sum(w)}"

    # Specific vector checks
    np.testing.assert_allclose(ARMS["Arm_A_CONTROL"]["weights"], [0.20, 0.20, 0.35, 0.15, 0.10], atol=1e-6)
    np.testing.assert_allclose(ARMS["Arm_B_CAND_0804"]["weights"], [0.200, 0.400, 0.250, 0.100, 0.050], atol=1e-6)
    np.testing.assert_allclose(ARMS["Arm_C_CAND_0678"]["weights"], [0.175, 0.400, 0.250, 0.125, 0.050], atol=1e-6)


def test_production_scoring_constants_match_frozen_arm_c():
    """Verify that production scoring constants match the frozen Arm C (CAND_0678) weights."""
    assert TEXT_WEIGHT == 0.175
    assert SEMANTIC_WEIGHT == 0.400
    assert SPECIFICATION_WEIGHT == 0.250
    assert GRADE_WEIGHT == 0.125
    assert OTHER_ATTRIBUTES_WEIGHT == 0.050


def test_confusion_matrix_at_50_calculation():
    """Verify confusion matrix computation at 0.50 threshold."""
    y_true = np.array([1, 1, 0, 0])
    scores = np.array([0.90, 0.40, 0.60, 0.20])
    # Positives: 0.90 >= 0.50 (TP), 0.40 < 0.50 (FN)
    # Negatives: 0.60 >= 0.50 (FP), 0.20 < 0.50 (TN)
    cm = compute_confusion_matrix_at_50(y_true, scores)
    assert cm["true_positives"] == 1
    assert cm["false_negatives"] == 1
    assert cm["false_positives"] == 1
    assert cm["true_negatives"] == 1
    assert cm["precision"] == 0.50
    assert cm["recall"] == 0.50
    assert cm["f1_score"] == 0.50
    assert cm["accuracy"] == 0.50


def test_vectorized_decision_simulation():
    """Verify vectorized decision simulator adheres to critical gates and threshold rules."""
    scores = np.array([0.90, 0.86, 0.70, 0.40, 0.30])
    has_conflict = np.array([False, True, False, False, False])
    has_unknown = np.array([False, False, False, False, False])
    gates_pass = np.array([True, False, True, True, True])

    res = evaluate_decisions_vectorized(scores, has_conflict, has_unknown, gates_pass)
    assert res["HIGH_CONFIDENCE"] == 1
    assert res["REVIEW"] == 2
    assert res["DIFFERENT"] == 2


def test_run_and_verify_controlled_ab_artifacts():
    """Run controlled A/B experiment and verify generated artifacts and safety constraints."""
    report = run_qwen_controlled_ab(
        output_report_path="data/evaluation/qwen_controlled_ab_report.json",
        output_csv_path="data/evaluation/qwen_controlled_ab_summary.csv",
    )

    report_path = Path("data/evaluation/qwen_controlled_ab_report.json")
    csv_path = Path("data/evaluation/qwen_controlled_ab_summary.csv")

    assert report_path.exists()
    assert csv_path.exists()

    assert "dataset_audit" in report
    assert report["dataset_audit"]["DEV"]["total"] == 5228
    assert report["dataset_audit"]["HELDOUT"]["total"] == 5284
    assert report["dataset_audit"]["HARD_NEGATIVES_300"]["total"] == 300

    arms = report["arms_evaluated"]
    for arm_id in ["Arm_A_CONTROL", "Arm_B_CAND_0804", "Arm_C_CAND_0678"]:
        assert arm_id in arms
        arm_data = arms[arm_id]

        # Invariant: zero HN in HIGH_CONFIDENCE
        assert arm_data["HARD_NEGATIVES_300"]["decision_distribution"]["HIGH_CONFIDENCE"] == 0
        assert arm_data["HARD_NEGATIVES_300"]["count_ge_0_85"] == 0
        assert arm_data["HARD_NEGATIVES_300"]["count_ge_0_80"] == 0

        # Invariant: DEV and HELDOUT metrics present
        assert arm_data["DEV"]["roc_auc"] > 0.70
        assert arm_data["HELDOUT"]["roc_auc"] > 0.70
        assert arm_data["DEV"]["score_separation"] > 0.15

        # Invariant: per-field breakdown on 300 HNs
        breakdown = arm_data["HARD_NEGATIVES_300"]["per_field_breakdown"]
        for f in ["dimensions", "metric_thread", "nominal_bore", "pressure_rating", "voltage_class"]:
            assert f in breakdown
            assert breakdown[f]["HIGH_CONFIDENCE"] == 0
