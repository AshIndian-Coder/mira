import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.core.rbac import require_permission
from app.core.security import get_current_active_user
from app.models.user import User
from app.services.normalization.service import normalize_material_description
from app.services.parsing.service import parse_specifications
from app import store

router = APIRouter(prefix="/materials", tags=["Materials"])


@router.post("/upload")
async def upload_materials_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(require_permission("upload_data")),
):
    """Upload CSV containing CPSE material master records."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV format")

    content = await file.read()
    decoded = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(decoded))

    new_records: list[dict[str, Any]] = []
    for row in reader:
        cpse = row.get("cpse") or row.get("source_org") or "CPSE_GENERIC"
        code = (
            row.get("material_code")
            or row.get("source_material_code")
            or f"MAT-{len(store.MATERIALS) + len(new_records) + 1:05d}"
        )
        raw_desc = row.get("description") or row.get("material_description") or ""

        if not raw_desc:
            continue

        norm_desc = normalize_material_description(raw_desc)
        parsed = parse_specifications(raw_desc)

        record: dict[str, Any] = {
            "id": len(store.MATERIALS) + len(new_records) + 1,
            "cpse": cpse,
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
            "other_attributes": {},
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
