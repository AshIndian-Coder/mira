from typing import Any
import os

from app.services.matching.critical_gates import (
    evaluate_critical_gates,
    gates_allow_high_confidence,
)
from app.services.matching.scoring import calculate_match_score


# Conservative starting points.
# Final threshold must be selected using DEV evaluation.
HIGH_CONFIDENCE_SCORE = float(
    os.getenv("MIRA_HIGH_CONFIDENCE_SCORE", "0.85")
)

DIFFERENT_SCORE = float(
    os.getenv("MIRA_DIFFERENT_SCORE", "0.45")
)


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

    critical_checks = evaluate_critical_gates(
        source,
        target,
    )

    final_score = scores["final_score"]

    has_unknown = any(
        check["status"] == "UNKNOWN"
        for check in critical_checks
    )

    has_conflict = any(
        check["status"] == "CONFLICT"
        for check in critical_checks
    )

    gates_pass = gates_allow_high_confidence(
        critical_checks
    )

    if (
        final_score >= HIGH_CONFIDENCE_SCORE
        and gates_pass
    ):
        decision = "HIGH_CONFIDENCE"

    elif has_unknown or has_conflict:
        decision = "REVIEW"

    elif final_score > DIFFERENT_SCORE:
        decision = "REVIEW"

    else:
        decision = "DIFFERENT"

    return {
        "scores": scores,
        "critical_checks": critical_checks,
        "decision": decision,
    }
