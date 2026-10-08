"""
Audit trail route.

GET /api/audit          — paginated append-only audit log
GET /api/audit/export   — full audit log as JSON (for governance/export)
"""

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.rbac import require_permission
from app.core.security import get_current_active_user
from app.db_adapter import PersistentList, audit_logs_table
from app.models.user import User

router = APIRouter(prefix="/audit", tags=["Audit"])

# Append-only, Postgres-backed — review route appends to this on every decision.
AUDIT_EVENTS = PersistentList(audit_logs_table)


def _apply_filters(
    events: list[dict[str, Any]],
    event_type: str | None,
    actor: str | None,
    source_cpse: str | None,
    target_cpse: str | None,
    cpse: str | None,
) -> list[dict[str, Any]]:
    """Shared filtering for the list and export endpoints.

    `cpse` matches either side of the pair, which is the useful view for
    "show me everything touching NTPC". `source_cpse` / `target_cpse` are
    for when direction matters.
    """
    filtered = events

    if event_type:
        wanted = event_type.upper()
        filtered = [e for e in filtered if e.get("event_type") == wanted]

    if actor:
        filtered = [e for e in filtered if e.get("actor") == actor]

    if source_cpse:
        wanted = source_cpse.strip().upper()
        filtered = [
            e for e in filtered
            if (e.get("source_cpse") or "").strip().upper() == wanted
        ]

    if target_cpse:
        wanted = target_cpse.strip().upper()
        filtered = [
            e for e in filtered
            if (e.get("target_cpse") or "").strip().upper() == wanted
        ]

    if cpse:
        wanted = cpse.strip().upper()
        filtered = [
            e for e in filtered
            if wanted in {
                (e.get("source_cpse") or "").strip().upper(),
                (e.get("target_cpse") or "").strip().upper(),
            }
        ]

    return filtered


@router.get("")
def list_audit_events(
    event_type: str | None = Query(None, description="e.g. MATCH_APPROVED, MATCH_REJECTED"),
    actor: str | None = Query(None, description="Filter by reviewer user_id"),
    source_cpse: str | None = Query(None, description="Filter by originating CPSE short code"),
    target_cpse: str | None = Query(None, description="Filter by counterpart CPSE short code"),
    cpse: str | None = Query(None, description="Filter by either side of the pair"),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(require_permission("view_audit")),
):
    """Paginated audit log in reverse-chronological order."""
    filtered = _apply_filters(
        list(reversed(AUDIT_EVENTS)),
        event_type=event_type,
        actor=actor,
        source_cpse=source_cpse,
        target_cpse=target_cpse,
        cpse=cpse,
    )

    total = len(filtered)
    paginated = filtered[skip: skip + limit]

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "events": paginated,
    }


@router.get("/export")
def export_audit_log(
    event_type: str | None = Query(None),
    actor: str | None = Query(None),
    source_cpse: str | None = Query(None),
    target_cpse: str | None = Query(None),
    cpse: str | None = Query(None),
    current_user: User = Depends(require_permission("view_audit")),
):
    """Full audit log — all events, oldest first. For governance / download."""
    filtered = _apply_filters(
        list(AUDIT_EVENTS),
        event_type=event_type,
        actor=actor,
        source_cpse=source_cpse,
        target_cpse=target_cpse,
        cpse=cpse,
    )
    return {
        "total": len(filtered),
        "events": filtered,
    }