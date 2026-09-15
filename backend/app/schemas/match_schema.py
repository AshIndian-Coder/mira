"""Match suggestion & review workflow schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.material_schema import MaterialResponse


class MatchRunRequest(BaseModel):
    """
    Trigger AI matching.
    Exactly one scope selector should be provided; with none, all active
    materials (up to ``limit``) are considered.
    """
    cpse_id: Optional[int] = Field(default=None, description="Restrict to one CPSE")
    material_ids: Optional[List[int]] = Field(
        default=None, description="Explicit materials to compare (mutually exclusive with cpse_id)"
    )
    limit: int = Field(default=200, ge=1, le=2000, description="Max source materials to process")
    top_k: int = Field(default=100, ge=1, le=1000, description="Candidates per material")
    exclude_same_cpse: bool = Field(default=True, description="Skip same-CPSE pairs by default")
    min_confidence: float = Field(default=0.45, ge=0, le=1, description="Drop below-threshold pairs")


class MatchRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    processed: int
    suggestions_created: int
    by_decision: Dict[str, int] = Field(default_factory=dict)
    embedding_backend: Optional[str] = None
    vector_backend: Optional[str] = None
    message: str


class BulkMatchRequest(BaseModel):
    pairs: List[Dict[str, Any]] = Field(..., description="[{material_id_1, material_id_2}, ...]")


class BulkMatchResponse(BaseModel):
    processed: int
    suggestions_created: int
    by_decision: Dict[str, int] = Field(default_factory=dict)
    message: str


class MatchSuggestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    material_1_id: int
    material_2_id: int
    material_1: Optional[MaterialResponse] = None
    material_2: Optional[MaterialResponse] = None
    semantic_similarity: Optional[float] = None
    fuzzy_similarity: Optional[float] = None
    attribute_similarity: Optional[float] = None
    final_confidence: Optional[float] = None
    explanation: Optional[Dict[str, Any]] = None
    status: str
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    review_comments: Optional[str] = None
    created_at: Optional[datetime] = None


class MatchSuggestionListItem(BaseModel):
    id: int
    material_1_id: int
    material_2_id: int
    material_1_code: Optional[str] = None
    material_2_code: Optional[str] = None
    material_1_cpse: Optional[str] = None
    material_2_cpse: Optional[str] = None
    final_confidence: Optional[float] = None
    decision: Optional[str] = None
    status: str
    gate_status: Optional[str] = None
    created_at: Optional[datetime] = None

    @classmethod
    def from_orm_object(cls, suggestion) -> "MatchSuggestionListItem":
        explanation = suggestion.explanation or {}
        return cls(
            id=suggestion.id,
            material_1_id=suggestion.material_1_id,
            material_2_id=suggestion.material_2_id,
            material_1_code=suggestion.material_1.material_code if suggestion.material_1 else None,
            material_2_code=suggestion.material_2.material_code if suggestion.material_2 else None,
            material_1_cpse=suggestion.material_1.cpse.short_code if suggestion.material_1 and suggestion.material_1.cpse else None,
            material_2_cpse=suggestion.material_2.cpse.short_code if suggestion.material_2 and suggestion.material_2.cpse else None,
            final_confidence=float(suggestion.final_confidence) if suggestion.final_confidence is not None else None,
            decision=explanation.get("decision"),
            status=suggestion.status,
            gate_status=explanation.get("gate", {}).get("status"),
            created_at=suggestion.created_at,
        )


class SuggestionListResponse(BaseModel):
    items: List[MatchSuggestionListItem]
    total: int
    page: int
    page_size: int
    counts: Dict[str, int] = Field(default_factory=dict)


class ReviewRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500, description="Reviewer's reasoning")


class ReviewResponse(BaseModel):
    match_id: int
    status: str
    cnmc_code: Optional[str] = None
    mapping_ids: List[int] = Field(default_factory=list)
    reason: Optional[str] = None
    message: str


class BulkReviewRequest(BaseModel):
    match_ids: List[int] = Field(..., min_length=1)
    reason: Optional[str] = Field(default=None, max_length=500)


class BulkReviewResponse(BaseModel):
    approved: int
    rejected: int
    failed: int
    errors: List[Dict[str, Any]] = Field(default_factory=list)
