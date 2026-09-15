"""Ingestion routes.

Handles material data upload (CSV/Excel), ingestion history, quality reports,
and material listing with filtering.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import require_role
from app.db.postgres import get_db
from app.models.material import Material
from app.models.upload_batch import UploadBatch
from app.schemas.material_schema import (
    IngestionHistoryResponse,
    IngestionQualityReport,
    MaterialCreate,
    MaterialListItem,
    MaterialResponse,
    MaterialUploadResponse,
)

router = APIRouter()


@router.post("/ingestion/upload", response_model=MaterialUploadResponse)
async def upload_materials(
    file: UploadFile,
    current_user=Depends(require_role(["admin", "data_steward"])),
    db: Session = Depends(get_db),
) -> MaterialUploadResponse:
    """Upload material data from CSV or Excel file.

    Supports CSV and Excel (.xlsx, .xls) files.
    Expected columns: name, description, cpsE, category, specification,
    material_grade, dimensions, pressure_rating, voltage_class, seal_type,
    standard, unit_of_measure, supplier, min_order_quantity, price
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    filename = file.filename.lower()
    if filename.endswith(".csv"):
        import csv
        import io

        content = await file.read()
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    elif filename.endswith((".xlsx", ".xls")):
        import pandas as pd

        content = await file.read()
        df = pd.read_excel(io.BytesIO(content))
        rows = df.to_dict(orient="records")
    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format. Use CSV or Excel (.xlsx, .xls)",
        )

    if not rows:
        raise HTTPException(status_code=400, detail="No data found in file")

    batch_id = uuid.uuid4()
    batch = UploadBatch(
        id=batch_id,
        filename=file.filename,
        uploaded_by=current_user.email if current_user else "system",
        total_records=len(rows),
        status="processing",
        created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    db.add(batch)
    db.commit()

    created_materials = []
    errors = []

    for idx, row in enumerate(rows, start=1):
        try:
            material_data = {
                "name": str(row.get("name", "")).strip(),
                "description": str(row.get("description", "")).strip(),
                "cpse": str(row.get("cpse", "")).strip().upper(),
                "category": str(row.get("category", "")).strip(),
                "specification": str(row.get("specification", "")).strip(),
                "material_grade": str(row.get("material_grade", "")).strip(),
                "dimensions": str(row.get("dimensions", "")).strip(),
                "pressure_rating": str(row.get("pressure_rating", "")).strip(),
                "voltage_class": str(row.get("voltage_class", "")).strip(),
                "seal_type": str(row.get("seal_type", "")).strip(),
                "standard": str(row.get("standard", "")).strip(),
                "unit_of_measure": str(row.get("unit_of_measure", "")).strip(),
                "supplier": str(row.get("supplier", "")).strip(),
                "min_order_quantity": _parse_float(row.get("min_order_quantity")),
                "price": _parse_float(row.get("price")),
            }

            if not material_data["name"]:
                errors.append(f"Row {idx}: Name is required")
                continue

            material = Material(**material_data, uploaded_batch_id=batch_id)
            db.add(material)
            created_materials.append(material)
        except Exception as e:
            errors.append(f"Row {idx}: {str(e)}")

    db.commit()

    batch.status = "completed" if not errors else "completed_with_errors"
    db.commit()

    return MaterialUploadResponse(
        batch_id=str(batch_id),
        filename=file.filename,
        total_records=len(rows),
        created_count=len(created_materials),
        error_count=len(errors),
        errors=errors,
        status=batch.status,
    )


@router.get("/ingestion/history", response_model=list[IngestionHistoryResponse])
async def get_ingestion_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user=Depends(require_role(["admin", "data_steward", "reviewer", "auditor"])),
    db: Session = Depends(get_db),
) -> list[IngestionHistoryResponse]:
    """Get ingestion history with pagination."""
    batches = (
        db.query(UploadBatch)
        .order_by(UploadBatch.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [IngestionHistoryResponse.model_validate(b) for b in batches]


@router.get("/ingestion/quality-report/{batch_id}", response_model=IngestionQualityReport)
async def get_quality_report(
    batch_id: str,
    current_user=Depends(require_role(["admin", "data_steward", "reviewer", "auditor"])),
    db: Session = Depends(get_db),
) -> IngestionQualityReport:
    """Get quality report for a specific ingestion batch."""
    batch = db.query(UploadBatch).filter(UploadBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    materials = db.query(Material).filter(Material.uploaded_batch_id == batch_id).all()

    total = len(materials)
    with_name = sum(1 for m in materials if m.name)
    with_description = sum(1 for m in materials if m.description)
    with_category = sum(1 for m in materials if m.category)
    with_spec = sum(1 for m in materials if m.specification)

    category_counts = {}
    cpse_counts = {}
    for m in materials:
        if m.category:
            category_counts[m.category] = category_counts.get(m.category, 0) + 1
        if m.cpse:
            cpse_counts[m.cpse] = cpse_counts.get(m.cpse, 0) + 1

    return IngestionQualityReport(
        batch_id=batch_id,
        filename=batch.filename,
        total_records=total,
        complete_records=total,
        missing_name=total - with_name,
        missing_description=total - with_description,
        missing_category=total - with_category,
        missing_specification=total - with_spec,
        category_distribution=category_counts,
        cpse_distribution=cpse_counts,
        status=batch.status,
        uploaded_at=batch.created_at,
    )


@router.get("/ingestion/materials", response_model=list[MaterialListItem])
async def list_materials(
    cpse: str | None = Query(None),
    category: str | None = Query(None),
    search: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user=Depends(require_role(["admin", "data_steward", "reviewer", "auditor"])),
    db: Session = Depends(get_db),
) -> list[MaterialListItem]:
    """List materials with filtering and pagination."""
    query = select(Material)

    if cpse:
        query = query.where(Material.cpse == cpse.upper())
    if category:
        query = query.where(Material.category == category)
    if search:
        search_term = f"%{search}%"
        query = query.where(
            (Material.name.ilike(search_term))
            | (Material.description.ilike(search_term))
            | (Material.specification.ilike(search_term))
        )

    materials = db.execute(query.offset(skip).limit(limit)).scalars().all()
    return [MaterialListItem.model_validate(m) for m in materials]


def _parse_float(value: Any) -> float | None:
    """Parse a value to float, returning None if not possible."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
