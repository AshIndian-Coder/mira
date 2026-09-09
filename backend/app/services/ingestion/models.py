from dataclasses import dataclass, field
from typing import Any


@dataclass
class MaterialRecord:
    """
    Canonical representation of a material independent of source format.
    Source-specific adapters must convert their input into this structure.
    """

    cpse: str
    material_code: str
    description: str

    category: str | None = None
    unit: str | None = None
    quantity: float | None = None

    manufacturer: str | None = None
    manufacturer_part_number: str | None = None
    material_grade: str | None = None

    dimensions: dict[str, Any] | None = None
    specifications: dict[str, Any] = field(default_factory=dict)
    other_attributes: dict[str, Any] = field(default_factory=dict)

    source_file: str | None = None
    source_page: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpse": self.cpse,
            "material_code": self.material_code,
            "description": self.description,
            "category": self.category,
            "unit": self.unit,
            "quantity": self.quantity,
            "manufacturer": self.manufacturer,
            "manufacturer_part_number": self.manufacturer_part_number,
            "material_grade": self.material_grade,
            "dimensions": self.dimensions,
            "specifications": self.specifications,
            "other_attributes": self.other_attributes,
            "source_file": self.source_file,
            "source_page": self.source_page,
        }
