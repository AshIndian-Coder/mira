"""
CPSE-to-NMC mappings route.

GET  /api/mappings          — list all established CPSE → NMC mappings
POST /api/mappings/generate — generate mapping suggestions from APPROVED candidates
GET  /api/mappings/export   — export mappings as flat records (ERP / CSV integration)

Note: Full Common Material Record + NMC generation is Phase 7 (Person 5).
This route provides the API surface so the frontend can connect now.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import store
from app.core.rbac import require_permission
from app.core.security import get_current_active_user
from app.db_adapter import PersistentList, mappings_table, next_id
from app.models.user import User
from app.services.clustering.service import cluster_approved_pairs
from app.services.cnmc.service import generate_or_get_cnmc
from app.services.harmonization.service import build_common_material_record
from app.services.matching.cnmc_matcher import attach_material_to_mapping

router = APIRouter(prefix="/mappings", tags=["Mappings"])

# Postgres-backed mapping store: each entry =
#   { id, nmc, cpse_mappings: [{cpse, material_code, description}], status, created_at }
MAPPINGS = PersistentList(mappings_table)


def _next_mapping_id() -> int:
    return next_id(mappings_table)



@router.get("")
def list_mappings(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
):
    """Return all generated CPSE → NMC mappings."""
    total = len(MAPPINGS)
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "mappings": MAPPINGS[skip: skip + limit],
    }


@router.post("/generate")
def generate_mappings(current_user: User = Depends(require_permission("create_mapping"))):
    """
    Build CPSE→NMC mapping suggestions from APPROVED candidate pairs.

    Algorithm:
    1. Collect all APPROVED candidates.
    2. Group connected material IDs into clusters using Union-Find.
    3. For each cluster, create one NMC and map every CPSE code to it.

    CRITICAL: Source CPSE codes are preserved; NMC is additive, not replacing.
    """
    approved = [
        c for c in store.CANDIDATES
        if c["review_status"] in {"APPROVED", "AUTO_APPROVED"}
    ]

    if not approved:
        return {
            "status": "no_approved_candidates",
            "mappings_created": 0,
            "message": "No approved or auto-approved candidates available to generate mappings.",
        }

    clusters = cluster_approved_pairs(approved)

    # Build material index for lookup
    mat_index: dict[int, dict[str, Any]] = {m["id"]: m for m in store.MATERIALS}

    # Skip clusters that already have a mapping
    existing_ids: set[frozenset] = set()
    for mapping in MAPPINGS:
        ids = frozenset(
            entry["material_id"] for entry in mapping.get("cpse_mappings", [])
        )
        existing_ids.add(ids)

    new_mappings = []
    for cluster_ids in clusters.values():
        cluster_set = frozenset(cluster_ids)
        if cluster_set in existing_ids:
            continue

        cluster_materials = [
            mat_index[mid]
            for mid in sorted(cluster_ids)
            if mid in mat_index
        ]

        if not cluster_materials:
            continue

        common_material_record = build_common_material_record(
            cluster_materials
        )

        user_db_id = getattr(current_user, "id", None) if current_user else None
        cnmc_info = generate_or_get_cnmc(
            materials=cluster_materials,
            cmr=common_material_record,
            approved_by=user_db_id,
        )
        cnmc_code = cnmc_info["cnmc_code"]
        mapping_id = _next_mapping_id()

        cpse_entries = []
        for mid in sorted(cluster_ids):
            mat = mat_index.get(mid)
            if mat:
                cpse_entries.append({
                    "material_id": mid,
                    "cpse": mat["cpse"],
                    "material_code": mat["material_code"],
                    "description": mat["description"],
                    "category": mat.get("category"),
                    "material_grade": mat.get("material_grade"),
                })

        from datetime import datetime, timezone
        mapping_record: dict[str, Any] = {
            "id": mapping_id,
            "nmc": cnmc_code,
            "cpse_mappings": cpse_entries,
            "cluster_size": len(cluster_ids),
            "status": "PROVISIONAL",
            "common_material_record": common_material_record,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        MAPPINGS.append(mapping_record)
        new_mappings.append(mapping_record)
        existing_ids.add(cluster_set)

    return {
        "status": "success",
        "mappings_created": len(new_mappings),
        "total_mappings": len(MAPPINGS),
        "mappings": new_mappings,
    }


@router.post("/{mapping_id}/approve")
def approve_mapping(
    mapping_id: int,
    current_user: User = Depends(require_permission("create_mapping")),
):
    """
    Data steward / Admin approves a PROVISIONAL mapping and its Common Material Record.
    - Sets mapping status to APPROVED.
    - Sets common_material_record approval_status to APPROVED.
    - Emits a MAPPING_APPROVED audit log event.
    """
    target_mapping = None
    for m in MAPPINGS:
        if m["id"] == mapping_id:
            target_mapping = m
            break

    if target_mapping is None:
        raise HTTPException(status_code=404, detail=f"Mapping {mapping_id} not found")

    if target_mapping.get("status") == "APPROVED":
        return {
            "status": "already_approved",
            "mapping": target_mapping,
            "message": f"Mapping {mapping_id} is already approved",
        }

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    actor_identity = current_user.email if (current_user and current_user.email) else "steward"

    target_mapping["status"] = "APPROVED"

    cmr = dict(target_mapping.get("common_material_record") or {})
    if cmr:
        cmr["approval_status"] = "APPROVED"
        target_mapping["common_material_record"] = cmr

    from app.api.v1.audit import AUDIT_EVENTS
    AUDIT_EVENTS.append({
        "event_type": "MAPPING_APPROVED",
        "candidate_id": None,
        "source_code": target_mapping.get("nmc"),
        "target_code": target_mapping.get("nmc"),
        "source_cpse": "MIRA",
        "target_cpse": "MIRA",
        "actor": actor_identity,
        "comments": f"Mapping cluster {mapping_id} ({target_mapping.get('nmc')}) approved by data steward.",
        "final_score": 1.0,
        "timestamp": now,
    })

    return {
        "status": "success",
        "mapping": target_mapping,
    }


@router.get("/{mapping_id}")
def get_mapping(
    mapping_id: int,
    current_user: User = Depends(get_current_active_user),
):
    for m in MAPPINGS:
        if m["id"] == mapping_id:
            return m
    raise HTTPException(status_code=404, detail=f"Mapping {mapping_id} not found")


@router.get("/export/flat")
def export_mappings_flat(current_user: User = Depends(get_current_active_user)):
    """
    Flat row-per-CPSE-code export.
    Format: cpse, material_code, nmc, category
    Suitable for CSV download or ERP import.
    """
    rows = []
    for mapping in MAPPINGS:
        for entry in mapping.get("cpse_mappings", []):
            rows.append({
                "nmc": mapping["nmc"],
                "cpse": entry["cpse"],
                "cpse_material_code": entry["material_code"],
                "description": entry["description"],
                "category": entry.get("category"),
                "material_grade": entry.get("material_grade"),
            })
    return {
        "total_rows": len(rows),
        "rows": rows,
    }


class AttachMaterialRequest(BaseModel):
    material_id: int


@router.post("/{mapping_id}/attach")
def attach_material(
    mapping_id: int,
    request: AttachMaterialRequest,
    current_user: User = Depends(require_permission("create_mapping")),
):
    """Attach an approved material to an existing mapping and re-synthesize its CMR."""
    mat_index = {m["id"]: m for m in store.MATERIALS}
    mat = mat_index.get(request.material_id)
    if not mat:
        raise HTTPException(status_code=404, detail=f"Material {request.material_id} not found")

    user_email = current_user.email if current_user else "reviewer"
    try:
        updated = attach_material_to_mapping(mapping_id, mat, actor=user_email)
        return {"status": "success", "mapping": updated}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
