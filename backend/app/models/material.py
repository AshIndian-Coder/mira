"""Raw material records from CPSEs (the main data source for matching)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.db.postgres import Base, bigserial_pk
from app.utils.helpers import utcnow


class Material(Base):
    __tablename__ = "materials"
    __table_args__ = (
        UniqueConstraint("cpse_id", "material_code", name="uq_materials_cpse_code"),
        Index("idx_materials_cpse", "cpse_id"),
        Index("idx_materials_category", "category"),
        Index("idx_materials_status", "status"),
    )

    id = Column(bigserial_pk(), primary_key=True)
    cpse_id = Column(Integer, ForeignKey("cpses.id", ondelete="CASCADE"), nullable=False)

    material_code = Column(String(100), nullable=False)  # CPSE's internal code
    description = Column(Text, nullable=False)  # original: "BRG BALL 6205 2RS"
    cleaned_description = Column(Text)  # after text_cleaner + abbreviation_expander

    # NER-extracted attributes: {"type": "Bearing", "subtype": "Ball",
    #                            "size": "6205", "seal": "2RS", ...}
    # Production: JSONB on PostgreSQL, JSON on SQLite/dev.
    attributes = Column(JSON().with_variant(JSONB, "postgresql"), default=dict)

    category = Column(String(100))  # "Bearing", "Valve", "Pipe", ...
    uom = Column(String(20))  # as uploaded
    uom_normalized = Column(String(20))  # canonical: "NOS", "KG", "MTR", ...

    specifications = Column(Text)  # free-text technical specification
    technical_details = Column(JSON().with_variant(JSONB, "postgresql"), default=dict)  # parsed structured specs

    # Procurement data (needed for ROI calculation)
    last_purchase_price = Column(Numeric(15, 2))
    avg_annual_quantity = Column(Numeric(15, 3))

    # Quality & lifecycle
    data_quality_score = Column(Integer)  # ISO 8000 style score 0-100
    status = Column(String(50), default="active", nullable=False)
    upload_batch_id = Column(Integer, ForeignKey("upload_batches.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    cpse = relationship("Cpse", back_populates="materials")
    upload_batch = relationship("UploadBatch", back_populates="materials")
    mappings = relationship("Mapping", back_populates="material", foreign_keys="Mapping.material_id")

    @property
    def attrs(self) -> Dict[str, Any]:
        """Attributes as a plain dict (None-safe)."""
        return dict(self.attributes or {})

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Material {self.material_code} ({self.cpse_id})>"

