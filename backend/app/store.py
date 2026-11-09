"""PostgreSQL-backed material, candidate, and CNMC stores."""

from sqlalchemy import text

from app.core.database import engine
from app.db_adapter import (
    PersistentList,
    cnmc_table,
    materials_table,
    match_suggestions_table,
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
# ---------------------------------------------------------------------------

def reserve_candidate_ids(count: int) -> list[int]:
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("count must be a non-negative integer")
    if count == 0:
        return []

    with engine.begin() as connection:
        values = connection.execute(
            text("""
                SELECT nextval('match_suggestions_id_seq')
                FROM generate_series(1, :count)
            """),
            {"count": count},
        ).scalars().all()

    if len(values) != count:
        raise RuntimeError("PostgreSQL did not reserve the requested candidate IDs")
    return [int(value) for value in values]


def next_candidate_id() -> int:
    return reserve_candidate_ids(1)[0]


def reset_stores() -> None:
    """Clear integration-test stores. Never call this from production routes."""
    # Order matters: match_suggestions has FKs to materials, so candidates
    # must be deleted BEFORE materials or Postgres raises ForeignKeyViolation.
    CANDIDATES.clear()
    MATERIALS.clear()
    CNMC_REGISTRY.clear()
    with engine.begin() as conn:
        conn.execute(text("ALTER SEQUENCE IF EXISTS cnmc_global_id_seq RESTART WITH 1;"))
        conn.execute(text("ALTER SEQUENCE IF EXISTS cnmc_id_seq RESTART WITH 1;"))
