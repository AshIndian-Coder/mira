"""
Matching routes.

POST /api/matching/compare       - single pair comparison
POST /api/matching/run-batch     - block, retrieve, score, and classify
GET  /api/matching/candidates    - list generated candidates
GET  /api/matching/candidates/{id} - candidate detail
GET  /api/matching/stats         - matching statistics
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app import store
from app.core.rbac import require_permission
from app.core.security import get_current_active_user
from app.models.user import User
from app.services.blocking.service import (
    MaterialForBlocking,
    generate_block_keys,
    generate_candidates as blocking_generate_candidates,
)
from app.services.matching.classifier import classify_match
from app.services.matching.cnmc_matcher import (
    compute_cnmc_candidate_margin,
    find_cnmc_candidates_for_material,
    match_new_materials_against_cnmcs,
)
from app.services.matching.embeddings import precompute_embeddings
from app.services.matching.hybrid_retrieval import retrieve_candidates
from app.services.normalization.service import normalize_material_description
from app.services.parsing.service import parse_specifications


router = APIRouter(prefix="/matching", tags=["Matching"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


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


class BatchRunRequest(BaseModel):
    max_candidates_per_material: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum blocking candidates per source material.",
    )
    overwrite: bool = Field(
        default=False,
        description="Clear existing candidates before running.",
    )
    source_cpse: str | None = Field(
        default=None,
        description="Only process source materials from this CPSE.",
    )
    target_cpse: str | None = Field(
        default=None,
        description="Only match against target materials from this CPSE.",
    )


class CnmcMatchRequest(BaseModel):
    material: MaterialInput
    max_candidates: int = Field(default=10, ge=1, le=50)
    min_score: float = Field(default=0.50, ge=0.0, le=1.0)


class CnmcBatchRunRequest(BaseModel):
    max_candidates_per_material: int = Field(default=5, ge=1, le=50)
    min_score: float = Field(default=0.65, ge=0.0, le=1.0)
    create_review_candidates: bool = Field(default=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prepare_material(material: MaterialInput) -> dict[str, Any]:
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


def _store_material_to_blocker(
    material: dict[str, Any],
) -> MaterialForBlocking:
    return MaterialForBlocking(
        id=material["id"],
        category=material.get("category"),
        normalized_description=(
            material.get("normalized_description")
            or material["description"]
        ),
        material_grade=material.get("material_grade"),
        manufacturer_part_number=material.get(
            "manufacturer_part_number"
        ),
    )


def _pair_key(a: int, b: int) -> tuple[int, int]:
    """Create a canonical unordered pair key."""
    return min(a, b), max(a, b)


def _build_candidate(
    source_material: dict[str, Any],
    target_material: dict[str, Any],
    result: dict[str, Any],
    started_at: datetime,
) -> dict[str, Any]:
    """
    Build a candidate recommendation.

    Important:
    HIGH_CONFIDENCE is still PENDING. The matching engine recommends,
    but a human reviewer must approve or reject every recommendation.
    DIFFERENT candidates are excluded from the human approval queue.
    """
    engine_decision = result["decision"]

    review_status = (
        "PENDING"
        if engine_decision in ("HIGH_CONFIDENCE", "REVIEW")
        else "DIFFERENT"
    )

    scores = result.get("scores", {})

    return {
        "id": store.next_candidate_id(),
        "source_material_id": source_material["id"],
        "target_material_id": target_material["id"],
        "source_cpse": source_material["cpse"],
        "target_cpse": target_material["cpse"],
        "source_code": source_material["material_code"],
        "target_code": target_material["material_code"],
        "source_description": source_material["description"],
        "target_description": target_material["description"],
        "scores": scores,
        "text_similarity": scores.get("text_similarity", 0.0),
        "semantic_similarity": scores.get("semantic_similarity", 0.0),
        "specification_similarity": scores.get(
            "specification_similarity",
            0.0,
        ),
        "material_grade_similarity": scores.get(
            "material_grade_similarity",
            0.0,
        ),
        "other_attributes_similarity": scores.get(
            "other_attributes_similarity",
            0.0,
        ),
        "final_score": scores.get("final_score", 0.0),
        "critical_checks": result.get("critical_checks", {}),
        "engine_decision": engine_decision,
        "review_status": review_status,
        "reviewer_id": None,
        "reviewer_comments": None,
        "reviewed_at": None,
        "created_at": started_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/compare")
def compare_materials(
    request: CompareRequest,
    current_user: User = Depends(get_current_active_user),
):
    """Score and classify one material pair."""
    source = _prepare_material(request.source)
    target = _prepare_material(request.target)

    result = classify_match(source, target)

    return {
        "source_material_id": source.get("id"),
        "target_material_id": target.get("id"),
        **result,
    }


@router.post("/run-batch")
def run_batch_matching(
    request: BatchRunRequest,
    current_user: User = Depends(require_permission("run_matching")),
):
    """
    Run dataset-level material matching.

    Workflow:

    1. Normalize and prepare ingested materials.
    2. Generate blocking candidates.
    3. Retrieve additional candidates using fast MiniLM retrieval.
    4. Score candidates using MIRA.ai and technical checks.
    5. Store HIGH_CONFIDENCE and REVIEW candidates as PENDING.
    6. Store DIFFERENT candidates outside the approval queue.

    MiniLM is used only for fast candidate retrieval.
    MIRA.ai remains responsible for final semantic scoring and
    technical validation through classify_match().
    """
    if not store.MATERIALS:
        raise HTTPException(
            status_code=400,
            detail=(
                "No materials ingested. Upload a CSV via "
                "POST /api/materials/upload first."
            ),
        )

    if request.overwrite:
        store.CANDIDATES.clear()

    started_at = datetime.now(timezone.utc)

    blocker_objects = [
        _store_material_to_blocker(material)
        for material in store.MATERIALS
    ]

    material_index: dict[int, dict[str, Any]] = {
        material["id"]: material
        for material in store.MATERIALS
    }

    material_cpse: dict[int, str] = {
        material["id"]: (
            material.get("cpse") or "CPSE_GENERIC"
        ).strip().upper()
        for material in store.MATERIALS
    }

    filtered_sources = blocker_objects

    if request.source_cpse:
        requested_source_cpse = request.source_cpse.strip().upper()
        filtered_sources = [
            blocker
            for blocker in blocker_objects
            if material_cpse.get(blocker.id) == requested_source_cpse
        ]

    # Build the blocking index.
    block_index: dict[str, list[int]] = {}
    material_block_keys: dict[int, set[str]] = {}
    target_order: dict[int, int] = {}

    for index, blocker in enumerate(blocker_objects):
        target_order[blocker.id] = index

        keys = generate_block_keys(blocker)
        material_block_keys[blocker.id] = keys

        for key in keys:
            block_index.setdefault(key, []).append(blocker.id)

    # Existing pairs are not regenerated.
    seen_pairs: set[tuple[int, int]] = {
        _pair_key(
            candidate["source_material_id"],
            candidate["target_material_id"],
        )
        for candidate in store.CANDIDATES
    }

    # Partition materials by CPSE so matching remains cross-CPSE.
    cpse_blockers: dict[
        str,
        dict[int, MaterialForBlocking],
    ] = {}

    for blocker in blocker_objects:
        cpse = material_cpse.get(blocker.id, "CPSE_GENERIC")
        cpse_blockers.setdefault(cpse, {})[blocker.id] = blocker

    target_map_by_source_cpse: dict[
        str,
        dict[int, MaterialForBlocking],
    ] = {}

    for source_cpse in cpse_blockers:
        target_map: dict[int, MaterialForBlocking] = {}

        for target_cpse, target_blockers in cpse_blockers.items():
            if target_cpse == source_cpse:
                continue

            if (
                request.target_cpse
                and target_cpse != request.target_cpse.strip().upper()
            ):
                continue

            target_map.update(target_blockers)

        target_map_by_source_cpse[source_cpse] = target_map

    all_descriptions = [
        material.get("normalized_description")
        or material.get("description")
        or ""
        for material in store.MATERIALS
    ]

    embedding_cache = precompute_embeddings(
        all_descriptions,
        batch_size=64,
    )

    new_candidates: list[dict[str, Any]] = []
    total_pairs_evaluated = 0

    # ---------------------------------------------------------------
    # Rule-based blocking candidates
    # ---------------------------------------------------------------

    for source_blocker in filtered_sources:
        source_keys = material_block_keys[source_blocker.id]
        source_cpse = material_cpse.get(
            source_blocker.id,
            "CPSE_GENERIC",
        )

        cross_target_map = target_map_by_source_cpse.get(source_cpse)

        if not cross_target_map:
            continue

        raw_candidates = blocking_generate_candidates(
            source_blocker,
            block_index=block_index,
            target_map=cross_target_map,
            target_order=target_order,
            source_keys=source_keys,
        )

        raw_candidates = raw_candidates[
            : request.max_candidates_per_material
        ]

        for target_blocker in raw_candidates:
            pair_key = _pair_key(
                source_blocker.id,
                target_blocker.id,
            )

            if pair_key in seen_pairs:
                continue

            seen_pairs.add(pair_key)
            total_pairs_evaluated += 1

            source_material = material_index[source_blocker.id]
            target_material = material_index[target_blocker.id]

            result = classify_match(
                source_material,
                target_material,
                embedding_cache=embedding_cache,
            )

            new_candidates.append(
                _build_candidate(
                    source_material=source_material,
                    target_material=target_material,
                    result=result,
                    started_at=started_at,
                )
            )

    # ---------------------------------------------------------------
    # Fast MiniLM candidate retrieval
    # ---------------------------------------------------------------
    #
    # MiniLM is used only to retrieve and rank likely candidates.
    # It is not the final matching model.
    #
    # MIRA.ai performs final semantic scoring and technical validation
    # through classify_match().
    #
    # MiniLM vectors remain in memory and are not sent to the
    # 1024-dimensional Milvus collection.
    # ---------------------------------------------------------------

    for source_blocker in filtered_sources:
        source_material = material_index[source_blocker.id]
        source_cpse = material_cpse.get(
            source_blocker.id,
            "CPSE_GENERIC",
        )

        target_materials = [
            material
            for material in store.MATERIALS
            if (
                material["id"] != source_blocker.id
                and material_cpse.get(material["id"])
                != source_cpse
            )
        ]

        ranked_targets = retrieve_candidates(
            source=source_material,
            targets=target_materials,
            embedding_cache=embedding_cache,
            top_k=10,
        )

        for target_material in ranked_targets:
            pair_key = _pair_key(
                source_blocker.id,
                target_material["id"],
            )

            if pair_key in seen_pairs:
                continue

            seen_pairs.add(pair_key)
            total_pairs_evaluated += 1

            result = classify_match(
                source_material,
                target_material,
                embedding_cache=embedding_cache,
            )

            new_candidates.append(
                _build_candidate(
                    source_material=source_material,
                    target_material=target_material,
                    result=result,
                    started_at=started_at,
                )
            )

    store.CANDIDATES.extend(new_candidates)

    finished_at = datetime.now(timezone.utc)
    elapsed_ms = int(
        (finished_at - started_at).total_seconds() * 1000
    )

    decision_counts: dict[str, int] = {}

    for candidate in new_candidates:
        decision = candidate["engine_decision"]
        decision_counts[decision] = (
            decision_counts.get(decision, 0) + 1
        )

    return {
        "status": "complete",
        "materials_processed": len(store.MATERIALS),
        "candidate_pairs_evaluated": total_pairs_evaluated,
        "new_candidates_stored": len(new_candidates),
        "total_candidates": len(store.CANDIDATES),
        "decision_breakdown": decision_counts,
        "elapsed_ms": elapsed_ms,
    }


@router.get("/candidates")
def list_candidates(
    decision: str | None = Query(
        None,
        description=(
            "Filter by engine_decision: "
            "HIGH_CONFIDENCE | REVIEW | DIFFERENT"
        ),
    ),
    review_status: str | None = Query(
        None,
        description=(
            "Filter by review_status: "
            "PENDING | APPROVED | REJECTED"
        ),
    ),
    cpse: str | None = Query(
        None,
        description="Filter pairs involving this CPSE.",
    ),
    min_score: float | None = Query(
        None,
        ge=0.0,
        le=1.0,
        description="Minimum final score.",
    ),
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_active_user),
):
    """List generated candidate pairs with optional filters."""
    filtered = store.CANDIDATES

    if decision:
        filtered = [
            candidate
            for candidate in filtered
            if candidate["engine_decision"] == decision.upper()
        ]

    if review_status:
        filtered = [
            candidate
            for candidate in filtered
            if candidate["review_status"] == review_status.upper()
        ]

    if cpse:
        cpse_upper = cpse.upper()

        filtered = [
            candidate
            for candidate in filtered
            if (
                candidate["source_cpse"].upper() == cpse_upper
                or candidate["target_cpse"].upper() == cpse_upper
            )
        ]

    if min_score is not None:
        filtered = [
            candidate
            for candidate in filtered
            if candidate["scores"].get("final_score", 0.0)
            >= min_score
        ]

    total = len(filtered)
    paginated = filtered[skip : skip + limit]

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "candidates": paginated,
    }


@router.get("/candidates/{candidate_id}")
def get_candidate(
    candidate_id: int,
    current_user: User = Depends(get_current_active_user),
):
    """Retrieve one candidate by ID."""
    for candidate in store.CANDIDATES:
        if candidate["id"] == candidate_id:
            return candidate

    raise HTTPException(
        status_code=404,
        detail=f"Candidate {candidate_id} not found",
    )


@router.get("/stats")
def matching_stats(
    current_user: User = Depends(get_current_active_user),
):
    """Return matching summary statistics."""
    if not store.CANDIDATES:
        return {
            "total_candidates": 0,
            "message": (
                "No candidates yet. Run "
                "POST /api/matching/run-batch first."
            ),
        }

    total = len(store.CANDIDATES)
    decision_counts: dict[str, int] = {}
    review_status_counts: dict[str, int] = {}
    scores: list[float] = []

    for candidate in store.CANDIDATES:
        decision = candidate["engine_decision"]
        decision_counts[decision] = (
            decision_counts.get(decision, 0) + 1
        )

        review_status = candidate["review_status"]
        review_status_counts[review_status] = (
            review_status_counts.get(review_status, 0) + 1
        )

        scores.append(
            candidate["scores"].get("final_score", 0.0)
        )

    scores.sort()
    count = len(scores)

    p50 = scores[count // 2] if count else 0.0
    p90 = scores[int(count * 0.90)] if count else 0.0
    p95 = scores[int(count * 0.95)] if count else 0.0

    material_count = len(store.MATERIALS)
    theoretical_max = material_count * (material_count - 1) // 2

    blocking_reduction = (
        round(1.0 - total / theoretical_max, 4)
        if theoretical_max > 0
        else None
    )

    reviewable_count = (
        decision_counts.get("HIGH_CONFIDENCE", 0)
        + decision_counts.get("REVIEW", 0)
    )

    high_confidence_recommendation_rate = (
        round(
            decision_counts.get("HIGH_CONFIDENCE", 0)
            / reviewable_count,
            4,
        )
        if reviewable_count > 0
        else None
    )

    return {
        "total_candidates": total,
        "decision_breakdown": decision_counts,
        "review_status_breakdown": review_status_counts,
        "high_confidence_recommendation_rate": (
            high_confidence_recommendation_rate
        ),
        "blocking_reduction_ratio": blocking_reduction,
        "score_percentiles": {
            "p50": round(p50, 4),
            "p90": round(p90, 4),
            "p95": round(p95, 4),
        },
    }


@router.post("/cnmc/candidates")
def find_cnmc_proposals(
    request: CnmcMatchRequest,
    current_user: User = Depends(get_current_active_user),
):
    """Find and rank existing CNMC proposals for one material."""
    prepared = _prepare_material(request.material)

    proposals = find_cnmc_candidates_for_material(
        prepared,
        max_candidates=request.max_candidates,
        min_score=request.min_score,
    )

    margin_info = compute_cnmc_candidate_margin(proposals)

    return {
        "material": prepared,
        "total_candidates": len(proposals),
        "best_score": margin_info["best_score"],
        "second_best_score": margin_info["second_best_score"],
        "score_margin": margin_info["score_margin"],
        "candidates": proposals,
    }


@router.post("/cnmc/run-batch")
def run_cnmc_batch_matching(
    request: CnmcBatchRunRequest,
    current_user: User = Depends(require_permission("run_matching")),
):
    """
    Match ingested materials against existing common material identities.
    """
    if not store.MATERIALS:
        raise HTTPException(
            status_code=400,
            detail="No materials ingested.",
        )

    if not store.CNMC_REGISTRY:
        return {
            "status": "no_existing_cnmc",
            "materials_evaluated": len(store.MATERIALS),
            "proposals_generated": 0,
            "message": "No existing CNMCs in registry.",
            "proposals": [],
        }

    return match_new_materials_against_cnmcs(
        list(store.MATERIALS),
        max_candidates_per_material=(
            request.max_candidates_per_material
        ),
        min_score=request.min_score,
        create_review_candidates=request.create_review_candidates,
        current_user=current_user,
    )