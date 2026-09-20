"""
Tests for CNMC Best-vs-Second-Best Margin Analysis and Evaluation logic.
"""

import pytest
from app.services.evaluation.cnmc_margin_analysis import (
    calculate_distribution_stats,
    compute_margin_bucket_breakdown,
    compute_score_vs_margin_matrix,
)
from app.services.matching.cnmc_matcher import compute_cnmc_candidate_margin


def test_distribution_stats_empty():
    """Empty list returns None for statistics."""
    stats = calculate_distribution_stats([])
    assert stats["count"] == 0
    assert stats["mean"] is None
    assert stats["median"] is None
    assert stats["min"] is None
    assert stats["max"] is None


def test_distribution_stats_values():
    """Verify statistical moments and percentiles calculation."""
    vals = [0.01, 0.02, 0.05, 0.10, 0.20, 0.50]
    stats = calculate_distribution_stats(vals)
    assert stats["count"] == 6
    assert stats["min"] == 0.01
    assert stats["max"] == 0.50
    assert stats["mean"] == pytest.approx(0.1467, abs=1e-3)
    assert stats["median"] == pytest.approx(0.075, abs=1e-3)
    assert stats["p10"] is not None
    assert stats["p90"] is not None


def test_margin_calculation_single_candidate():
    """Requirement 3: Exactly 1 candidate yields margin=None and second_best_score=None."""
    proposals = [{"final_score": 0.92, "cnmc_code": "CNMC-1"}]
    margin_info = compute_cnmc_candidate_margin(proposals)
    assert margin_info["best_score"] == 0.92
    assert margin_info["second_best_score"] is None
    assert margin_info["score_margin"] is None


def test_margin_calculation_zero_candidates():
    """Requirement 4: Zero candidates yields all None."""
    proposals = []
    margin_info = compute_cnmc_candidate_margin(proposals)
    assert margin_info["best_score"] is None
    assert margin_info["second_best_score"] is None
    assert margin_info["score_margin"] is None


def test_correct_and_incorrect_top_1_margin_bucketing():
    """
    Requirements 1 & 2: Correct vs incorrect top-1 candidate margin bucketing.
    """
    records = [
        {"query_id": "Q1", "score_margin": 0.005, "top_1_correct": False},
        {"query_id": "Q2", "score_margin": 0.008, "top_1_correct": True},
        {"query_id": "Q3", "score_margin": 0.015, "top_1_correct": True},
        {"query_id": "Q4", "score_margin": 0.040, "top_1_correct": True},
        {"query_id": "Q5", "score_margin": 0.150, "top_1_correct": True},
        {"query_id": "Q6", "score_margin": None, "top_1_correct": True},  # Single candidate
    ]
    buckets = compute_margin_bucket_breakdown(records)
    b0 = next(b for b in buckets if b["bucket"] == "[0.00, 0.01)")
    assert b0["total_queries"] == 2
    assert b0["correct_top_1"] == 1
    assert b0["incorrect_top_1"] == 1
    assert b0["top_1_accuracy"] == 0.50

    b1 = next(b for b in buckets if b["bucket"] == "[0.01, 0.02)")
    assert b1["total_queries"] == 1
    assert b1["correct_top_1"] == 1
    assert b1["top_1_accuracy"] == 1.0


def test_deterministic_ordering_tie_breaking():
    """Requirement 5: Deterministic ordering preserved for tied scores."""
    proposals = [
        {"final_score": 0.85, "cnmc_code": "CNMC-002"},
        {"final_score": 0.85, "cnmc_code": "CNMC-001"},
    ]
    # Sorted by (-final_score, cnmc_code)
    proposals.sort(key=lambda p: (-p["final_score"], p["cnmc_code"]))
    assert proposals[0]["cnmc_code"] == "CNMC-001"
    assert proposals[1]["cnmc_code"] == "CNMC-002"

    margin_info = compute_cnmc_candidate_margin(proposals)
    assert margin_info["best_score"] == 0.85
    assert margin_info["second_best_score"] == 0.85
    assert margin_info["score_margin"] == 0.0


def test_no_production_decision_change_by_margin():
    """
    Requirement 6: Margin is pure observability; does NOT alter decisions.
    """
    records = [
        {
            "best_score": 0.90,
            "score_margin": 0.005,  # Very tight margin
            "top_1_correct": True,
            "engine_decision": "HIGH_CONFIDENCE",  # Unaltered
        },
        {
            "best_score": 0.90,
            "score_margin": 0.500,  # Wide margin
            "top_1_correct": True,
            "engine_decision": "HIGH_CONFIDENCE",
        },
    ]
    matrix = compute_score_vs_margin_matrix(records)
    cell_tight = next(
        c for c in matrix
        if c["score_range"] == ">=0.85 (High)" and c["margin_range"] == "<0.02 (Tight)"
    )
    assert cell_tight["total"] == 1
    assert cell_tight["HIGH_CONFIDENCE"] == 1
    assert cell_tight["REVIEW"] == 0
