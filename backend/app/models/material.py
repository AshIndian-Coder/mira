"""SQLAlchemy ORM model for CPSE material master records."""

from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Source provenance — never overwritten
    cpse: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    material_code: Mapped[str] = mapped_column(String(200), nullable=False, index=True)

    # Raw description as supplied by the CPSE
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Normalization + parsing outputs
    normalized_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)

    # Technical attributes
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    manufacturer_part_number: Mapped[str | None] = mapped_column(String(200), nullable=True)
    material_grade: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Structured JSON blobs
    dimensions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    specifications: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    parsed_specifications: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    other_attributes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
