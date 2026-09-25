"""
Unit tests for Step 7 Independent Stress-Test Construction & Evaluation.
"""

import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from app.services.matching.scoring import (
    TEXT_WEIGHT,
    SEMANTIC_WEIGHT,
    SPECIFICATION_WEIGHT,
    GRADE_WEIGHT,
    OTHER_ATTRIBUTES_WEIGHT,
)


def test_production_constants_invariant_step7():
    """Verify that production weights and thresholds match frozen production weights."""
    assert TEXT_WEIGHT == 0.175
    assert SEMANTIC_WEIGHT == 0.400
    assert SPECIFICATION_WEIGHT == 0.250
    assert GRADE_WEIGHT == 0.125
    assert OTHER_ATTRIBUTES_WEIGHT == 0.050


def test_stress_dataset_schema_and_provenance():
    """Verify stress test dataset schema and completeness of provenance fields."""
    dataset_path = Path("data/evaluation/stress_test_dataset.csv")
    assert dataset_path.exists(), "stress_test_dataset.csv must exist"

    df = pd.read_csv(dataset_path)
    required_cols = [
        "stress_case_id",
        "stress_population",
        "source_material_a",
        "source_material_b",
        "cpse_a",
        "cpse_b",
        "description_a",
        "description_b",
        "category",
        "label",
        "construction_reason",
        "critical_field",
        "source_dataset",
        "source_row_a",
        "source_row_b",
    ]
    for col in required_cols:
        assert col in df.columns, f"Missing required column: {col}"

    # Verify 4 populations exist
    populations = set(df["stress_population"].unique())
    expected_pops = {
        "SPARSE_TRUE_POSITIVE",
        "STRUCTURED_TRUE_POSITIVE",
        "CRITICAL_HARD_NEGATIVE",
        "NEAR_DUPLICATE_NEGATIVE",
    }
    assert populations == expected_pops, f"Expected populations {expected_pops}, got {populations}"

    # Verify counts in expected ranges
    counts = df["stress_population"].value_counts().to_dict()
    assert 100 <= counts["SPARSE_TRUE_POSITIVE"] <= 250
    assert 100 <= counts["STRUCTURED_TRUE_POSITIVE"] <= 250
    assert 200 <= counts["CRITICAL_HARD_NEGATIVE"] <= 400
    assert 100 <= counts["NEAR_DUPLICATE_NEGATIVE"] <= 250

    # Verify labels match population type
    assert (df[df["stress_population"] == "SPARSE_TRUE_POSITIVE"]["label"] == 1).all()
    assert (df[df["stress_population"] == "STRUCTURED_TRUE_POSITIVE"]["label"] == 1).all()
    assert (df[df["stress_population"] == "CRITICAL_HARD_NEGATIVE"]["label"] == 0).all()
    assert (df[df["stress_population"] == "NEAR_DUPLICATE_NEGATIVE"]["label"] == 0).all()

    # Verify critical_field is populated for CRITICAL_HARD_NEGATIVE
    crit_neg = df[df["stress_population"] == "CRITICAL_HARD_NEGATIVE"]
    assert crit_neg["critical_field"].notna().all()
    assert (crit_neg["critical_field"] != "NONE").all()


def test_leakage_audit_report_validity():
    """Verify that leakage report exists and contains zero pair ID or desc-pair overlap."""
    audit_path = Path("data/evaluation/stress_leakage_audit_report.json")
    assert audit_path.exists(), "stress_leakage_audit_report.json must exist"

    with open(audit_path) as f:
        report = json.load(f)

    for target, metrics in report["leakage_audits"].items():
        assert metrics["pair_id_overlap"] == 0, f"Pair ID overlap detected with {target}"
        assert metrics["exact_description_pair_overlap"] == 0, f"Desc-pair overlap detected with {target}"


def test_evaluation_report_completeness():
    """Verify that evaluation metrics report has complete population and per-field results."""
    eval_path = Path("data/evaluation/stress_test_evaluation_report.json")
    assert eval_path.exists(), "stress_test_evaluation_report.json must exist"

    with open(eval_path) as f:
        rep = json.load(f)

    assert "BASELINE" in rep["configurations"]
    assert "REG_1.00" in rep["configurations"]
    assert "REG_HN_2.00" in rep["configurations"]

    assert "overall_metrics" in rep
    assert "per_population_metrics" in rep
    assert "tier_transition_analysis" in rep
    assert "critical_field_breakdown" in rep

    # Verify all 7 critical fields are present in breakdown
    crit_fields = set(rep["critical_field_breakdown"].keys())
    expected_fields = {"dimensions", "metric_thread", "nominal_bore", "pressure_rating", "voltage_class", "material_grade", "schedule"}
    assert expected_fields.issubset(crit_fields), f"Missing fields in breakdown: {expected_fields - crit_fields}"
