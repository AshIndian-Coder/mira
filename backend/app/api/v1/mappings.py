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

from app import store
from app.core.rbac import require_permission
from app.core.security import get_current_active_user
from app.db_adapter import PersistentList, mappings_table, next_id
from app.models.user import User
from app.services.clustering.service import cluster_approved_pairs
from app.services.harmonization.service import build_common_material_record

router = APIRouter(prefix="/mappings", tags=["Mappings"])

# Postgres-backed mapping store: each entry =
#   { id, nmc, cpse_mappings: [{cpse, material_code, description}], status, created_at }
MAPPINGS = PersistentList(mappings_table)


def _next_mapping_id() -> int:
    return next_id(mappings_table)


def _make_nmc(mapping_id: int) -> str:
    """
    Provisional NMC format: NMC-YYYYMM-NNNNNN
    """
    from datetime import datetime, timezone
    ym = datetime.now(timezone.utc).strftime("%Y%m")
    return f"NMC-{ym}-{mapping_id:06d}"


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
    approved = [c for c in store.CANDIDATES if c["review_status"] == "APPROVED"]

    if not approved:
        return {
            "status": "no_approved_candidates",
            "mappings_created": 0,
            "message": "Approve candidates via POST /api/review/queue/{id}/action first.",
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

        mapping_id = _next_mapping_id()
        nmc = _make_nmc(mapping_id)

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
            "nmc": nmc,
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
