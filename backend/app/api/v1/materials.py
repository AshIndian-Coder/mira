import csv
import io
from typing import Any
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.core.rbac import require_permission
from app.core.security import get_current_active_user
from app.db_adapter import materials_table, next_id
from app.models.user import User
from app.services.ingestion.provenance import resolve_provenance
from app.services.ingestion.service import parse_legacy_file
from app.services.normalization.service import normalize_material_description
from app.services.parsing.service import parse_specifications
from app import store

router = APIRouter(prefix="/materials", tags=["Materials"])


@router.post("/upload")
async def upload_materials_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(require_permission("upload_data")),
):
    """Upload material master records in legacy formats (CSV, TXT, XML, JSON, XLS, XLSX)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename must be provided")

    content = await file.read()

    try:
        raw_rows = parse_legacy_file(content, file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    start_id = next_id(materials_table)
    new_records: list[dict[str, Any]] = []
    for row in raw_rows:
        sheet_name = row.get("_sheet_name")
        prov = resolve_provenance(row, sheet_name=sheet_name, filename=file.filename)
        cpse = prov.cpse if (prov.cpse and prov.cpse != "UNKNOWN") else "CPSE_GENERIC"
        code = (
            row.get("material_code")
            or row.get("source_material_code")
            or row.get("item_code")
            or f"MAT-{uuid.uuid4().hex[:8].upper()}"
        )
        raw_desc = (row.get("description") or row.get("material_description") or "").strip()

        if not raw_desc:
            continue

        norm_desc = normalize_material_description(raw_desc)
        parsed = parse_specifications(raw_desc)

        record: dict[str, Any] = {
            "id": start_id + len(new_records),
            "cpse": cpse,
            "provenance_level": prov.level.value,
            "provenance_confidence": prov.confidence,
            "provenance_source": prov.source,
            "provenance_conflict": prov.conflict_detected,
            "requires_review": prov.requires_review,
            "provenance_details": {
                "all_evidence": prov.all_evidence,
                "conflicts": prov.conflicting_evidence,
            },
            "material_code": code,
            "description": raw_desc,
            "normalized_description": norm_desc,
            # parse_specifications returns {material_grade, pressure_rating, dimensions, voltage_class}
            "category": row.get("category") or "General",
            "unit": row.get("unit"),
            "manufacturer": row.get("manufacturer"),
            "manufacturer_part_number": row.get("manufacturer_part_number"),
            "material_grade": row.get("material_grade") or parsed.get("material_grade"),
            "parsed_specifications": {
                k: v for k, v in parsed.items() if v is not None
            },
            "other_attributes": row.get("other_attributes") or {},
        }
        new_records.append(record)

    store.MATERIALS.extend(new_records)

    return {
        "status": "success",
        "records_ingested": len(new_records),
        "total_materials": len(store.MATERIALS),
        "sample": new_records[:10],
    }


@router.get("")
def list_materials(
    query: str | None = Query(None, description="Search description or code"),
    cpse: str | None = Query(None, description="Filter by CPSE"),
    category: str | None = Query(None, description="Filter by category"),
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_active_user),
):
    """List ingested material records with optional filtering and pagination."""
    filtered = store.MATERIALS

    if cpse:
        filtered = [m for m in filtered if m["cpse"].lower() == cpse.lower()]

    if category:
        filtered = [
            m for m in filtered if (m.get("category") or "").lower() == category.lower()
        ]

    if query:
        q = query.lower()
        filtered = [
            m for m in filtered
            if q in m["description"].lower() or q in m["material_code"].lower()
        ]

    total = len(filtered)
    paginated = filtered[skip: skip + limit]

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "materials": paginated,
    }


@router.get("/stats")
def materials_stats(current_user: User = Depends(get_current_active_user)):
    """Summary counts for the dashboard / analytics panels."""
    cpse_set = {m["cpse"] for m in store.MATERIALS}
    category_counts: dict[str, int] = {}
    for m in store.MATERIALS:
        cat = m.get("category") or "Uncategorised"
        category_counts[cat] = category_counts.get(cat, 0) + 1

    return {
        "total_materials": len(store.MATERIALS),
        "cpse_count": len(cpse_set),
        "cpse_list": sorted(cpse_set),
        "category_distribution": category_counts,
    }


@router.get("/{material_id}")
def get_material(
    material_id: int,
    current_user: User = Depends(get_current_active_user),
):
    """Retrieve a single material record by ID."""
    for item in store.MATERIALS:
        if item["id"] == material_id:
            return item
    raise HTTPException(status_code=404, detail=f"Material {material_id} not found")
