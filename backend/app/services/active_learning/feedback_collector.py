"""Collect human approve/reject signals for active learning.

The feedback table is the training-signal store:
  * approve -> label 1 (same material)
  * reject  -> label 0 (different material)

``export_feedback.py`` (ml_pipeline) converts these rows into
``data/training/feedback_pairs.csv`` for Qwen fine-tuning.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.models.feedback import Feedback
from app.models.match_suggestion import MatchSuggestion
from app.utils.constants import FEEDBACK_APPROVE, FEEDBACK_REJECT

logger = get_logger("mira.feedback")


def store_feedback(
    db: Session,
    suggestion: MatchSuggestion,
    reviewer_id: int,
    action: str,
    reason: Optional[str] = None,
    commit: bool = False,
) -> Feedback:
    """Persist one review decision as a training signal."""
    normalized = (action or "").strip().lower()
    if normalized not in (FEEDBACK_APPROVE, FEEDBACK_REJECT):
        raise ValueError(f"action must be '{FEEDBACK_APPROVE}' or '{FEEDBACK_REJECT}'")
    entry = Feedback(
        match_suggestion_id=suggestion.id,
        reviewer_id=reviewer_id,
        action=normalized,
        reason=reason,
    )
    db.add(entry)
    db.flush()
    if commit:
        db.commit()
    logger.info(
        "Feedback stored: suggestion=%s action=%s reviewer=%s",
        suggestion.id,
        normalized,
        reviewer_id,
    )
    return entry


def get_training_feedback(
    db: Session,
    since: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Feedback rows joined with the pair descriptions (export helper)."""
    from sqlalchemy.orm import aliased

    from app.models.material import Material

    m1 = aliased(Material)
    m2 = aliased(Material)
    query = (
        db.query(Feedback, MatchSuggestion, m1, m2)
        .join(MatchSuggestion, Feedback.match_suggestion_id == MatchSuggestion.id)
        .join(m1, MatchSuggestion.material_1_id == m1.id)
        .join(m2, MatchSuggestion.material_2_id == m2.id)
    )
    if since is not None:
        query = query.filter(Feedback.timestamp >= since)

    rows = []
    for feedback, suggestion, m1, m2 in query.all():
        rows.append(
            {
                "feedback_id": feedback.id,
                "match_suggestion_id": suggestion.id,
                "action": feedback.action,
                "reason": feedback.reason,
                "label": 1 if feedback.action == FEEDBACK_APPROVE else 0,
                "material_1_id": m1.id,
                "material_2_id": m2.id,
                "material_1_desc": m1.description or "",
                "material_2_desc": m2.description or "",
                "final_confidence": suggestion.final_confidence,
                "timestamp": feedback.timestamp,
            }
        )
    return rows

