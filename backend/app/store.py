"""
Shared Postgres-backed stores for the MIRA backend.

This used to hold plain in-memory lists. It's now backed by real
PostgreSQL persistence via PersistentList (see app/db_adapter.py), but
MATERIALS and CANDIDATES still behave exactly like lists from the
outside -- .append(), .extend(), .clear(), iteration, len(), and
in-place dict mutation (`c["review_status"] = "APPROVED"`) all still
work. No route file needs to change how it uses these.
"""

from app.db_adapter import (
    PersistentList,
    cnmc_table,
    materials_table,
    match_suggestions_table,
    next_id,
)

# ---------------------------------------------------------------------------
# Material master (populated by POST /api/materials/upload)
# ---------------------------------------------------------------------------
MATERIALS = PersistentList(materials_table)

# ---------------------------------------------------------------------------
# Match candidates (populated by POST /api/matching/run-batch)
# ---------------------------------------------------------------------------
CANDIDATES = PersistentList(match_suggestions_table)

# ---------------------------------------------------------------------------
# CNMC Master Registry
# ---------------------------------------------------------------------------
CNMC_REGISTRY = PersistentList(cnmc_table)

# ---------------------------------------------------------------------------
# Candidate ID generation.
#
# matching.py generates ALL candidate ids for a batch in memory before
# saving any of them (via one .extend() call at the end), so ids must be
# handed out from an in-memory counter -- querying the DB fresh each
# time would hand out the same id repeatedly within one batch. The
# counter reseeds itself from the DB's current max id the first time
# it's used after a restart, so ids stay correct and gap-free across
# restarts too.
# ---------------------------------------------------------------------------
_candidate_id_cache: int | None = None


def next_candidate_id() -> int:
    global _candidate_id_cache
    if _candidate_id_cache is None:
        _candidate_id_cache = next_id(match_suggestions_table)
    else:
        _candidate_id_cache += 1
    return _candidate_id_cache


def reset_stores() -> None:
    """Clear all stores -- used in tests."""
    global _candidate_id_cache
    # Order matters: match_suggestions has FKs to materials, so candidates
    # must be deleted BEFORE materials or Postgres raises ForeignKeyViolation.
    CANDIDATES.clear()
    MATERIALS.clear()
    CNMC_REGISTRY.clear()
    _candidate_id_cache = None
    from sqlalchemy import text
    from app.core.database import engine
    with engine.begin() as conn:
        try:
            conn.execute(text("ALTER SEQUENCE IF EXISTS cnmc_global_id_seq RESTART WITH 1;"))
            conn.execute(text("ALTER SEQUENCE IF EXISTS cnmc_id_seq RESTART WITH 1;"))
        except Exception:
            pass
