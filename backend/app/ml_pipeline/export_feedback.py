"""
Step 2b - Export reviewer feedback from PostgreSQL as training pairs.

Joins feedback + match_suggestions + materials and writes
    data/training/feedback_pairs.csv
with the standard pair format:
    material_1_desc,material_2_desc,label      (approve=1, reject=0)

This closes the active-learning loop:
    DB feedback -> training pairs -> Qwen fine-tune -> better matching.

Weak labels: reviewer decisions are TRAINING SIGNALS, not verified ground
truth - they are down-weighted relative to curated pairs by the trainer.
"""
from __future__ import annotations

import argparse
import csv
import os
from typing import List, Tuple

from app.db.postgres import SessionLocal
from app.models.feedback import Feedback
from app.models.material import Material
from app.models.match_suggestion import MatchSuggestion


def export_pairs(since: str = None) -> Tuple[int, str]:
    """Export feedback-derived pairs. Returns (count, output path)."""
    from sqlalchemy.orm import aliased

    m1 = aliased(Material)
    m2 = aliased(Material)
    db = SessionLocal()
    try:
        query = (
            db.query(Feedback, MatchSuggestion, m1, m2)
            .join(MatchSuggestion, Feedback.match_suggestion_id == MatchSuggestion.id)
            .join(m1, MatchSuggestion.material_1_id == m1.id)
            .join(m2, MatchSuggestion.material_2_id == m2.id)
            .order_by(Feedback.timestamp)
        )
        if since:
            query = query.filter(Feedback.timestamp >= since)

        rows: List[Tuple[str, str, int]] = []
        seen = set()
        for feedback, suggestion, m1, m2 in query.all():
            label = 1 if feedback.action == "approve" else 0
            desc_1 = (m1.cleaned_description or m1.description or "").strip()
            desc_2 = (m2.cleaned_description or m2.description or "").strip()
            if not desc_1 or not desc_2:
                continue
            key = (tuple(sorted((desc_1, desc_2))), label)
            if key in seen:
                continue  # keep first decision for a pair (no contradictory rows)
            seen.add(key)
            rows.append((desc_1, desc_2, label))
        return len(rows), _write_csv(rows)
    finally:
        db.close()


def _write_csv(rows: List[Tuple[str, str, int]]) -> str:
    out_path = os.path.join(os.path.dirname(__file__), "data", "training", "feedback_pairs.csv")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["material_1_desc", "material_2_desc", "label"])
        writer.writerows(rows)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export reviewer feedback as training pairs")
    parser.add_argument("--since", default=None, help="ISO timestamp filter, e.g. 2026-01-01")
    args = parser.parse_args()
    count, out_path = export_pairs(since=args.since)
    print(f"Exported {count} feedback pairs -> {out_path}")


if __name__ == "__main__":
    main()
