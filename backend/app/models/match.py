"""SQLAlchemy ORM models for match candidates and human review decisions."""

import enum
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MatchDecisionEnum(str, enum.Enum):
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
    REVIEW = "REVIEW"
    DIFFERENT = "DIFFERENT"


class ReviewStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class MatchCandidate(Base):
    """Persisted candidate pair produced by the matching engine."""

    __tablename__ = "match_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    source_material_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("materials.id"), nullable=False, index=True
    )
    target_material_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("materials.id"), nullable=False, index=True
    )

    # Frozen hybrid score components
    text_similarity: Mapped[float] = mapped_column(Float, nullable=False)
    semantic_similarity: Mapped[float] = mapped_column(Float, nullable=False)
    specification_similarity: Mapped[float] = mapped_column(Float, nullable=False)
    material_grade_similarity: Mapped[float] = mapped_column(Float, nullable=False)
    other_attributes_similarity: Mapped[float] = mapped_column(Float, nullable=False)
    final_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)

    # Classifier output
    engine_decision: Mapped[MatchDecisionEnum] = mapped_column(
        Enum(MatchDecisionEnum), nullable=False, index=True
    )

    # Critical gate results stored as JSON list of check dicts
    critical_checks: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Human review fields
    review_status: Mapped[ReviewStatusEnum] = mapped_column(
        Enum(ReviewStatusEnum), nullable=False, default=ReviewStatusEnum.PENDING, index=True
    )
    reviewer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewer_comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    source_material = relationship("Material", foreign_keys=[source_material_id])
    target_material = relationship("Material", foreign_keys=[target_material_id])


class AuditEvent(Base):
    """Append-only audit trail for all significant decisions."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # e.g. MATCH_CREATED, MATCH_APPROVED, MATCH_REJECTED, MATERIAL_INGESTED

    match_candidate_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    material_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    actor: Mapped[str | None] = mapped_column(String(100), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
