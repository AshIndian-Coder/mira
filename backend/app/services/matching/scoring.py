from typing import Any

from app.services.matching.similarity import (
    semantic_similarity,
    specification_similarity,
    text_similarity,
    value_similarity,
)


# MIRA Production Frozen Weights
# Validated via Qwen Controlled A/B Evaluation (Arm C / CAND_0678)
# Optimization constraints: w_i >= 0, sum(w) = 1.0, w_spec >= 0.25, w_grade >= 0.10
TEXT_WEIGHT = 0.175
SEMANTIC_WEIGHT = 0.400
SPECIFICATION_WEIGHT = 0.250
GRADE_WEIGHT = 0.125
OTHER_ATTRIBUTES_WEIGHT = 0.050



def calculate_match_score(
    source: dict[str, Any],
    target: dict[str, Any],
    embedding_cache: Any = None,
) -> dict[str, float]:
    text_score = text_similarity(
        source.get("normalized_description", ""),
        target.get("normalized_description", ""),
    )

    semantic_score = semantic_similarity(
        source.get("normalized_description", ""),
        target.get("normalized_description", ""),
        embedding_cache=embedding_cache,
    )

    specification_score = specification_similarity(
        source.get("parsed_specifications"),
        target.get("parsed_specifications"),
        source.get("category"),
    )

    grade_score = value_similarity(
        source.get("material_grade"),
        target.get("material_grade"),
    )

    left_other = source.get("other_attributes")
    right_other = target.get("other_attributes")
    
    if not left_other and not right_other:
        other_score = 1.0
    else:
        other_score = specification_similarity(
            left_other,
            right_other,
        )

    final_score = (
        TEXT_WEIGHT * text_score
        + SEMANTIC_WEIGHT * semantic_score
        + SPECIFICATION_WEIGHT * specification_score
        + GRADE_WEIGHT * grade_score
        + OTHER_ATTRIBUTES_WEIGHT * other_score
    )

    return {
        "text_similarity": round(text_score, 4),
        "semantic_similarity": round(semantic_score, 4),
        "specification_similarity": round(specification_score, 4),
        "material_grade_similarity": round(grade_score, 4),
        "other_attributes_similarity": round(other_score, 4),
        "final_score": round(final_score, 4),
    }
