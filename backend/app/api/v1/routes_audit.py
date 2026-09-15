"""Audit trail & integrity verification endpoints (AuditTrail page).

    GET /api/v1/audit/trail       Filterable audit log
    GET /api/v1/audit/verify      Verify the SHA-256 hash chain integrity
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.rbac import require_permission
from app.db.postgres import get_db
from app.models.user import User
from app.services.audit.audit_service import get_audit_trail, verify_audit_chain
from app.utils.helpers import format_datetime

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/trail")
def audit_trail(
    user_id: Optional[int] = Query(default=None),
    action: Optional[str] = Query(default=None, description="e.g. approve_match, create_cnmc"),
    entity_type: Optional[str] = Query(default=None),
    from_date: Optional[datetime] = Query(default=None),
    to_date: Optional[datetime] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("view_audit")),
):
    """Filterable audit log (who, what, when, which entity)."""
    result = get_audit_trail(
        db,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        from_date=from_date,
        to_date=to_date,
        page=page,
        page_size=page_size,
    )
    items = []
    for entry in result["items"]:
        changes = entry.changes or {}
        items.append(
            {
                "id": entry.id,
                "user_id": entry.user_id,
                "user_email": (
                    entry.user.email
                    if entry.user
                    else ("system" if entry.user_id == 0 else "unknown")
                ),
                "action": entry.action,
                "entity_type": entry.entity_type,
                "entity_id": entry.entity_id,
                "changes": changes.get("data", {}).get("changes", changes.get("data", {})),
                "integrity": changes.get("integrity", {}),
                "timestamp": format_datetime(entry.timestamp),
            }
        )
    return {
        "items": items,
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
    }


@router.get("/verify")
def verify_integrity(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("view_audit")),
):
    """Recompute the hash chain and report trail integrity."""
    return verify_audit_chain(db)

