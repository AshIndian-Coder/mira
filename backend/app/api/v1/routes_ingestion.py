"""Data ingestion endpoints (CSV/Excel upload + material listing).

    POST /api/v1/ingestion/upload                Upload CSV/Excel material data
    GET  /api/v1/ingestion/history               Upload history
    GET  /api/v1/ingestion/quality-report/{id}   ISO 8000 style quality report
    GET  /api/v1/ingestion/materials             Paginated material listing
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.core.rbac import require_permission
from app.core.security import get_current_active_user
from app.db.postgres import get_db
from app.models.cpse import Cpse
from app.models.material import Material
from app.models.user import User
from app.models.upload_batch import UploadBatch
from app.schemas.material_schema import (
    MaterialListResponse,
    MaterialResponse,
    QualityReportResponse,
    UploadBatchResponse,
    UploadHistoryResponse,
    UploadResultResponse,
)
from app.services.audit.audit_service import log_action
from app.services.matching_engine.vector_search import get_vector_search_service
from app.services.preprocessing import (
    expand_abbreviations,
    normalize_uom,
    preprocess_description,
)
from app.services.ner_extraction import extract_attributes
from app.utils.constants import AUDIT_UPLOAD_DATA, MATERIAL_STATUS_ACTIVE
from app.utils.helpers import group_count, pick_field, to_float, to_decimal, utcnow

router = APIRouter(prefix="/ingestion", tags=["ingestion"])

# Accepted column aliases per field (ERP files are inconsistent).
FIELD_ALIASES = {
    "material_code": [
        "material_code", "material code", "code", "mat_code", "mat code",
        "material number", "material number ", "sap_material_code", "sap material code",
        "item_code", "item code", "item number", "materialno",
    ],
    "description": [
        "description", "desc", "material_description", "material description",
        "long_text", "long text", "long description", "text", "material desc",
    ],
    "uom": ["uom", "unit", "unit_of_measure", "uom_description", "uom description", "units", "basic unit"],
    "category": ["category", "material_group", "material group", "class", "group", "material type"],
    "specifications": ["specifications", "spec", "specification", "technical_details", "technical details", "specs"],
    "last_purchase_price": [
        "last_purchase_price", "last purchase price", "price", "unit_price",
        "unit price", "rate", "purchase_price", "purchase price", "basic price",
    ],
    "avg_annual_quantity": [
        "avg_annual_quantity", "avg annual quantity", "annual_quantity",
        "annual quantity", "quantity", "annual_qty", "annual qty", "demand", "annual_demand",
    ],
}

REQUIRED_FIELDS = ["material_code", "description"]


def _resolve_row(row: dict) -> dict:
    """Map a raw file row onto the canonical field names."""
    return {field: pick_field(row, aliases) for field, aliases in FIELD_ALIASES.items()}


def _score_row(row: dict) -> int:
    """ISO 8000 style row quality score (0-100).

    Completeness (50) + validity (30) + category sanity (20).
    """
    score = 0
    for field in REQUIRED_FIELDS:
        if row.get(field):
            score += 25
    if row.get("uom"):
        score += 10
    if row.get("category"):
        score += 10
    price = to_float(row.get("last_purchase_price"))
    if price > 0:
        score += 10
    quantity = to_float(row.get("avg_annual_quantity"))
    if quantity > 0:
        score += 10
    code_len = len(str(row.get("material_code") or ""))
    if 2 <= code_len <= 100:
        score += 5
    desc_len = len(str(row.get("description") or ""))
    if 5 <= desc_len <= 1000:
        score += 5
    return min(100, score)


def _build_material(
    row: dict,
    cpse_id: int,
    batch_id: int,
) -> tuple:
    """Preprocess one validated row into a Material row + attrs + quality."""
    description = str(row["description"]).strip()
    code = str(row["material_code"]).strip()
    cleaned = preprocess_description(description)
    attrs = extract_attributes(cleaned, category_hint=str(row.get("category") or "").strip() or None)
    if not attrs.get("category") and row.get("category"):
        attrs["category"] = str(row["category"]).strip().title()
    uom_raw = str(row.get("uom") or "").strip() or None
    return Material(
        cpse_id=cpse_id,
        material_code=code[:100],
        description=description[:4000],
        cleaned_description=cleaned,
        attributes=attrs,
        category=(attrs.get("category") or (str(row["category"]).strip().title() if row.get("category") else None))[:100],
        uom=uom_raw[:20] if uom_raw else None,
        uom_normalized=normalize_uom(uom_raw),
        specifications=(str(row["specifications"])[:4000] if row.get("specifications") else None),
        last_purchase_price=to_decimal(row.get("last_purchase_price")),
        avg_annual_quantity=to_decimal(row.get("avg_annual_quantity")),
        data_quality_score=_score_row(row),
        status=MATERIAL_STATUS_ACTIVE,
        upload_batch_id=batch_id,
    )


@router.post("/upload", response_model=UploadResultResponse)
def upload_materials(
    file: UploadFile = File(...),
    cpse_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("upload_data")),
):
    """Upload a CSV/Excel file of materials for a CPSE.

    Pipeline per row: validate -> clean -> expand abbreviations ->
    normalize UOM -> extract attributes -> quality score -> persist ->
    index embedding.
    """
    cpse = db.query(Cpse).filter(Cpse.id == cpse_id, Cpse.is_active == True).first()  # noqa: E712
    if cpse is None:
        raise HTTPException(status_code=404, detail=f"CPSE {cpse_id} not found or inactive")

    filename = file.filename or "upload"
    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    lower_name = filename.lower()
    try:
        if lower_name.endswith((".xlsx", ".xls")):
            from app.utils.helpers import load_excel_rows

            raw_rows = load_excel_rows(content)
        elif lower_name.endswith(".csv"):
            from app.utils.helpers import load_csv_rows

            raw_rows = load_csv_rows(content)
        else:
            raise HTTPException(
                status_code=400, detail="Unsupported file type (use .csv, .xlsx or .xls)"
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse file: {exc}")

    if not raw_rows:
        raise HTTPException(status_code=400, detail="File contains no data rows")

    # --- validate + preprocess rows ---
    valid: List[tuple] = []
    errors: List[dict] = []
    for index, raw in enumerate(raw_rows, start=2):  # header is row 1
        row = _resolve_row(raw)
        missing = [f for f in REQUIRED_FIELDS if not row.get(f)]
        if missing:
            errors.append({"row": index, "error": f"missing required fields: {', '.join(missing)}"})
            continue
        valid.append(row)

    # --- persist batch ---
    batch = UploadBatch(
        cpse_id=cpse_id,
        uploaded_by=user.id,
        filename=filename[:255],
        file_size_bytes=len(content),
        total_records=len(raw_rows),
        successful_records=len(valid),
        failed_records=len(raw_rows) - len(valid),
        uploaded_at=utcnow(),
    )
    db.add(batch)
    db.flush()

    inserted, updated = 0, 0
    quality_scores: List[int] = []
    embedding_rows: List[dict] = []

    for row in valid:
        material = _build_material(row, cpse_id, batch.id)
        existing = (
            db.query(Material)
            .filter(
                Material.cpse_id == cpse_id,
                Material.material_code == material.material_code,
            )
            .first()
        )
        if existing:
            for field in (
                "description", "cleaned_description", "attributes", "category",
                "uom", "uom_normalized", "specifications", "last_purchase_price",
                "avg_annual_quantity", "data_quality_score", "upload_batch_id",
            ):
                setattr(existing, field, getattr(material, field))
            existing.status = MATERIAL_STATUS_ACTIVE
            existing.updated_at = utcnow()
            material = existing
            updated += 1
        else:
            db.add(material)
            inserted += 1
        quality_scores.append(material.data_quality_score or 0)
        db.flush()
        embedding_rows.append(
            {
                "id": int(material.id),
                "cpse_id": material.cpse_id,
                "category": material.category or "",
                "cleaned_description": material.cleaned_description,
            }
        )

    batch.successful_records = inserted + updated
    batch.failed_records = len(raw_rows) - (inserted + updated)
    batch.data_quality_score = (
        round(sum(quality_scores) / len(quality_scores)) if quality_scores else None
    )
    batch.quality_report = _quality_breakdown(valid, errors)
    db.commit()

    # --- index embeddings (post-commit; safe to fail) ---
    indexed = 0
    try:
        indexed = get_vector_search_service().index_materials(embedding_rows)
    except Exception:
        pass  # embeddings can be rebuilt lazily during matching

    log_action(
        db,
        user,
        AUDIT_UPLOAD_DATA,
        entity_type="upload_batch",
        entity_id=batch.id,
        changes={
            "cpse_id": cpse_id,
            "filename": filename,
            "inserted": inserted,
            "updated": updated,
            "failed": len(raw_rows) - (inserted + updated),
        },
        commit=True,
    )

    return UploadResultResponse(
        upload_id=batch.id,
        cpse_id=cpse_id,
        filename=filename,
        total_rows=len(raw_rows),
        inserted=inserted,
        updated=updated,
        skipped=len(raw_rows) - (inserted + updated),
        avg_quality_score=batch.data_quality_score,
        embedding_indexed=indexed,
        errors=errors[:20],
    )


def _quality_breakdown(valid_rows: List[dict], errors: List[dict]) -> dict:
    missing_fields = group_count(
        [f for row in valid_rows for f in REQUIRED_FIELDS if not row.get(f)]
    )
    scores = [_score_row(row) for row in valid_rows]
    distribution = {"0-39": 0, "40-69": 0, "70-89": 0, "90-100": 0}
    for score in scores:
        if score < 40:
            distribution["0-39"] += 1
        elif score < 70:
            distribution["40-69"] += 1
        elif score < 90:
            distribution["70-89"] += 1
        else:
            distribution["90-100"] += 1
    categories = group_count(
        [str(row["category"]).strip().title() for row in valid_rows if row.get("category")]
    )
    return {
        "missing_required_fields": missing_fields,
        "score_distribution": distribution,
        "category_breakdown": categories,
        "parse_errors": len(errors),
    }


@router.get("/history", response_model=UploadHistoryResponse)
def upload_history(
    cpse_id: Optional[int] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Upload batch history (optional CPSE filter)."""
    query = db.query(UploadBatch)
    if cpse_id:
        query = query.filter(UploadBatch.cpse_id == cpse_id)
    total = query.count()
    items = (
        query.order_by(desc(UploadBatch.uploaded_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return UploadHistoryResponse(
        items=[UploadBatchResponse.from_orm_object(b) for b in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/quality-report/{upload_id}", response_model=QualityReportResponse)
def quality_report(
    upload_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """ISO 8000 style quality breakdown for one upload batch."""
    batch = db.query(UploadBatch).filter(UploadBatch.id == upload_id).first()
    if batch is None:
        raise HTTPException(status_code=404, detail="Upload batch not found")
    report = batch.quality_report or {}
    return QualityReportResponse(
        upload_id=batch.id,
        cpse_id=batch.cpse_id,
        filename=batch.filename,
        total_records=batch.total_records or 0,
        successful_records=batch.successful_records or 0,
        failed_records=batch.failed_records or 0,
        avg_quality_score=float(batch.data_quality_score) if batch.data_quality_score else None,
        score_distribution=report.get("score_distribution", {}),
        missing_fields=report.get("missing_required_fields", {}),
        category_breakdown=report.get("category_breakdown", {}),
    )


@router.get("/materials", response_model=MaterialListResponse)
def list_materials(
    cpse_id: Optional[int] = Query(default=None, description="Filter by CPSE"),
    category: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default="active"),
    search: Optional[str] = Query(default=None, description="Substring match on description/code"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Paginated material listing (MaterialTable page)."""
    query = db.query(Material)
    if cpse_id:
        query = query.filter(Material.cpse_id == cpse_id)
    if category:
        query = query.filter(Material.category == category)
    if status:
        query = query.filter(Material.status == status)
    if search:
        like = f"%{search.strip()}%"
        query = query.filter(
            (Material.description.ilike(like)) | (Material.material_code.ilike(like))
        )
    total = query.count()
    items = (
        query.order_by(desc(Material.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return MaterialListResponse(
        items=[MaterialResponse.model_validate(m) for m in items],
        total=total,
        page=page,
        page_size=page_size,
    )

