"""Material <-> CNMC mapping (CPSE code -> Common National Material Code)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.postgres import Base, bigserial_pk
from app.utils.helpers import utcnow


class Mapping(Base):
    __tablename__ = "mappings"
    __table_args__ = (
        # One active mapping per material (UNIQUE(material_id, status) in schema).
        UniqueConstraint("material_id", "status", name="uq_mappings_material_status"),
        Index("idx_mappings_cnmc", "cnmc_id"),
        Index("idx_mappings_status", "status"),
    )

    id = Column(bigserial_pk(), primary_key=True)
    material_id = Column(BigInteger, ForeignKey("materials.id", ondelete="CASCADE"), nullable=False)
    cnmc_id = Column(Integer, ForeignKey("cnmc.id", ondelete="CASCADE"), nullable=False)

    confidence_score = Column(Numeric(5, 2))  # 0.00 - 100.00
    mapping_type = Column(String(50), default="ai_suggested")  # ai_suggested | manual | auto_approved
    approved_by = Column(Integer, ForeignKey("users.id"))
    approved_at = Column(DateTime)
    status = Column(String(50), default="active", nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    # Relationships
    material = relationship("Material", back_populates="mappings", foreign_keys=[material_id])
    cnmc = relationship("CNMC", back_populates="mappings")
    approver = relationship("User", foreign_keys=[approved_by])

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Mapping material={self.material_id} cnmc={self.cnmc_id} {self.status}>"

