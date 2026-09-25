import json
from pathlib import Path
import numpy as np
import pytest

from app.services.evaluation.qwen_learned_weights_experiment import (
    BASELINE_WEIGHTS,
    FEATURE_NAMES,
    SEARCH_BOUNDS,
    generate_candidate_grid,
    evaluate_decisions_vectorized,
    evaluate_dataset,
    evaluate_hard_negatives,
)
from app.services.matching.scoring import (
    TEXT_WEIGHT,
    SEMANTIC_WEIGHT,
    SPECIFICATION_WEIGHT,
    GRADE_WEIGHT,
    OTHER_ATTRIBUTES_WEIGHT,
)


def test_qwen_experiment_feature_contract_and_bounds():
    """Verify feature names, baseline weights, and constrained search bounds."""
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

    # Bounds check
    assert SEARCH_BOUNDS["text"] == (0.10, 0.25)
    assert SEARCH_BOUNDS["semantic"] == (0.20, 0.40)
    assert SEARCH_BOUNDS["specification"] == (0.25, 0.45)
    assert SEARCH_BOUNDS["material_grade"] == (0.10, 0.20)
    assert SEARCH_BOUNDS["other_attributes"] == (0.05, 0.15)


def test_candidate_grid_generation():
    """Verify deterministic candidate grid generation and baseline inclusion."""
    candidates = generate_candidate_grid(step=0.025)
    assert len(candidates) > 0

    # Verify every candidate satisfies constraints
    found_baseline = False
    for w in candidates:
        assert len(w) == 5
        assert np.all(w >= 0.0)
        assert abs(np.sum(w) - 1.0) < 1e-5
        assert SEARCH_BOUNDS["text"][0] - 1e-6 <= w[0] <= SEARCH_BOUNDS["text"][1] + 1e-6
        assert SEARCH_BOUNDS["semantic"][0] - 1e-6 <= w[1] <= SEARCH_BOUNDS["semantic"][1] + 1e-6
        assert SEARCH_BOUNDS["specification"][0] - 1e-6 <= w[2] <= SEARCH_BOUNDS["specification"][1] + 1e-6
        assert SEARCH_BOUNDS["material_grade"][0] - 1e-6 <= w[3] <= SEARCH_BOUNDS["material_grade"][1] + 1e-6
        assert SEARCH_BOUNDS["other_attributes"][0] - 1e-6 <= w[4] <= SEARCH_BOUNDS["other_attributes"][1] + 1e-6

        if np.allclose(w, BASELINE_WEIGHTS, atol=1e-5):
            found_baseline = True

    assert found_baseline is True


def test_production_decision_simulation():
    """Verify vectorized decision logic aligns with MIRA classifier rules."""
    scores = np.array([0.90, 0.86, 0.70, 0.40, 0.30])
    has_conflict = np.array([False, True, False, False, False])
    has_unknown = np.array([False, False, False, False, False])
    # In real critical gates, conflict or unknown causes gates_allow_high_confidence to be False
    gates_pass = np.array([True, False, True, True, True])

    res = evaluate_decisions_vectorized(scores, has_conflict, has_unknown, gates_pass)

    # Pair 0: 0.90 >= 0.85 and gates pass -> HIGH_CONFIDENCE
    # Pair 1: 0.86 >= 0.85 but gates_pass=False and has_conflict -> REVIEW
    # Pair 2: 0.70 > 0.45 -> REVIEW
    # Pair 3: 0.40 <= 0.45 and no conflict/unknown -> DIFFERENT
    # Pair 4: 0.30 <= 0.45 -> DIFFERENT
    assert res["HIGH_CONFIDENCE"] == 1
    assert res["REVIEW"] == 2
    assert res["DIFFERENT"] == 2
    assert res["decisions"][0] == "HIGH_CONFIDENCE"
    assert res["decisions"][1] == "REVIEW"
    assert res["decisions"][2] == "REVIEW"
    assert res["decisions"][3] == "DIFFERENT"
    assert res["decisions"][4] == "DIFFERENT"


def test_production_constants_remain_untouched():
    """Safety guard: verify production weights match frozen production weights."""
    assert TEXT_WEIGHT == 0.175
    assert SEMANTIC_WEIGHT == 0.400
    assert SPECIFICATION_WEIGHT == 0.250
    assert GRADE_WEIGHT == 0.125
    assert OTHER_ATTRIBUTES_WEIGHT == 0.050


def test_qwen_report_and_candidates_exist():
    """Verify that the experiment report and candidate csv exist and have valid structure."""
    report_path = Path("data/evaluation/qwen_learned_weights_experiment_report.json")
    csv_path = Path("data/evaluation/qwen_learned_weights_candidates.csv")

    assert report_path.exists(), "Report JSON does not exist"
    assert csv_path.exists(), "Candidates CSV does not exist"

    with open(report_path) as f:
        report = json.load(f)

    assert "dataset_audit" in report
    assert report["dataset_audit"]["DEV"]["total"] == 5228
    assert report["dataset_audit"]["HELDOUT"]["total"] == 5284
    assert report["dataset_audit"]["HARD_NEGATIVES_300"]["total"] == 300

    assert "baseline_qwen" in report
    assert "top_surviving_candidates" in report
    assert len(report["top_surviving_candidates"]) > 0

    # Verify best candidate properties
    best_cand = report["top_surviving_candidates"][0]
    assert best_cand["w_spec"] >= 0.25
    assert best_cand["w_grade"] >= 0.10
    assert best_cand["hn_count_ge_0_85"] == 0
    assert best_cand["hn_hc"] == 0
