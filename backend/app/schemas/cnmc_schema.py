"""CNMC (Common National Material Code) & mapping schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.material_schema import MaterialResponse


class CNMCCreate(BaseModel):
    standardized_description: str = Field(min_length=3, max_length=4000)
    category: Optional[str] = None
    unspsc_code: Optional[str] = None
    nic_code: Optional[str] = None
    technical_specs: Optional[Dict[str, Any]] = None
    material_ids: List[int] = Field(
        default_factory=list,
        description="Optionally map these materials to the new CNMC immediately",
    )


class CNMCUpdate(BaseModel):
    standardized_description: Optional[str] = Field(default=None, min_length=3)
    category: Optional[str] = None
    unspsc_code: Optional[str] = None
    nic_code: Optional[str] = None
    technical_specs: Optional[Dict[str, Any]] = None


class CNMCGenerateRequest(BaseModel):
    material_ids: List[int] = Field(min_length=2, description="Cluster member material ids")
    reason: Optional[str] = None


class CNMCResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cnmc_code: str
    standardized_description: str
    category: Optional[str] = None
    unspsc_code: Optional[str] = None
    nic_code: Optional[str] = None
    technical_specs: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    mapped_materials_count: int = 0


class CNMCDetailResponse(CNMCResponse):
    mapped_materials: List[MaterialResponse] = Field(default_factory=list)


class CNMCRegistryResponse(BaseModel):
    items: List[CNMCResponse]
    total: int
    page: int
    page_size: int


class MappingCreate(BaseModel):
    material_id: int
    cnmc_id: int
    confidence_score: Optional[float] = Field(default=None, ge=0, le=100)


class MappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    material_id: int
    cnmc_id: int
    cnmc_code: Optional[str] = None
    confidence_score: Optional[float] = None
    mapping_type: Optional[str] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    status: str
    created_at: Optional[datetime] = None
    material: Optional[MaterialResponse] = None

    @classmethod
    def from_orm_object(cls, mapping) -> "MappingResponse":
        return cls(
            id=mapping.id,
            material_id=mapping.material_id,
            cnmc_id=mapping.cnmc_id,
            cnmc_code=mapping.cnmc.cnmc_code if mapping.cnmc else None,
            confidence_score=mapping.confidence_score,
            mapping_type=mapping.mapping_type,
            approved_by=mapping.approved_by,
            approved_at=mapping.approved_at,
            status=mapping.status,
            created_at=mapping.created_at,
            material=MaterialResponse.model_validate(mapping.material)
            if mapping.material
            else None,
        )


class MappingListResponse(BaseModel):
    items: List[MappingResponse]
    total: int
    page: int
    page_size: int


class MaterialMappingStatusResponse(BaseModel):
    material_id: int
    material_code: Optional[str] = None
    cpse_id: Optional[int] = None
    mapped: bool
    mapping: Optional[MappingResponse] = None
    pending_matches: int = 0


class MigrationStatusResponse(BaseModel):
    cpse_id: Optional[int] = None
    total_materials: int
    mapped_materials: int
    unmapped_materials: int
    pending_matches: int
    active_cnmc_count: int
    progress_percent: float

