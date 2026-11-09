
"""
Matching routes.

POST /api/matching/compare
POST /api/matching/run-batch
GET  /api/matching/candidates
GET  /api/matching/candidates/{id}
GET  /api/matching/stats
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app import store
from app.core.rbac import require_permission
from app.core.security import get_current_active_user
from app.jobs import create_job, finish_job, update_job
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
from app.services.matching.embeddings import (
    EMBED_BATCH_SIZE,
    MiraRemoteEmbeddingError,
    precompute_embeddings,
)
from app.services.matching.vector_search import search_similar_materials
from app.services.normalization.service import normalize_material_description
from app.services.parsing.service import parse_specifications

router = APIRouter(prefix="/matching", tags=["Matching"])
logger = logging.getLogger(__name__)
_MATCHING_RUN_LOCK = threading.Lock()


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
        description="Cap on blocking output per source material to control runtime.",
    )
    overwrite: bool = Field(
        default=False,
        description="If True, clear existing candidates before running.",
    )
    source_cpse: str | None = Field(
        default=None,
        description="Optional filter to only process source materials from this CPSE.",
    )
    target_cpse: str | None = Field(
        default=None,
        description="Optional filter to only match against candidate materials from this CPSE.",
    )


class CnmcMatchRequest(BaseModel):
    material: MaterialInput
    max_candidates: int = Field(default=10, ge=1, le=50)
    min_score: float = Field(default=0.50, ge=0.0, le=1.0)


class CnmcBatchRunRequest(BaseModel):
    max_candidates_per_material: int = Field(default=5, ge=1, le=50)
    min_score: float = Field(default=0.65, ge=0.0, le=1.0)
    create_review_candidates: bool = Field(default=True)


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


def _store_material_to_blocker(m: dict[str, Any]) -> MaterialForBlocking:
    return MaterialForBlocking(
        id=m["id"],
        category=m.get("category"),
        normalized_description=m.get("normalized_description") or m["description"],
        material_grade=m.get("material_grade"),
        manufacturer_part_number=m.get("manufacturer_part_number"),
    )


def _pair_key(a: int, b: int) -> tuple[int, int]:
    return (min(a, b), max(a, b))


@router.post("/compare")
def compare_materials(
    request: CompareRequest,
    current_user: User = Depends(get_current_active_user),
):
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
    materials = list(store.MATERIALS)

    if not materials:
        raise HTTPException(
            status_code=400,
            detail="No materials ingested. Upload a CSV via POST /api/materials/upload first.",
        )

    if not _MATCHING_RUN_LOCK.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail="A matching run is already in progress. Wait for it to finish before starting another.",
        )

    job_id: str | None = None

    try:
        job_id = create_job(
            "matching",
            total=len(materials),
            detail="Loading model and computing embedding vectors",
        )
        update_job(job_id, phase="embedding")

        existing_candidates = (
            [] if request.overwrite else list(store.CANDIDATES)
        )

        started_at = datetime.now(timezone.utc)

        blocker_objects = [
            _store_material_to_blocker(material)
            for material in materials
        ]

        material_index = {
            material["id"]: material
            for material in materials
        }

        material_cpse = {
            material["id"]: (
                material.get("cpse") or "CPSE_GENERIC"
            ).strip().upper()
            for material in materials
        }

        available_cpses = set(material_cpse.values())

        filtered_sources = blocker_objects

        if request.source_cpse:
            source_cpse_filter = request.source_cpse.strip().upper()
            filtered_sources = [
                material
                for material in blocker_objects
                if material_cpse.get(material.id) == source_cpse_filter
            ]

        block_index: dict[str, list[int]] = {}
        material_block_keys: dict[int, set[str]] = {}
        blocker_by_id: dict[int, MaterialForBlocking] = {}
        target_order: dict[int, int] = {}

        for index, material in enumerate(blocker_objects):
            blocker_by_id[material.id] = material
            target_order[material.id] = index

            keys = generate_block_keys(material)
            material_block_keys[material.id] = keys

            for key in keys:
                block_index.setdefault(key, []).append(material.id)

        seen_pairs = {
            _pair_key(
                candidate["source_material_id"],
                candidate["target_material_id"],
            )
            for candidate in existing_candidates
        }

        new_candidates_by_source: dict[int, int] = {}

        target_cpse_filter = (
            request.target_cpse.strip().upper()
            if request.target_cpse
            else None
        )

        all_descriptions = [
            material.get("normalized_description")
            or material.get("description")
            or ""
            for material in materials
        ]

        embedding_cache = precompute_embeddings(
            all_descriptions,
            batch_size=EMBED_BATCH_SIZE,
        )

        new_candidates: list[dict[str, Any]] = []
        total_pairs_evaluated = 0
        total_sources = len(filtered_sources)

        update_job(
            job_id,
            phase="scoring",
            total=total_sources,
        )

        report_every = max(1, total_sources // 100)

        for index, source_bo in enumerate(filtered_sources):
            if index % report_every == 0:
                update_job(
                    job_id,
                    processed=index,
                    detail=(
                        f"Scoring "
                        f"{material_index[source_bo.id]['material_code']} "
                        f"({index} of {total_sources})"
                    ),
                )

            source_keys = material_block_keys[source_bo.id]
            source_cpse = material_cpse.get(
                source_bo.id,
                "CPSE_GENERIC",
            )

            if target_cpse_filter is not None:
                if (
                    source_cpse == target_cpse_filter
                    or target_cpse_filter not in available_cpses
                ):
                    continue
            elif len(available_cpses) < 2:
                continue

            def eligible_target(
                target_id: int,
                source_cpse: str = source_cpse,
            ) -> bool:
                candidate_cpse = material_cpse.get(
                    target_id,
                    "CPSE_GENERIC",
                )
                return (
                    candidate_cpse != source_cpse
                    and (
                        target_cpse_filter is None
                        or candidate_cpse == target_cpse_filter
                    )
                )

            raw_candidates = blocking_generate_candidates(
                source_bo,
                block_index=block_index,
                target_map=blocker_by_id,
                target_order=target_order,
                source_keys=source_keys,
                target_filter=eligible_target,
            )

            raw_candidates = raw_candidates[
                :request.max_candidates_per_material
            ]

            for target_bo in raw_candidates:
                pair = _pair_key(source_bo.id, target_bo.id)

                if pair in seen_pairs:
                    continue

                seen_pairs.add(pair)
                total_pairs_evaluated += 1

                source_mat = material_index[source_bo.id]
                target_mat = material_index[target_bo.id]

                result = classify_match(
                    source_mat,
                    target_mat,
                    embedding_cache=embedding_cache,
                )

                engine_decision = result["decision"]
                review_status = (
                    "DIFFERENT"
                    if engine_decision == "DIFFERENT"
                    else "PENDING"
                )

                new_candidates.append({
                    "id": None,
                    "source_material_id": source_bo.id,
                    "target_material_id": target_bo.id,
                    "source_cpse": source_mat["cpse"],
                    "target_cpse": target_mat["cpse"],
                    "source_code": source_mat["material_code"],
                    "target_code": target_mat["material_code"],
                    "source_description": source_mat["description"],
                    "target_description": target_mat["description"],
                    "scores": result["scores"],
                    "critical_checks": result["critical_checks"],
                    "engine_decision": engine_decision,
                    "review_status": review_status,
                    "reviewer_id": None,
                    "reviewer_comments": None,
                    "reviewed_at": None,
                    "created_at": started_at.isoformat(),
                })

                new_candidates_by_source[source_bo.id] = (
                    new_candidates_by_source.get(source_bo.id, 0) + 1
                )

        vector_results: dict[int, list[int]] = {}

        try:
            for source_bo in filtered_sources:
                source_mat = material_index[source_bo.id]
                source_cpse = material_cpse.get(
                    source_bo.id,
                    "CPSE_GENERIC",
                )

                description = (
                    source_mat.get("normalized_description")
                    or source_mat.get("description", "")
                )

                vector_results[source_bo.id] = search_similar_materials(
                    description=description,
                    category=source_mat.get("category"),
                    top_k=50,
                    exclude_cpse=source_cpse,
                    embedding_cache=embedding_cache,
                )

        except Exception:
            logger.warning(
                "Vector candidate retrieval failed; continuing with rule-based candidates",
                exc_info=True,
            )
            vector_results = {}

        for source_bo in filtered_sources:
            if (
                new_candidates_by_source.get(source_bo.id, 0)
                >= request.max_candidates_per_material
            ):
                continue

            source_mat = material_index[source_bo.id]

            for target_id in vector_results.get(source_bo.id, []):
                if (
                    target_id == source_bo.id
                    or target_id not in material_index
                ):
                    continue

                target_mat = material_index[target_id]

                target_cpse = (
                    target_mat.get("cpse") or "CPSE_GENERIC"
                ).strip().upper()

                source_cpse = (
                    source_mat.get("cpse") or "CPSE_GENERIC"
                ).strip().upper()

                if source_cpse == target_cpse:
                    continue

                if (
                    target_cpse_filter is not None
                    and target_cpse != target_cpse_filter
                ):
                    continue

                if (
                    new_candidates_by_source.get(source_bo.id, 0)
                    >= request.max_candidates_per_material
                ):
                    break

                pair = _pair_key(source_bo.id, target_id)

                if pair in seen_pairs:
                    continue

                seen_pairs.add(pair)
                total_pairs_evaluated += 1

                result = classify_match(
                    source_mat,
                    target_mat,
                    embedding_cache=embedding_cache,
                )

                engine_decision = result["decision"]
                review_status = (
                    "DIFFERENT"
                    if engine_decision == "DIFFERENT"
                    else "PENDING"
                )

                new_candidates.append({
                    "id": None,
                    "source_material_id": source_bo.id,
                    "target_material_id": target_id,
                    "source_cpse": source_mat["cpse"],
                    "target_cpse": target_mat["cpse"],
                    "source_code": source_mat["material_code"],
                    "target_code": target_mat["material_code"],
                    "source_description": source_mat["description"],
                    "target_description": target_mat["description"],
                    "scores": result["scores"],
                    "critical_checks": result["critical_checks"],
                    "engine_decision": engine_decision,
                    "review_status": review_status,
                    "reviewer_id": None,
                    "reviewer_comments": None,
                    "reviewed_at": None,
                    "created_at": started_at.isoformat(),
                })

                new_candidates_by_source[source_bo.id] = (
                    new_candidates_by_source.get(source_bo.id, 0) + 1
                )

        update_job(
            job_id,
            phase="storing",
            processed=total_sources,
            detail=f"Writing {len(new_candidates)} candidates",
        )

        candidate_ids = (
            store.reserve_candidate_ids(len(new_candidates))
            if new_candidates
            else []
        )

        for candidate, candidate_id in zip(new_candidates, candidate_ids):
            candidate["id"] = candidate_id

        if request.overwrite:
            store.CANDIDATES.clear()

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

        summary = {
            "status": "complete",
            "materials_processed": len(materials),
            "candidate_pairs_evaluated": total_pairs_evaluated,
            "new_candidates_stored": len(new_candidates),
            "total_candidates": len(store.CANDIDATES),
            "decision_breakdown": decision_counts,
            "elapsed_ms": elapsed_ms,
        }

        finish_job(job_id, result=summary)
        return summary

    except MiraRemoteEmbeddingError as exc:
        if job_id is not None:
            finish_job(job_id, error=str(exc))

        logger.warning(
            "Matching stopped because the embedding service is unavailable: %s",
            exc,
            exc_info=True,
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "The MIRA embedding service did not respond in time. "
                "The matching job was not committed; wait briefly and retry."
            ),
            headers={"Retry-After": "30"},
        ) from exc

    except Exception as exc:
        if job_id is not None:
            finish_job(job_id, error=str(exc))
        raise

    finally:
        _MATCHING_RUN_LOCK.release()


@router.get("/candidates")
def list_candidates(
    decision: str | None = Query(None),
    review_status: str | None = Query(None),
    cpse: str | None = Query(None),
    min_score: float | None = Query(None, ge=0.0, le=1.0),
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_active_user),
):
    filtered = store.CANDIDATES

    if decision:
        filtered = [
            c for c in filtered
            if c["engine_decision"] == decision.upper()
        ]

    if review_status:
        filtered = [
            c for c in filtered
            if c["review_status"] == review_status.upper()
        ]

    if cpse:
        cpse_upper = cpse.upper()
        filtered = [
            c for c in filtered
            if (
                c["source_cpse"].upper() == cpse_upper
                or c["target_cpse"].upper() == cpse_upper
            )
        ]

    if min_score is not None:
        filtered = [
            c for c in filtered
            if c["scores"].get("final_score", 0) >= min_score
        ]

    total = len(filtered)
    paginated = filtered[skip:skip + limit]

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
    if not store.CANDIDATES:
        return {
            "total_candidates": 0,
            "message": "No candidates yet. Run POST /api/matching/run-batch first.",
        }

    total = len(store.CANDIDATES)
    decision_counts: dict[str, int] = {}
    review_status_counts: dict[str, int] = {}
    scores = []

    for candidate in store.CANDIDATES:
        decision = candidate["engine_decision"]
        decision_counts[decision] = decision_counts.get(decision, 0) + 1

        review_status = candidate["review_status"]
        review_status_counts[review_status] = (
            review_status_counts.get(review_status, 0) + 1
        )

        scores.append(candidate["scores"].get("final_score", 0.0))

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

    reviewable = (
        decision_counts.get("HIGH_CONFIDENCE", 0)
        + decision_counts.get("REVIEW", 0)
    )

    automation_rate = (
        round(
            decision_counts.get("HIGH_CONFIDENCE", 0) / reviewable,
            4,
        )
        if reviewable > 0
        else None
    )

    return {
        "total_candidates": total,
        "decision_breakdown": decision_counts,
        "review_status_breakdown": review_status_counts,
        "automation_rate": automation_rate,
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
        max_candidates_per_material=request.max_candidates_per_material,
        min_score=request.min_score,
        create_review_candidates=request.create_review_candidates,
        current_user=current_user,
    )
