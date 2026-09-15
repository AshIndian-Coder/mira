"""CPSE code <-> CNMC mapping endpoints.

    GET  /api/v1/mapping/cpse/{cpse_id}           All mappings for a CPSE
    GET  /api/v1/mapping/material/{material_id}   Mapping status of one material
    POST /api/v1/mapping/create                   Manually create a mapping
    GET  /api/v1/mapping/migration-status         Legacy code migration progress
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
from app.models.cpse import Cpse
from app.models.mapping import Mapping
from app.models.match_suggestion import MatchSuggestion
from app.models.material import Material
from app.models.user import User
from app.schemas.cnmc_schema import (
    MaterialMappingStatusResponse,
    MappingCreate,
    MappingListResponse,
    MappingResponse,
    MigrationStatusResponse,
)
from app.services.audit.audit_service import log_action
from app.utils.constants import (
    AUDIT_CREATE_MAPPING,
    MAPPING_STATUS_ACTIVE,
    MAPPING_TYPE_MANUAL,
    SUGGESTION_STATUS_PENDING,
)
from app.utils.helpers import utcnow

router = APIRouter(prefix="/mapping", tags=["mapping"])


@router.get("/cpse/{cpse_id}", response_model=MappingListResponse)
def mappings_for_cpse(
    cpse_id: int,
    status: Optional[str] = Query(default=MAPPING_STATUS_ACTIVE),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """All mappings for a CPSE (CPSEMappingView page)."""
    cpse = db.query(Cpse).filter(Cpse.id == cpse_id).first()
    if cpse is None:
        raise HTTPException(status_code=404, detail=f"CPSE {cpse_id} not found")

    material_subquery = db.query(Material.id).filter(Material.cpse_id == cpse_id)
    query = (
        db.query(Mapping)
        .filter(Mapping.material_id.in_(material_subquery))
        .join(Material)
        .join(CNMC)
    )
    if status:
        query = query.filter(Mapping.status == status)
    total = query.count()
    items = (
        query.order_by(desc(Mapping.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return MappingListResponse(
        items=[MappingResponse.from_orm_object(m) for m in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/material/{material_id}", response_model=MaterialMappingStatusResponse)
def material_mapping_status(
    material_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Is this material already mapped to a CNMC?"""
    material = db.query(Material).filter(Material.id == material_id).first()
    if material is None:
        raise HTTPException(status_code=404, detail="Material not found")
    mapping = (
        db.query(Mapping)
        .filter(Mapping.material_id == material_id, Mapping.status == MAPPING_STATUS_ACTIVE)
        .first()
    )
    pending_matches = (
        db.query(func.count(MatchSuggestion.id))
        .filter(
            MatchSuggestion.status == SUGGESTION_STATUS_PENDING,
            (MatchSuggestion.material_1_id == material_id)
            | (MatchSuggestion.material_2_id == material_id),
        )
        .scalar()
        or 0
    )
    return MaterialMappingStatusResponse(
        material_id=material_id,
        material_code=material.material_code,
        cpse_id=material.cpse_id,
        mapped=mapping is not None,
        mapping=MappingResponse.from_orm_object(mapping) if mapping else None,
        pending_matches=int(pending_matches),
    )


@router.post("/create", response_model=MappingResponse)
def create_mapping(
    payload: MappingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("create_mapping")),
):
    """Manually create a material -> CNMC mapping.

    Any existing active mapping for the material is superseded (one active
    mapping per material by design).
    """
    material = db.query(Material).filter(Material.id == payload.material_id).first()
    if material is None:
        raise HTTPException(status_code=404, detail="Material not found")
    cnmc = db.query(CNMC).filter(CNMC.id == payload.cnmc_id).first()
    if cnmc is None:
        raise HTTPException(status_code=404, detail="CNMC not found")

    existing = (
        db.query(Mapping)
        .filter(Mapping.material_id == material.id, Mapping.status == MAPPING_STATUS_ACTIVE)
        .first()
    )
    if existing:
        if existing.cnmc_id == cnmc.id:
            raise HTTPException(
                status_code=409, detail="Material already mapped to this CNMC"
            )
        existing.status = "superseded"

    mapping = Mapping(
        material_id=material.id,
        cnmc_id=cnmc.id,
        confidence_score=payload.confidence_score if payload.confidence_score is not None else 100.0,
        mapping_type=MAPPING_TYPE_MANUAL,
        approved_by=user.id,
        approved_at=utcnow(),
        status=MAPPING_STATUS_ACTIVE,
    )
    db.add(mapping)
    db.flush()
    log_action(
        db,
        user,
        AUDIT_CREATE_MAPPING,
        entity_type="mapping",
        entity_id=mapping.id,
        changes={
            "material_id": material.id,
            "material_code": material.material_code,
            "cnmc_id": cnmc.id,
            "cnmc_code": cnmc.cnmc_code,
        },
        commit=True,
    )
    db.refresh(mapping)
    return MappingResponse.from_orm_object(mapping)


@router.get("/migration-status", response_model=MigrationStatusResponse)
def migration_status(
    cpse_id: Optional[int] = Query(default=None, description="Per-CPSE or national progress"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Legacy material code migration progress (mapped vs total)."""
    material_query = db.query(Material).filter(Material.status == "active")
    if cpse_id:
        material_query = material_query.filter(Material.cpse_id == cpse_id)
    total_materials = material_query.count()

    mapped_query = (
        db.query(Mapping)
        .join(Material)
        .filter(Mapping.status == MAPPING_STATUS_ACTIVE)
    )
    if cpse_id:
        mapped_query = mapped_query.filter(Material.cpse_id == cpse_id)
    mapped_materials = mapped_query.count()

    pending_query = db.query(func.count(MatchSuggestion.id)).filter(
        MatchSuggestion.status == SUGGESTION_STATUS_PENDING
    )
    pending_matches = int(pending_query.scalar() or 0)
    cnmc_count = db.query(func.count(CNMC.id)).scalar() or 0

    progress = round(100.0 * mapped_materials / total_materials, 1) if total_materials else 0.0
    return MigrationStatusResponse(
        cpse_id=cpse_id,
        total_materials=total_materials,
        mapped_materials=mapped_materials,
        unmapped_materials=total_materials - mapped_materials,
        pending_matches=pending_matches,
        active_cnmc_count=int(cnmc_count),
        progress_percent=progress,
    )
