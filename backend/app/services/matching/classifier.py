from typing import Any

from app.services.matching.critical_gates import (
    evaluate_critical_gates,
    gates_allow_high_confidence,
)
from app.services.matching.scoring import calculate_match_score


# These are deliberately conservative starting points.
# They are NOT the final evaluated thresholds.
HIGH_CONFIDENCE_SCORE = 0.85
DIFFERENT_SCORE = 0.45


def classify_match(
    source: dict[str, Any],
    target: dict[str, Any],
) -> dict[str, Any]:
    """
    Score and classify a candidate material pair.

    Critical gates can prevent HIGH_CONFIDENCE even when
    the numerical similarity score is high.
    """

    scores = calculate_match_score(source, target)

    critical_checks = evaluate_critical_gates(source, target)

    final_score = scores["final_score"]

    has_unknown = any(
        check["status"] == "UNKNOWN"
        for check in critical_checks
    )

    has_conflict = any(
        check["status"] == "CONFLICT"
        for check in critical_checks
    )

    gates_pass = gates_allow_high_confidence(critical_checks)

    # Strong similarity is not sufficient by itself.
    if (
        final_score >= HIGH_CONFIDENCE_SCORE
        and gates_pass
    ):
        decision = "HIGH_CONFIDENCE"

    # Missing or conflicting critical specifications must
    # be reviewed by a human.
    elif has_unknown or has_conflict:
        decision = "REVIEW"

    # Ambiguous similarity should also be reviewed.
    elif final_score > DIFFERENT_SCORE:
        decision = "REVIEW"

    else:
        decision = "DIFFERENT"

    return {
        "scores": scores,
        "critical_checks": critical_checks,
        "decision": decision,
    }
