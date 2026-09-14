from app.db_adapter import PersistentList, materials_table, match_suggestions_table, next_id
MATERIALS = PersistentList(materials_table)
CANDIDATES = PersistentList(match_suggestions_table)

_candidate_id_cache: int | None = None

def next_candidate_id() -> int:
    global _candidate_id_cache
    if _candidate_id_cache is None:
        _candidate_id_cache = next_id(match_suggestions_table)
    else:
        _candidate_id_cache += 1
    return _candidate_id_cache

def reset_stores() -> None:
    global _candidate_id_cache
    CANDIDATES.clear()
    MATERIALS.clear()
    _candidate_id_cache = None
