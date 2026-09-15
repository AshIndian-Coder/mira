"""SAP/ERP integration endpoints (SAPIntegrationStatus page).

    GET  /api/v1/sap/status      Per-CPSE sync status + connector mode
    POST /api/v1/sap/sync        Trigger material pull for a CPSE (or all)
    POST /api/v1/sap/push-cnmc   Push approved CNMC mappings back to SAP
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.rbac import require_permission
from app.core.security import get_current_active_user
from app.db.postgres import get_db
from app.integrations.sap_connector import get_sap_connector
from app.models.cpse import Cpse
from app.models.mapping import Mapping
from app.models.material import Material
from app.models.user import User
from app.services.audit.audit_service import log_action
from app.services.matching_engine.vector_search import get_vector_search_service
from app.utils.constants import (
    AUDIT_SAP_PUSH,
    AUDIT_SAP_SYNC,
    MAPPING_STATUS_ACTIVE,
    MATERIAL_STATUS_ACTIVE,
    SYNC_STATUS_FAILED,
    SYNC_STATUS_RUNNING,
    SYNC_STATUS_SUCCESS,
)
from app.utils.helpers import utcnow

router = APIRouter(prefix="/sap", tags=["sap"])


class SyncRequest(BaseModel):
    cpse_id: Optional[int] = Field(default=None, description="Single CPSE, or omit for all active")
    commit: bool = Field(default=True)


class PushRequest(BaseModel):
    cpse_id: int
    cnmc_id: Optional[int] = Field(default=None, description="Limit to one CNMC (default: all mapped for the CPSE)")


def _sync_one(db: Session, cpse: Cpse, user: User) -> dict:
    """Pull materials from SAP (or simulation) and persist them."""
    cpse.last_sync_status = SYNC_STATUS_RUNNING
    cpse.last_sync_error = None
    db.commit()

    connector = get_sap_connector()
    result = connector.pull_materials(cpse)
    error = result.get("error")
    rows = result.get("rows", [])

    inserted, updated, embedding_rows = 0, 0, []
    if not error:
        for row in rows:
            material_code = str(row.get("material_code") or "").strip()
            description = str(row.get("description") or "").strip()
            if not material_code or not description:
                continue
            existing = (
                db.query(Material)
                .filter(Material.cpse_id == cpse.id, Material.material_code == material_code)
                .first()
            )
            if existing:
                existing.description = description
                existing.uom = row.get("uom")
                existing.category = row.get("category") or existing.category
                if row.get("last_purchase_price") is not None:
                    existing.last_purchase_price = row["last_purchase_price"]
                if row.get("avg_annual_quantity") is not None:
                    existing.avg_annual_quantity = row["avg_annual_quantity"]
                existing.status = MATERIAL_STATUS_ACTIVE
                updated += 1
            else:
                from app.services.preprocessing import normalize_uom, preprocess_description
                from app.services.ner_extraction import extract_attributes

                cleaned = preprocess_description(description)
                attrs = extract_attributes(cleaned, row.get("category"))
                material = Material(
                    cpse_id=cpse.id,
                    material_code=material_code[:100],
                    description=description[:4000],
                    cleaned_description=cleaned,
                    attributes=attrs,
                    category=(row.get("category") or attrs.get("category") or None)[:100],
                    uom=(row.get("uom") or None),
                    uom_normalized=normalize_uom(row.get("uom")),
                    last_purchase_price=row.get("last_purchase_price"),
                    avg_annual_quantity=row.get("avg_annual_quantity"),
                    data_quality_score=80,
                    status=MATERIAL_STATUS_ACTIVE,
                )
                db.add(material)
                db.flush()
                inserted += 1
            embedding_rows.append(
                {
                    "id": int(existing.id if existing else material.id),
                    "cpse_id": cpse.id,
                    "category": (existing.category if existing else material.category) or "",
                    "cleaned_description": existing.cleaned_description if existing else material.cleaned_description,
                }
            )
        # Refresh attributes/cleaned for updated rows too
        for row_dict in embedding_rows:
            m = db.query(Material).filter(Material.id == row_dict["id"]).first()
            if m and not m.cleaned_description:
                from app.services.preprocessing import preprocess_description
                from app.services.ner_extraction import extract_attributes

                m.cleaned_description = preprocess_description(m.description)
                m.attributes = extract_attributes(m.cleaned_description, m.category)

        try:
            get_vector_search_service().index_materials(embedding_rows)
        except Exception:
            pass

    if error:
        cpse.last_sync_status = SYNC_STATUS_FAILED
        cpse.last_sync_error = error[:4000]
    else:
        cpse.last_sync_status = SYNC_STATUS_SUCCESS
    cpse.last_sync_at = utcnow()
    db.commit()

    log_action(
        db,
        user,
        AUDIT_SAP_SYNC,
        entity_type="cpse",
        entity_id=cpse.id,
        changes={
            "mode": connector.mode(),
            "inserted": inserted,
            "updated": updated,
            "status": cpse.last_sync_status,
            "error": error,
        },
        commit=True,
    )
    return {
        "cpse_id": cpse.id,
        "short_code": cpse.short_code,
        "status": cpse.last_sync_status,
        "inserted": inserted,
        "updated": updated,
        "error": error,
        "mode": connector.mode(),
    }


@router.get("/status")
def sap_status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """SAP sync status per CPSE + connector mode (SAPIntegrationStatus page)."""
    connector = get_sap_connector()
    cpses = db.query(Cpse).filter(Cpse.is_active == True).order_by(Cpse.short_code).all()  # noqa: E712
    items = [
        {
            "cpse_id": cpse.id,
            "name": cpse.name,
            "short_code": cpse.short_code,
            "sap_url": cpse.sap_url,
            "last_sync_at": cpse.last_sync_at.isoformat() if cpse.last_sync_at else None,
            "last_sync_status": cpse.last_sync_status,
            "last_sync_error": cpse.last_sync_error,
        }
        for cpse in cpses
    ]
    return {
        "mode": connector.mode(),
        "simulate": connector.simulate,
        "items": items,
    }


@router.post("/sync")
def trigger_sync(
    payload: SyncRequest = SyncRequest(),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("sap_sync")),
):
    """Trigger a material pull for one CPSE (or all active CPSEs)."""
    query = db.query(Cpse).filter(Cpse.is_active == True)  # noqa: E712
    if payload.cpse_id is not None:
        cpse = db.query(Cpse).filter(Cpse.id == payload.cpse_id).first()
        if cpse is None:
            raise HTTPException(status_code=404, detail="CPSE not found")
        results = [_sync_one(db, cpse, user)]
    else:
        results = [_sync_one(db, cpse, user) for cpse in query.all()]
    return {"results": results}


@router.post("/push-cnmc")
def push_cnmc(
    payload: PushRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("sap_sync")),
):
    """Push approved CNMC mappings back into the CPSE SAP system."""
    cpse = db.query(Cpse).filter(Cpse.id == payload.cpse_id).first()
    if cpse is None:
        raise HTTPException(status_code=404, detail="CPSE not found")

    query = (
        db.query(Mapping)
        .join(Material, Mapping.material_id == Material.id)
        .filter(Material.cpse_id == cpse.id, Mapping.status == MAPPING_STATUS_ACTIVE)
    )
    if payload.cnmc_id is not None:
        query = query.filter(Mapping.cnmc_id == payload.cnmc_id)
    mappings = query.all()
    if not mappings:
        raise HTTPException(status_code=404, detail="No active mappings found for this CPSE")

    payload_rows = [
        {
            "material_code": m.material.material_code if m.material else None,
            "cnmc_code": m.cnmc.cnmc_code if m.cnmc else None,
            "confidence": float(m.confidence_score) if m.confidence_score else None,
        }
        for m in mappings
    ]
    result = get_sap_connector().push_cnmc(cpse, payload_rows)
    log_action(
        db,
        user,
        AUDIT_SAP_PUSH,
        entity_type="cpse",
        entity_id=cpse.id,
        changes={"count": len(payload_rows), "result": result.get("status"), "cnmc_id": payload.cnmc_id},
        commit=True,
    )
    return {"cpse_id": cpse.id, **result}

