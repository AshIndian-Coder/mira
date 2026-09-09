"""
Shared in-memory stores for the MIRA backend.

These are the authoritative runtime stores until Person 3 (Database)
replaces them with PostgreSQL-backed persistence.

All route modules should import from here — never define their own lists.
"""

from typing import Any

# ---------------------------------------------------------------------------
# Material master (populated by POST /api/materials/upload)
# ---------------------------------------------------------------------------
MATERIALS: list[dict[str, Any]] = []

# ---------------------------------------------------------------------------
# Match candidates (populated by POST /api/matching/run-batch)
# Each entry structure:
#   id, source_material_id, target_material_id,
#   scores: {...}, critical_checks: [...], engine_decision,
#   review_status: PENDING | APPROVED | REJECTED,
#   reviewer_id, reviewer_comments, reviewed_at
# ---------------------------------------------------------------------------
CANDIDATES: list[dict[str, Any]] = []

# Monotonic counter for candidate IDs
_candidate_id_counter: int = 0


def next_candidate_id() -> int:
    global _candidate_id_counter
    _candidate_id_counter += 1
    return _candidate_id_counter


def reset_stores() -> None:
    """Clear all stores — used in tests."""
    global _candidate_id_counter
    MATERIALS.clear()
    CANDIDATES.clear()
    _candidate_id_counter = 0
