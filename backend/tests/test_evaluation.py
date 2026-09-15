import pytest
from app.services.evaluation.evaluate import (
    evaluate_production_safety,
    evaluate_hard_negatives_score_diagnostic,
    evaluate_committed_decisions,
    final_score,
    WEIGHTS,
)


def test_evaluate_production_safety_passes_with_review():
    records = [
        {
            "left": {"description": "MAT A"},
            "right": {"description": "MAT B"},
            "conflict_field": "grade",
        },
        {
            "left": {"description": "MAT C"},
            "right": {"description": "MAT D"},
            "conflict_field": "pressure_rating",
        },
    ]

    mock_classifier = lambda left, right: {
        "decision": "REVIEW",
        "scores": {"final_score": 0.90},
        "critical_checks": [{"field": "grade", "status": "CONFLICT"}],
    }

    results = evaluate_production_safety(records, classifier_fn=mock_classifier)

    assert results["total"] == 2
    assert results["high_confidence"] == 0
    assert results["review"] == 2
    assert results["different"] == 0
    assert results["false_high_confidence"] == 0
    assert results["false_high_confidence_rate"] == 0.0
    assert results["by_conflict_field"]["grade"]["REVIEW"] == 1
    assert results["by_conflict_field"]["grade"]["HIGH_CONFIDENCE"] == 0
    assert results["by_conflict_field"]["pressure_rating"]["REVIEW"] == 1


def test_evaluate_production_safety_detects_failure_on_high_confidence():
    records = [
        {
            "left": {"description": "MAT A"},
            "right": {"description": "MAT B"},
            "conflict_field": "grade",
        },
        {
            "left": {"description": "MAT C"},
            "right": {"description": "MAT D"},
            "conflict_field": "grade",
        },
    ]

    # Return HIGH_CONFIDENCE for one record (simulating safety failure)
    def mock_classifier(left, right):
        if left["description"] == "MAT A":
            return {"decision": "HIGH_CONFIDENCE"}
        return {"decision": "REVIEW"}

    results = evaluate_production_safety(records, classifier_fn=mock_classifier)

    assert results["total"] == 2
    assert results["high_confidence"] == 1
    assert results["review"] == 1
    assert results["different"] == 0
    assert results["false_high_confidence"] == 1
    assert results["false_high_confidence_rate"] == 0.5
    assert results["by_conflict_field"]["grade"]["HIGH_CONFIDENCE"] == 1
    assert results["by_conflict_field"]["grade"]["REVIEW"] == 1


def test_evaluate_production_safety_conflict_field_grouping():
    records = [
        {
            "left": {"description": "MAT 1"},
            "right": {"description": "MAT 2"},
            "conflict_field": "grade",
        },
        {
            "left": {"description": "MAT 3"},
            "right": {"description": "MAT 4"},
            "conflict_field": "grade",
        },
        {
            "left": {"description": "MAT 5"},
            "right": {"description": "MAT 6"},
            "conflict_field": "pressure_rating",
        },
        {
            "left": {"description": "MAT 7"},
            "right": {"description": "MAT 8"},
            "conflict_field": "dimension",
        },
    ]

    def mock_classifier(left, right):
        if left["description"] == "MAT 1":
            return {"decision": "REVIEW"}
        elif left["description"] == "MAT 3":
            return {"decision": "DIFFERENT"}
        elif left["description"] == "MAT 5":
            return {"decision": "REVIEW"}
        else:
            return {"decision": "DIFFERENT"}

    results = evaluate_production_safety(records, classifier_fn=mock_classifier)

    assert results["total"] == 4
    assert results["high_confidence"] == 0
    assert results["review"] == 2
    assert results["different"] == 2
    assert results["false_high_confidence"] == 0

    assert results["by_conflict_field"]["grade"]["total"] == 2
    assert results["by_conflict_field"]["grade"]["REVIEW"] == 1
    assert results["by_conflict_field"]["grade"]["DIFFERENT"] == 1

    assert results["by_conflict_field"]["pressure_rating"]["total"] == 1
    assert results["by_conflict_field"]["pressure_rating"]["REVIEW"] == 1

    assert results["by_conflict_field"]["dimension"]["total"] == 1
    assert results["by_conflict_field"]["dimension"]["DIFFERENT"] == 1


def test_evaluate_production_safety_raises_on_invalid_decision():
    records = [
        {"left": {}, "right": {}, "conflict_field": "grade"},
    ]
    mock_classifier = lambda l, r: {"decision": "INVALID"}

    with pytest.raises(ValueError, match="Unexpected classifier decision"):
        evaluate_production_safety(records, classifier_fn=mock_classifier)


def test_evaluate_score_only_diagnostic():
    rows = [
        {
            "text_similarity": "0.9",
            "semantic_similarity": "0.9",
            "specification_similarity": "0.9",
            "material_grade_similarity": "0.9",
            "other_attributes_similarity": "0.9",
        },
        {
            "text_similarity": "0.1",
            "semantic_similarity": "0.1",
            "specification_similarity": "0.1",
            "material_grade_similarity": "0.1",
            "other_attributes_similarity": "0.1",
        },
    ]
    diag = evaluate_hard_negatives_score_diagnostic(rows, threshold=0.50)
    assert diag["total"] == 2
    assert diag["score_above_threshold"] == 1
    assert diag["rate"] == 0.5


def test_weight_sum_is_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9
