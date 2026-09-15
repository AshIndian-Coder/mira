"""CNMC (Common National Material Code) registry endpoints.

    GET  /api/v1/cnmc                       Browse registry (search/filter)
    GET  /api/v1/cnmc/{cnmc_id}             Detail + mapped materials
    POST /api/v1/cnmc/generate              Auto-generate CNMC for a cluster
    PUT  /api/v1/cnmc/{cnmc_id}             Update CNMC metadata
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.core.rbac import require_permission
from app.core.security import get_current_active_user
from app.db.postgres import get_db
from app.models.cnmc import CNMC
from app.models.mapping import Mapping
from app.models.material import Material
from app.models.user import User
from app.schemas.cnmc_schema import (
    CNMCDetailResponse,
    CNMCGenerateRequest,
    CNMCRegistryResponse,
    CNMCResponse,
    CNMCUpdate,
)
from app.schemas.material_schema import MaterialResponse
from app.services.audit.audit_service import log_action
from app.services.cnmc_generator.code_generator import create_cnmc_for_cluster
from app.utils.constants import AUDIT_CREATE_CNMC, AUDIT_UPDATE_CNMC, MAPPING_STATUS_ACTIVE

router = APIRouter(prefix="/cnmc", tags=["cnmc"])


def _to_response(cnmc: CNMC) -> CNMCResponse:
    return CNMCResponse(
        id=cnmc.id,
        cnmc_code=cnmc.cnmc_code,
        standardized_description=cnmc.standardized_description,
        category=cnmc.category,
        unspsc_code=cnmc.unspsc_code,
        nic_code=cnmc.nic_code,
        technical_specs=cnmc.technical_specs,
        created_at=cnmc.created_at,
        approved_by=cnmc.approved_by,
        approved_at=cnmc.approved_at,
        mapped_materials_count=len(cnmc.mappings),
    )


@router.get("", response_model=CNMCRegistryResponse)
def registry(
    search: Optional[str] = Query(default=None, description="Matches code or description"),
    category: Optional[str] = Query(default=None),
    unspsc_code: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """CNMC registry (CNMCRegistry page)."""
    query = db.query(CNMC)
    if search:
        like = f"%{search.strip()}%"
        query = query.filter(
            (CNMC.cnmc_code.ilike(like)) | (CNMC.standardized_description.ilike(like))
        )
    if category:
        query = query.filter(CNMC.category == category)
    if unspsc_code:
        query = query.filter(CNMC.unspsc_code == unspsc_code)
    total = query.count()
    items = (
        query.order_by(desc(CNMC.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return CNMCRegistryResponse(
        items=[_to_response(c) for c in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{cnmc_id}", response_model=CNMCDetailResponse)
def cnmc_detail(
    cnmc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Single CNMC with all mapped CPSE materials (traceability)."""
    cnmc = db.query(CNMC).filter(CNMC.id == cnmc_id).first()
    if cnmc is None:
        raise HTTPException(status_code=404, detail="CNMC not found")
    base = _to_response(cnmc).model_dump()
    materials = [
        MaterialResponse.model_validate(m.material)
        for m in cnmc.mappings
        if m.status == MAPPING_STATUS_ACTIVE and m.material is not None
    ]
    return CNMCDetailResponse(**base, mapped_materials=materials)


@router.post("/generate", response_model=CNMCDetailResponse)
def generate_cnmc(
    payload: CNMCGenerateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("generate_cnmc")),
):
    """Generate a CNMC for an explicit material cluster (manual grouping)."""
    materials = (
        db.query(Material).filter(Material.id.in_(payload.material_ids)).all()
    )
    if len(materials) < 2:
        raise HTTPException(
            status_code=400, detail="At least two existing materials are required"
        )
    material_dicts = [
        {
            "id": int(m.id),
            "cpse_id": m.cpse_id,
            "material_code": m.material_code,
            "description": m.description,
            "cleaned_description": m.cleaned_description,
            "attributes": dict(m.attributes or {}),
            "category": m.category,
        }
        for m in materials
    ]
    cnmc = create_cnmc_for_cluster(
        db, material_dicts, approved_by=user.id, mapping_type="manual", commit=False
    )
    log_action(
        db,
        user,
        AUDIT_CREATE_CNMC,
        entity_type="cnmc",
        entity_id=cnmc.id,
        changes={"cnmc_code": cnmc.cnmc_code, "material_ids": payload.material_ids, "reason": payload.reason},
        commit=True,
    )
    base = _to_response(cnmc).model_dump()
    return CNMCDetailResponse(
        **base,
        mapped_materials=[MaterialResponse.model_validate(m) for m in materials],
    )


@router.put("/{cnmc_id}", response_model=CNMCResponse)
def update_cnmc(
    cnmc_id: int,
    payload: CNMCUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("update_cnmc")),
):
    """Update CNMC metadata (standardization work)."""
    cnmc = db.query(CNMC).filter(CNMC.id == cnmc_id).first()
    if cnmc is None:
        raise HTTPException(status_code=404, detail="CNMC not found")
    changes = {}
    for field in ("standardized_description", "category", "unspsc_code", "nic_code", "technical_specs"):
        value = getattr(payload, field)
        if value is not None:
            changes[field] = {"old": getattr(cnmc, field), "new": value}
            setattr(cnmc, field, value)
    if not changes:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    log_action(
        db,
        user,
        AUDIT_UPDATE_CNMC,
        entity_type="cnmc",
        entity_id=cnmc.id,
        changes=changes,
        commit=True,
    )
    return _to_response(cnmc)

