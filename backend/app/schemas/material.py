from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MaterialBase(BaseModel):
    cpse: str = Field(min_length=1)
    material_code: str = Field(min_length=1)
    description: str = Field(min_length=1)

    category: str | None = None
    unit: str | None = None

    manufacturer: str | None = None
    manufacturer_part_number: str | None = None

    material_grade: str | None = None
    dimensions: dict[str, Any] | None = None
    specifications: dict[str, Any] | None = None
    other_attributes: dict[str, Any] | None = None


class MaterialCreate(MaterialBase):
    pass


class MaterialResponse(MaterialBase):
    id: int
    normalized_description: str | None = None
    parsed_specifications: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)
