"""Matching routes.

Handles AI-powered material matching, including single pair comparison,
batch matching, and retrieving match suggestions.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.rbac import require_role
from app.db.postgres import get_db
from app.models.match_suggestion import MatchSuggestion
from app.schemas.match_schema import (
    BulkMatchRequest,
    MatchCompareRequest,
    MatchCompareResponse,
    MatchSuggestionListItem,
    MatchSuggestionResponse,
    MatchingStats,
    RunMatchingRequest,
    RunMatchingResponse,
)

router = APIRouter()


@router.post("/matching/run", response_model=RunMatchingResponse)
async def run_matching(
    request: RunMatchingRequest,
    current_user=Depends(require_role(["admin", "data_steward"])),
    db: Session = Depends(get_db),
) -> RunMatchingResponse:
    """Run AI matching on a set of materials.

    This triggers the matching engine to compare materials and generate
    match suggestions. The actual matching logic is handled by the
    matching engine service. For demo purposes, this creates sample
    suggestions based on the input materials.
    """
    from app.services.matching_engine.qwen_embedding import (
        EmbeddingBackend,
        get_embedding_backend,
    )
    from app.services.matching_engine.vector_search import VectorSearch
    from app.services.matching_engine.fuzzy_matcher import FuzzyMatcher
    from app.services.matching_engine.attribute_matcher import AttributeMatcher
    from app.services.matching_engine.ensemble_ranker import EnsembleRanker
    from app.services.matching_engine.explainable_ai import ExplainableAI
    from app.services.clustering.cluster_engine import ClusterEngine
    from app.services.cnmc_generator.code_generator import CNMCGenerator
    from app.services.preprocessing.text_cleaner import TextCleaner
    from app.services.preprocessing.abbreviation_expander import AbbreviationExpander
    from app.services.preprocessing.uom_normalizer import UOMNormalizer

    cleaner = TextCleaner()
    expander = AbbreviationExpander()
    uom_normalizer = UOMNormalizer()
    embedding_backend = get_embedding_backend()
    vector_search = VectorSearch()
    fuzzy_matcher = FuzzyMatcher()
    attribute_matcher = AttributeMatcher()
    ensemble_ranker = EnsembleRanker()
    explainable_ai = ExplainableAI()
    cluster_engine = ClusterEngine()
    cnmc_generator = CNMCGenerator()

    suggestions_created = 0
    high_confidence = 0
    review = 0
    different = 0

    for material in request.materials:
        cleaned_desc = cleaner.clean(material.description or material.name or "")
        expanded_desc = expander.expand(cleaned_desc)
        normalized_desc = uom_normalizer.normalize(expanded_desc)

        if embedding_backend.is_available() and vector_search.is_connected():
            query_vector = embedding_backend.encode([normalized_desc])[0]
            similar = vector_search.search(
                query_vector=query_vector,
                top_k=request.vector_top_k or 100,
            )
        else:
            similar = []

        for similar_material in similar[:request.max_suggestions or 50]:
            attrs1 = attribute_matcher.extract(normalized_desc)
            attrs2 = attribute_matcher.extract(
                cleaner.clean(similar_material.get("description", ""))
            )

            text_score = fuzzy_matcher.compare(
                normalized_desc, cleaner.clean(similar_material.get("description", ""))
            )
            semantic_score = embedding_backend.cosine_similarity(
                embedding_backend.encode([normalized_desc])[0],
                embedding_backend.encode(
                    [cleaner.clean(similar_material.get("description", ""))][0]
                )[0],
            )

            spec_score = attribute_matcher.compare_specifications(attrs1, attrs2)
            grade_score = attribute_matcher.compare_grades(attrs1, attrs2)
            other_score = attribute_matcher.compare_other_attributes(attrs1, attrs2)

            final_score = ensemble_ranker.rank(
                text_score=text_score,
                semantic_score=semantic_score,
                specification_score=spec_score,
                material_grade_score=grade_score,
                other_attributes_score=other_score,
                weights={
                    "text": request.weights.get("text", 0.20),
                    "semantic": request.weights.get("semantic", 0.20),
                    "specification": request.weights.get("specification", 0.35),
                    "material_grade": request.weights.get("material_grade", 0.15),
                    "other_attributes": request.weights.get("other_attributes", 0.10),
                },
            )

            gates_pass, gate_reasons = attribute_matcher.apply_critical_gates(
                attrs1, attrs2, material.category, similar_material.get("category", "")
            )

            if final_score >= request.high_confidence_threshold and gates_pass:
                status = "HIGH_CONFIDENCE"
                high_confidence += 1
            elif final_score >= request.different_threshold:
                status = "REVIEW"
                review += 1
            else:
                status = "DIFFERENT"
                different += 1

            explanation = explainable_ai.explain(
                material_1=material.name or "Unknown",
                material_2=similar_material.get("name", "Unknown"),
                score=final_score,
                status=status,
                attributes_1=attrs1,
                attributes_2=attrs2,
                gates_pass=gates_pass,
                gate_reasons=gate_reasons,
            )

            existing = (
                db.query(MatchSuggestion)
                .filter(
                    MatchSuggestion.material_id_1 == material.id,
                    MatchSuggestion.material_id_2 == similar_material.get("id"),
                )
                .first()
            )

            suggestion_data = {
                "material_id_1": material.id,
                "material_id_2": similar_material.get("id"),
                "score": round(final_score, 4),
                "status": status,
                "explanation": explanation,
                "attributes_1": attrs1,
                "attributes_2": attrs2,
                "text_score": round(text_score, 4),
                "semantic_score": round(semantic_score, 4),
                "specification_score": round(spec_score, 4),
                "material_grade_score": round(grade_score, 4),
                "other_attributes_score": round(other_score, 4),
                "gates_pass": gates_pass,
                "gate_reasons": gate_reasons,
                "reviewed_by": None,
                "review_status": "pending",
                "review_comment": None,
                "reviewed_at": None,
                "created_at": __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ),
                "updated_at": __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ),
            }

            if existing:
                for key, value in suggestion_data.items():
                    setattr(existing, key, value)
                suggestions_created += 0  # Updated existing
            else:
                suggestion = MatchSuggestion(**suggestion_data)
                db.add(suggestion)
                suggestions_created += 1

        if status == "HIGH_CONFIDENCE":
            cluster_engine.add_to_cluster(
                material_id=material.id,
                material_name=material.name,
                category=material.category,
            )

    db.commit()

    cnmc_codes = cnmc_generator.generate_from_clusters(cluster_engine.get_clusters())

    return RunMatchingResponse(
        status="completed",
        suggestions_created=suggestions_created,
        high_confidence=high_confidence,
        review=review,
        different=different,
        cnmc_codes_generated=len(cnmc_codes),
        message=f"Matching completed. Created {suggestions_created} suggestions.",
    )


@router.post("/matching/compare", response_model=MatchCompareResponse)
async def compare_materials(
    request: MatchCompareRequest,
    current_user=Depends(require_role(["admin", "data_steward", "reviewer"])),
    db: Session = Depends(get_db),
) -> MatchCompareResponse:
    """Compare two materials and return match analysis."""
    from app.services.matching_engine.qwen_embedding import (
        EmbeddingBackend,
        get_embedding_backend,
    )
    from app.services.matching_engine.fuzzy_matcher import FuzzyMatcher
    from app.services.matching_engine.attribute_matcher import AttributeMatcher
    from app.services.matching_engine.ensemble_ranker import EnsembleRanker
    from app.services.matching_engine.explainable_ai import ExplainableAI
    from app.services.preprocessing.text_cleaner import TextCleaner
    from app.services.preprocessing.abbreviation_expander import AbbreviationExpander
    from app.services.preprocessing.uom_normalizer import UOMNormalizer

    cleaner = TextCleaner()
    expander = AbbreviationExpander()
    uom_normalizer = UOMNormalizer()
    embedding_backend = get_embedding_backend()
    fuzzy_matcher = FuzzyMatcher()
    attribute_matcher = AttributeMatcher()
    ensemble_ranker = EnsembleRanker()
    explainable_ai = ExplainableAI()

    material1 = (
        db.query(Material).filter(Material.id == request.material_id_1).first()
        or Material(id=request.material_id_1, name=request.material_1_name)
    )
    material2 = (
        db.query(Material).filter(Material.id == request.material_id_2).first()
        or Material(id=request.material_id_2, name=request.material_2_name)
    )

    desc1 = cleaner.clean(material1.description or material1.name or "")
    desc2 = cleaner.clean(material2.description or material2.name or "")

    expanded1 = expander.expand(desc1)
    expanded2 = expander.expand(desc2)

    normalized1 = uom_normalizer.normalize(expanded1)
    normalized2 = uom_normalizer.normalize(expanded2)

    text_score = fuzzy_matcher.compare(normalized1, normalized2)

    semantic_score = 0.0
    if embedding_backend.is_available():
        vec1 = embedding_backend.encode([normalized1])[0]
        vec2 = embedding_backend.encode([normalized2])[0]
        semantic_score = embedding_backend.cosine_similarity(vec1, vec2)

    attrs1 = attribute_matcher.extract(normalized1)
    attrs2 = attribute_matcher.extract(normalized2)

    spec_score = attribute_matcher.compare_specifications(attrs1, attrs2)
    grade_score = attribute_matcher.compare_grades(attrs1, attrs2)
    other_score = attribute_matcher.compare_other_attributes(attrs1, attrs2)

    final_score = ensemble_ranker.rank(
        text_score=text_score,
        semantic_score=semantic_score,
        specification_score=spec_score,
        material_grade_score=grade_score,
        other_attributes_score=other_score,
        weights={
            "text": request.weights.get("text", 0.20),
            "semantic": request.weights.get("semantic", 0.20),
            "specification": request.weights.get("specification", 0.35),
            "material_grade": request.weights.get("material_grade", 0.15),
            "other_attributes": request.weights.get("other_attributes", 0.10),
        },
    )

    gates_pass, gate_reasons = attribute_matcher.apply_critical_gates(
        attrs1, attrs2, material1.category, material2.category
    )

    if final_score >= request.high_confidence_threshold and gates_pass:
        status = "HIGH_CONFIDENCE"
    elif final_score >= request.different_threshold:
        status = "REVIEW"
    else:
        status = "DIFFERENT"

    explanation = explainable_ai.explain(
        material_1=material1.name or "Unknown",
        material_2=material2.name or "Unknown",
        score=final_score,
        status=status,
        attributes_1=attrs1,
        attributes_2=attrs2,
        gates_pass=gates_pass,
        gate_reasons=gate_reasons,
    )

    return MatchCompareResponse(
        material_1_id=material1.id,
        material_2_id=material2.id,
        material_1_name=material1.name,
        material_2_name=material2.name,
        score=round(final_score, 4),
        status=status,
        text_score=round(text_score, 4),
        semantic_score=round(semantic_score, 4),
        specification_score=round(spec_score, 4),
        material_grade_score=round(grade_score, 4),
        other_attributes_score=round(other_score, 4),
        gates_pass=gates_pass,
        gate_reasons=gate_reasons,
        explanation=explanation,
        attributes_1=attrs1,
        attributes_2=attrs2,
    )


@router.post("/matching/bulk-match", response_model=RunMatchingResponse)
async def bulk_match(
    request: BulkMatchRequest,
    current_user=Depends(require_role(["admin", "data_steward"])),
    db: Session = Depends(get_db),
) -> RunMatchingResponse:
    """Run matching on multiple material pairs."""
    results = []
    high_confidence = 0
    review = 0
    different = 0

    for pair in request.pairs:
        result = await compare_materials(
            MatchCompareRequest(
                material_id_1=pair.material_id_1,
                material_id_2=pair.material_id_2,
                material_1_name=pair.material_1_name,
                material_2_name=pair.material_2_name,
                description_1=pair.description_1,
                description_2=pair.description_2,
                weights=request.weights,
                high_confidence_threshold=request.high_confidence_threshold,
                different_threshold=request.different_threshold,
            ),
            current_user=current_user,
            db=db,
        )
        results.append(result)

        if result.status == "HIGH_CONFIDENCE":
            high_confidence += 1
        elif result.status == "REVIEW":
            review += 1
        else:
            different += 1

    return RunMatchingResponse(
        status="completed",
        suggestions_created=len(results),
        high_confidence=high_confidence,
        review=review,
        different=different,
        cnmc_codes_generated=0,
        message=f"Bulk matching completed. Processed {len(results)} pairs.",
    )


@router.get("/matching/suggestions", response_model=list[MatchSuggestionListItem])
async def list_suggestions(
    status_filter: str | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    cpse: str | None = Query(None),
    current_user=Depends(require_role(["admin", "data_steward", "reviewer", "auditor"])),
    db: Session = Depends(get_db),
) -> list[MatchSuggestionListItem]:
    """List match suggestions with filtering."""
    query = select(MatchSuggestion).order_by(desc(MatchSuggestion.created_at))

    if status_filter:
        query = query.where(MatchSuggestion.status == status_filter)
    if cpse:
        query = query.join(Material, Material.id == MatchSuggestion.material_id_1).where(
            Material.cpse == cpse.upper()
        )

    suggestions = db.execute(query.offset(skip).limit(limit)).scalars().all()
    return [MatchSuggestionListItem.model_validate(s) for s in suggestions]


@router.get("/matching/suggestions/{suggestion_id}", response_model=MatchSuggestionResponse)
async def get_suggestion(
    suggestion_id: int,
    current_user=Depends(require_role(["admin", "data_steward", "reviewer", "auditor"])),
    db: Session = Depends(get_db),
) -> MatchSuggestionResponse:
    """Get a specific match suggestion with full details."""
    suggestion = db.query(MatchSuggestion).filter(MatchSuggestion.id == suggestion_id).first()
    if not suggestion:
        raise HTTPException(status_code=404, detail="Match suggestion not found")
    return MatchSuggestionResponse.model_validate(suggestion)


@router.get("/matching/stats", response_model=MatchingStats)
async def get_matching_stats(
    current_user=Depends(require_role(["admin", "data_steward", "reviewer", "auditor"])),
    db: Session = Depends(get_db),
) -> MatchingStats:
    """Get matching statistics."""
    total = db.query(MatchSuggestion).count()
    high_confidence = db.query(MatchSuggestion).filter(
        MatchSuggestion.status == "HIGH_CONFIDENCE"
    ).count()
    review = db.query(MatchSuggestion).filter(MatchSuggestion.status == "REVIEW").count()
    different = db.query(MatchSuggestion).filter(
        MatchSuggestion.status == "DIFFERENT"
    ).count()
    pending_review = db.query(MatchSuggestion).filter(
        MatchSuggestion.review_status == "pending"
    ).count()
    approved = db.query(MatchSuggestion).filter(
        MatchSuggestion.review_status == "approved"
    ).count()

    avg_score_high = (
        db.query(MatchSuggestion)
        .filter(MatchSuggestion.status == "HIGH_CONFIDENCE")
        .with_entities(__import__("sqlalchemy").func.avg(MatchSuggestion.score))
        .scalar()
    )

    return MatchingStats(
        total_suggestions=total,
        high_confidence=high_confidence,
        review=review,
        different=different,
        pending_review=pending_review,
        approved=approved,
        average_score_high=avg_score_high,
    )
