from enum import Enum
from typing import Any

from pydantic import BaseModel


class MatchDecision(str, Enum):
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
    REVIEW = "REVIEW"
    DIFFERENT = "DIFFERENT"


class MatchScores(BaseModel):
    text_similarity: float
    semantic_similarity: float
    specification_similarity: float
    material_grade_similarity: float
    other_attributes_similarity: float
    final_score: float


class CriticalCheck(BaseModel):
    field: str
    status: str
    source_value: Any | None = None
    target_value: Any | None = None
    reason: str | None = None


class MatchResponse(BaseModel):
    source_material_id: int
    target_material_id: int

    scores: MatchScores
    critical_checks: list[CriticalCheck]

    decision: MatchDecision
