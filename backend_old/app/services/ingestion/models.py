from dataclasses import dataclass, field
from typing import Any


@dataclass
class MaterialRecord:
    """
    Canonical representation of a material independent of source format.

    Adapters are responsible for extracting information from source
    documents. Unknown/uninterpreted information must not be discarded;
    it can be preserved in raw_attributes / extraction_metadata.
    """

    cpse: str
    material_code: str
    description: str

    # Canonicalized description used by downstream matching.
    normalized_description: str | None = None

    category: str | None = None
    unit: str | None = None
    quantity: float | None = None

    manufacturer: str | None = None
    manufacturer_part_number: str | None = None
    material_grade: str | None = None

    dimensions: dict[str, Any] | None = None
    specifications: dict[str, Any] = field(default_factory=dict)

    # Parsed technical specifications derived from the description.
    parsed_specifications: dict[str, Any] = field(default_factory=dict)

    other_attributes: dict[str, Any] = field(default_factory=dict)

    # Original source information.
    source_file: str | None = None
    source_page: int | None = None

    # Evidence that could not yet be safely mapped into a canonical field.
    raw_attributes: dict[str, Any] = field(default_factory=dict)

    # Metadata about how confidently the record was extracted.
    extraction_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpse": self.cpse,
            "material_code": self.material_code,
            "description": self.description,
            "normalized_description": self.normalized_description,
            "category": self.category,
            "unit": self.unit,
            "quantity": self.quantity,
            "manufacturer": self.manufacturer,
            "manufacturer_part_number": self.manufacturer_part_number,
            "material_grade": self.material_grade,
            "dimensions": self.dimensions,
            "specifications": self.specifications,
            "parsed_specifications": self.parsed_specifications,
            "other_attributes": self.other_attributes,
            "source_file": self.source_file,
            "source_page": self.source_page,
            "raw_attributes": self.raw_attributes,
            "extraction_metadata": self.extraction_metadata,
        }