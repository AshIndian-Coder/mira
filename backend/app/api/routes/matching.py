from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.matching.classifier import classify_match
from app.services.normalization.service import normalize_material_description
from app.services.parsing.service import parse_specifications


router = APIRouter(prefix="/matching", tags=["Matching"])


class MaterialInput(BaseModel):
    id: int | None = None
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
    parsed_specifications: dict[str, Any] | None = None
    other_attributes: dict[str, Any] | None = None
    normalized_description: str | None = None


class CompareRequest(BaseModel):
    source: MaterialInput
    target: MaterialInput


def prepare_material(material: MaterialInput) -> dict[str, Any]:
    data = material.model_dump()

    data["normalized_description"] = (
        data.get("normalized_description")
        or normalize_material_description(data["description"])
    )

    data["parsed_specifications"] = (
        data.get("parsed_specifications")
        or parse_specifications(data["description"])
    )

    if not data.get("dimensions"):
        data["dimensions"] = data["parsed_specifications"].get("dimensions")

    return data


@router.post("/compare")
def compare_materials(request: CompareRequest):
    source = prepare_material(request.source)
    target = prepare_material(request.target)

    result = classify_match(source, target)

    return {
        "source_material_id": source.get("id"),
        "target_material_id": target.get("id"),
        **result,
    }
