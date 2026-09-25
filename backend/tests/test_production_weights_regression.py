"""
Production Weights Regression Test for MIRA Matching Pipeline.

Asserts and proves that the justified and validated production weights (Arm C / CAND_0678)
are strictly frozen in backend/app/services/matching/scoring.py and integrated with the
production decision and critical-gate pipelines.
"""

from typing import Any
import numpy as np
import pytest

from app.services.matching.scoring import (
    TEXT_WEIGHT,
    SEMANTIC_WEIGHT,
    SPECIFICATION_WEIGHT,
    GRADE_WEIGHT,
    OTHER_ATTRIBUTES_WEIGHT,
    calculate_match_score,
)
from app.services.matching.classifier import (
    HIGH_CONFIDENCE_SCORE,
    DIFFERENT_SCORE,
    classify_match,
)
from app.services.matching.critical_gates import evaluate_critical_gates


def test_frozen_production_weight_constants():
    """Verify exact values of frozen production weights."""
    assert TEXT_WEIGHT == 0.175, f"Expected TEXT_WEIGHT=0.175, got {TEXT_WEIGHT}"
    assert SEMANTIC_WEIGHT == 0.400, f"Expected SEMANTIC_WEIGHT=0.400, got {SEMANTIC_WEIGHT}"
    assert SPECIFICATION_WEIGHT == 0.250, f"Expected SPECIFICATION_WEIGHT=0.250, got {SPECIFICATION_WEIGHT}"
    assert GRADE_WEIGHT == 0.125, f"Expected GRADE_WEIGHT=0.125, got {GRADE_WEIGHT}"
    assert OTHER_ATTRIBUTES_WEIGHT == 0.050, f"Expected OTHER_ATTRIBUTES_WEIGHT=0.050, got {OTHER_ATTRIBUTES_WEIGHT}"


def test_simplex_and_engineering_bounds():
    """Verify that production weights satisfy simplex and safety bounds."""
    weights = np.array([
        TEXT_WEIGHT,
        SEMANTIC_WEIGHT,
        SPECIFICATION_WEIGHT,
        GRADE_WEIGHT,
        OTHER_ATTRIBUTES_WEIGHT,
    ], dtype=np.float64)

    # 1. Simplex constraint: sum == 1.0
    assert abs(np.sum(weights) - 1.0) < 1e-7, f"Weights do not sum to 1.0: {np.sum(weights)}"

    # 2. Non-negativity
    assert np.all(weights >= 0.0), "Found negative weight"

    # 3. Constrained engineering bounds
    assert 0.10 <= TEXT_WEIGHT <= 0.25
    assert 0.20 <= SEMANTIC_WEIGHT <= 0.40
    assert 0.25 <= SPECIFICATION_WEIGHT <= 0.45
    assert 0.10 <= GRADE_WEIGHT <= 0.20
    assert 0.05 <= OTHER_ATTRIBUTES_WEIGHT <= 0.15


def test_calculate_match_score_with_frozen_weights():
    """Verify calculate_match_score correctly computes weighted sum with frozen weights."""
    mat_a = {
        "normalized_description": "SS 304 GATE VALVE 2 IN 150 LB",
        "material_grade": "SS304",
        "category": "Valve",
        "parsed_specifications": {
            "pressure_rating": {"value": 150.0, "unit": "LB"},
            "dimensions": {"value": 2.0, "unit": "IN"},
        },
        "other_attributes": {},
    }

    # Identical pair -> final_score == 1.0
    res_identical = calculate_match_score(mat_a, mat_a)
    assert res_identical["final_score"] == 1.0
    assert res_identical["text_similarity"] == 1.0
    assert res_identical["specification_similarity"] == 1.0
    assert res_identical["material_grade_similarity"] == 1.0
    assert res_identical["other_attributes_similarity"] == 1.0

    # Grade conflict only -> material_grade_similarity == 0.0 -> score reduced by exactly GRADE_WEIGHT (0.125)
    mat_b = dict(mat_a, material_grade="SS316")
    res_grade = calculate_match_score(mat_a, mat_b)
    expected_score = round(1.0 - GRADE_WEIGHT, 4)
    assert res_grade["material_grade_similarity"] == 0.0
    assert abs(res_grade["final_score"] - expected_score) < 1e-4


def test_decision_pipeline_thresholds_and_gates_preserved():
    """Verify that classifier thresholds and critical gates remain intact with new weights."""
    assert HIGH_CONFIDENCE_SCORE == 0.85
    assert DIFFERENT_SCORE == 0.45

    # Conflicting dimension pair must NEVER be HIGH_CONFIDENCE even if text/semantic are high
    mat_src = {
        "normalized_description": "HEX BOLT M12 X 50 MM GRADE 8.8",
        "material_grade": "8.8",
        "category": "Fastener",
        "parsed_specifications": {
            "metric_thread": {"nominal_diameter": 12.0, "pitch": None, "unit": "MM"},
            "dimensions": {"value": 50.0, "unit": "MM"},
        },
        "other_attributes": {},
    }
    mat_tgt = {
        "normalized_description": "HEX BOLT M12 X 60 MM GRADE 8.8",
        "material_grade": "8.8",
        "category": "Fastener",
        "parsed_specifications": {
            "metric_thread": {"nominal_diameter": 12.0, "pitch": None, "unit": "MM"},
            "dimensions": {"value": 60.0, "unit": "MM"},
        },
        "other_attributes": {},
    }

    checks = evaluate_critical_gates(mat_src, mat_tgt)
    has_conflict = any(c["status"] == "CONFLICT" for c in checks)
    assert has_conflict is True, "Expected dimension conflict between 50 MM and 60 MM"

    res_class = classify_match(mat_src, mat_tgt)
    assert res_class["decision"] != "HIGH_CONFIDENCE", "Conflict pair must not receive HIGH_CONFIDENCE"
    assert res_class["decision"] in {"REVIEW", "DIFFERENT"}
