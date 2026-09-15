"""Material & ingestion schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class MaterialUploadRow(BaseModel):
    material_code: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=4000)
    uom: Optional[str] = None
    category: Optional[str] = None
    specifications: Optional[str] = None
    last_purchase_price: Optional[float] = None
    avg_annual_quantity: Optional[float] = None


class MaterialCreate(BaseModel):
    """Programmatic material creation (API upload without a file)."""

    model_config = ConfigDict(from_attributes=True)

    cpse_id: int
    material_code: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=4000)
    uom: Optional[str] = None
    category: Optional[str] = None
    specifications: Optional[str] = None
    last_purchase_price: Optional[float] = None
    avg_annual_quantity: Optional[float] = None


class MaterialUpdate(BaseModel):
    description: Optional[str] = None
    category: Optional[str] = None
    uom: Optional[str] = None
    specifications: Optional[str] = None
    last_purchase_price: Optional[float] = None
    avg_annual_quantity: Optional[float] = None
    status: Optional[str] = Field(default=None, pattern="^(active|obsolete|merged)$")


class MaterialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cpse_id: int
    material_code: str
    description: str
    cleaned_description: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    category: Optional[str] = None
    uom: Optional[str] = None
    uom_normalized: Optional[str] = None
    specifications: Optional[str] = None
    technical_details: Optional[Dict[str, Any]] = None
    last_purchase_price: Optional[float] = None
    avg_annual_quantity: Optional[float] = None
    data_quality_score: Optional[int] = None
    status: str
    upload_batch_id: Optional[int] = None
    created_at: Optional[datetime] = None


class MaterialListResponse(BaseModel):
    items: List[MaterialResponse]
    total: int
    page: int
    page_size: int


class UploadResultResponse(BaseModel):
    upload_id: int
    cpse_id: int
    filename: Optional[str] = None
    total_rows: int
    inserted: int
    updated: int
    skipped: int
    avg_quality_score: Optional[float] = None
    embedding_indexed: int
    errors: List[Dict[str, Any]] = Field(default_factory=list)


class UploadBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cpse_id: int
    uploaded_by: int
    uploader_email: Optional[str] = None
    filename: Optional[str] = None
    file_size_bytes: Optional[int] = None
    total_records: Optional[int] = None
    successful_records: Optional[int] = None
    failed_records: Optional[int] = None
    data_quality_score: Optional[int] = None
    uploaded_at: Optional[datetime] = None

    @classmethod
    def from_orm_object(cls, batch) -> "UploadBatchResponse":
        return cls(
            id=batch.id,
            cpse_id=batch.cpse_id,
            uploaded_by=batch.uploaded_by,
            uploader_email=batch.uploader.email if batch.uploader else None,
            filename=batch.filename,
            file_size_bytes=batch.file_size_bytes,
            total_records=batch.total_records,
            successful_records=batch.successful_records,
            failed_records=batch.failed_records,
            data_quality_score=batch.data_quality_score,
            uploaded_at=batch.uploaded_at,
        )


class UploadHistoryResponse(BaseModel):
    items: List[UploadBatchResponse]
    total: int
    page: int
    page_size: int


class QualityReportResponse(BaseModel):
    upload_id: int
    cpse_id: int
    filename: Optional[str] = None
    total_records: int
    successful_records: int
    failed_records: int
    avg_quality_score: Optional[float] = None
    score_distribution: Dict[str, int] = Field(default_factory=dict)
    missing_fields: Dict[str, int] = Field(default_factory=dict)
    category_breakdown: Dict[str, int] = Field(default_factory=dict)
