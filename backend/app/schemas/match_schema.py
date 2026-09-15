"""Match suggestion & review workflow schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.material_schema import MaterialResponse


class MatchRunRequest(BaseModel):
    """Trigger AI matching.

    Exactly one scope selector should be provided; with none, all active
    materials (up to ``limit``) are processed.
    """

    material_ids: Optional[List[int]] = Field(
        default=None, description="Specific material ids to match"
    )
    upload_batch_id: Optional[int] = Field(
        default=None, description="Match everything in this upload batch"
    )
    cpse_id: Optional[int] = Field(
        default=None, description="Only source materials of this CPSE"
    )
    include_same_cpse: bool = Field(
        default=False,
        description="Also compare materials within the same CPSE (default: cross-CPSE only)",
    )
    limit: int = Field(default=500, ge=1, le=5000, description="Max source materials")
    min_confidence: float = Field(
        default=0.45, ge=0.0, le=1.0, description="Persist suggestions at/above this score"
    )


class MatchRunResult(BaseModel):
    processed: int
    candidates_evaluated: int
    suggestions_created: int
    suggestions_existing: int
    by_decision: Dict[str, int] = Field(default_factory=dict)
    embedding_backend: Optional[str] = None
    vector_backend: Optional[str] = None


class SuggestionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    material_1_id: int
    material_2_id: int
    semantic_similarity: Optional[float] = None
    fuzzy_similarity: Optional[float] = None
    attribute_similarity: Optional[float] = None
    final_confidence: Optional[float] = None
    decision: str = Field(description="HIGH_CONFIDENCE | REVIEW | DIFFERENT")
    status: str
    created_at: Optional[datetime] = None
    material_1: Optional[MaterialResponse] = None
    material_2: Optional[MaterialResponse] = None

    @classmethod
    def from_orm_object(cls, suggestion) -> "SuggestionListItem":
        explanation = suggestion.explanation or {}
        return cls(
            id=suggestion.id,
            material_1_id=suggestion.material_1_id,
            material_2_id=suggestion.material_2_id,
            semantic_similarity=suggestion.semantic_similarity,
            fuzzy_similarity=suggestion.fuzzy_similarity,
            attribute_similarity=suggestion.attribute_similarity,
            final_confidence=suggestion.final_confidence,
            decision=explanation.get("decision", "REVIEW"),
            status=suggestion.status,
            created_at=suggestion.created_at,
            material_1=MaterialResponse.model_validate(suggestion.material_1)
            if suggestion.material_1
            else None,
            material_2=MaterialResponse.model_validate(suggestion.material_2)
            if suggestion.material_2
            else None,
        )


class SuggestionListResponse(BaseModel):
    items: List[SuggestionListItem]
    total: int
    page: int
    page_size: int
    counts: Dict[str, int] = Field(
        default_factory=dict, description="Pending counts by decision label"
    )


class MatchSuggestionResponse(SuggestionListItem):
    explanation: Optional[Dict[str, Any]] = None
    reviewed_by: Optional[int] = None
    reviewer_email: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_comments: Optional[str] = None

    @classmethod
    def from_orm_object(cls, suggestion) -> "MatchSuggestionResponse":
        base = SuggestionListItem.from_orm_object(suggestion).model_dump()
        return cls(
            **base,
            explanation=suggestion.explanation,
            reviewed_by=suggestion.reviewed_by,
            reviewer_email=suggestion.reviewer.email if suggestion.reviewer else None,
            reviewed_at=suggestion.reviewed_at,
            review_comments=suggestion.review_comments,
        )


class ReviewRequest(BaseModel):
    reason: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Why the reviewer approved/rejected (feeds active learning)",
    )


class BulkReviewRequest(BaseModel):
    match_ids: List[int] = Field(min_length=1, max_length=500)
    reason: Optional[str] = None


class BulkReviewResponse(BaseModel):
    approved: int
    rejected: int
    failed: int
    errors: List[Dict[str, Any]] = Field(default_factory=list)


class ReviewResponse(BaseModel):
    match_id: int
    status: str = Field(description="approved | rejected")
    cnmc_code: Optional[str] = Field(default=None, description="Set when a mapping was created")
    mapping_ids: List[int] = Field(default_factory=list)
    reason: Optional[str] = None
    message: str

