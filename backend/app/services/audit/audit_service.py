"""Central audit logging service.

Every critical action (upload, approve/reject, CNMC create, mapping,
user admin, SAP sync) is logged here with:
  * user, action, entity, changes
  * a SHA-256 hash chain (prev_hash + payload hash) stored inside the
    ``changes`` JSONB column, enabling tamper verification of the whole
    trail (``verify_audit_chain``) without external infrastructure.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.models.audit_log import AuditLog
from app.models.user import User
from app.utils.helpers import utcnow

logger = get_logger("mira.audit")

GENESIS_HASH = "0" * 64


def _canonical_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _chain_hash(prev_hash: str, payload: Dict[str, Any]) -> str:
    digest = hashlib.sha256()
    digest.update(prev_hash.encode("utf-8"))
    digest.update(_canonical_json(payload).encode("utf-8"))
    return digest.hexdigest()


def log_action(
    db: Session,
    user: Optional[User],
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    changes: Optional[Dict[str, Any]] = None,
    commit: bool = False,
) -> AuditLog:
    """Write an audit log entry (with hash-chain integrity data).

    Pass ``user=None`` only for system actions; a user_id is required by
    the schema, so a system user id of 0 is used in that case.
    """
    if user is None:
        user_id = 0
        user_email = "system"
    else:
        user_id = user.id
        user_email = user.email

    previous = db.query(AuditLog).order_by(desc(AuditLog.id)).first()
    prev_hash = _extract_hash(previous) if previous else GENESIS_HASH
    timestamp = utcnow()

    data = {
        "user_email": user_email,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "changes": changes or {},
    }
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        changes={"data": data, "integrity": {"prev_hash": prev_hash, "hash": None}},
        timestamp=timestamp,
    )
    db.add(entry)
    db.flush()  # assign entry.id

    # Hash includes the row id so every entry is uniquely anchored.
    payload = dict(data, id=entry.id, timestamp=timestamp.isoformat())
    entry_hash = _chain_hash(prev_hash, payload)
    integrity = entry.changes.get("integrity", {}) if entry.changes else {}
    entry.changes = {"data": data, "integrity": {**integrity, "hash": entry_hash}}
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(entry, "changes")
    db.flush()

    if commit:
        db.commit()
    logger.info(
        "AUDIT user=%s action=%s entity=%s:%s hash=%s",
        user_email,
        action,
        entity_type,
        entity_id,
        entry_hash[:12],
    )
    return entry


def _extract_hash(entry: Optional[AuditLog]) -> str:
    if entry is None or not entry.changes:
        return GENESIS_HASH
    integrity = entry.changes.get("integrity") or {}
    return integrity.get("hash") or GENESIS_HASH


def get_audit_trail(
    db: Session,
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    page: int = 1,
    page_size: int = 50,
) -> Dict[str, Any]:
    """Query the audit trail with filters (AuditTrail page)."""
    query = db.query(AuditLog)
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if from_date:
        query = query.filter(AuditLog.timestamp >= from_date)
    if to_date:
        query = query.filter(AuditLog.timestamp <= to_date)

    total = query.count()
    items = (
        query.order_by(desc(AuditLog.timestamp))
        .offset((max(1, page) - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def verify_audit_chain(db: Session) -> Dict[str, Any]:
    """Recompute the hash chain across the whole audit_logs table.

    Returns {"valid": bool, "total": int, "first_invalid_id": int|None}.
    """
    entries = db.query(AuditLog).order_by(AuditLog.id).all()
    prev_hash = GENESIS_HASH
    for entry in entries:
        integrity = (entry.changes or {}).get("integrity") or {}
        stored_hash = integrity.get("hash")
        data = (entry.changes or {}).get("data") or {}
        if not stored_hash:
            return {"valid": False, "total": len(entries), "first_invalid_id": entry.id}
        payload = dict(
            data,
            id=entry.id,
            timestamp=(entry.timestamp.isoformat() if entry.timestamp else ""),
        )
        expected = _chain_hash(prev_hash, payload)
        if expected != stored_hash or integrity.get("prev_hash") != prev_hash:
            return {"valid": False, "total": len(entries), "first_invalid_id": entry.id}
        prev_hash = stored_hash
    return {"valid": True, "total": len(entries), "first_invalid_id": None}

