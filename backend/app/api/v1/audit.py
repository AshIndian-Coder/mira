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


@router.get("")
def list_audit_events(
    event_type: str | None = Query(None, description="e.g. MATCH_APPROVED, MATCH_REJECTED"),
    actor: str | None = Query(None, description="Filter by reviewer user_id"),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(require_permission("view_audit")),
):
    """Paginated audit log in reverse-chronological order."""
    filtered = list(reversed(AUDIT_EVENTS))

    if event_type:
        filtered = [e for e in filtered if e["event_type"] == event_type.upper()]

    if actor:
        filtered = [e for e in filtered if e.get("actor") == actor]

    total = len(filtered)
    paginated = filtered[skip: skip + limit]

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "events": paginated,
    }


@router.get("/export")
def export_audit_log(current_user: User = Depends(require_permission("view_audit"))):
    """Full audit log — all events, oldest first. For governance / download."""
    return {
        "total": len(AUDIT_EVENTS),
        "events": list(AUDIT_EVENTS),
    }
