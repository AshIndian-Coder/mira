"""
Matching routes.

POST /api/matching/compare   — single pair comparison (existing, unchanged)
POST /api/matching/run-batch — dataset-level: block → score → classify all
GET  /api/matching/candidates — list generated candidates with filters
GET  /api/matching/candidates/{id} — single candidate detail
GET  /api/matching/stats     — blocking / recall / score summary stats
"""

import inspect
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
import app.services.matching.vector_search as vector_search_module
from app.services.normalization.service import normalize_material_description
from app.services.parsing.service import parse_specifications

router = APIRouter(prefix="/matching", tags=["Matching"])
logger = logging.getLogger(__name__)
_MATCHING_RUN_LOCK = threading.Lock()
_VECTOR_SEARCH_BATCH_SIZE = max(1, min(8, EMBED_BATCH_SIZE))


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


def _store_material_to_blocker(m: dict[str, Any]) -> MaterialForBlocking:
    return MaterialForBlocking(
        id=m["id"],
        category=m.get("category"),
        normalized_description=m.get("normalized_description") or m["description"],
        material_grade=m.get("material_grade"),
        manufacturer_part_number=m.get("manufacturer_part_number"),
    )


def _pair_key(a: int, b: int) -> tuple[int, int]:
    """Canonical unordered pair key — avoids A-B and B-A duplicates."""
    return (min(a, b), max(a, b))


def _supported_kwargs(function: Any, values: dict[str, Any]) -> dict[str, Any]:
    try:
        parameters = inspect.signature(function).parameters
    except (TypeError, ValueError):
        return values

    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
        return values
    return {key: value for key, value in values.items() if key in parameters}


def _normalize_vector_results(raw: Any) -> dict[int, list[int]]:
    if not isinstance(raw, dict):
        raise TypeError("Vector search must return a mapping of material IDs to hit IDs.")

    normalized: dict[int, list[int]] = {}
    for source_id, target_ids in raw.items():
        source_id = int(source_id)
        normalized[source_id] = []
        for target_id in target_ids or []:
            try:
                normalized[source_id].append(int(target_id))
            except (TypeError, ValueError):
                logger.debug("Ignoring invalid Milvus hit ID %r for source %s", target_id, source_id)
    return normalized


def _search_vector_candidates(
    items: list[tuple[int, str, str | None]],
    embedding_cache: Any,
    source_cpse_by_id: dict[int, str],
) -> dict[int, list[int]]:
    if not items:
        return {}

    batch_search = getattr(vector_search_module, "search_similar_materials_batch", None)
    if callable(batch_search):
        try:
            kwargs = _supported_kwargs(
                batch_search,
                {
                    "top_k": 50,
                    "embedding_cache": embedding_cache,
                    "batch_size": _VECTOR_SEARCH_BATCH_SIZE,
                },
            )
            results = batch_search(items, **kwargs)
            return _normalize_vector_results(results)
        except MiraRemoteEmbeddingError:
            raise
        except Exception:
            logger.warning(
                "Batched Milvus retrieval failed; falling back to scalar retrieval",
                exc_info=True,
            )
    else:
        logger.warning(
            "Batched Milvus search is unavailable in the deployed vector_search module; "
            "using the compatible scalar search path"
        )

    scalar_search = getattr(vector_search_module, "search_similar_materials", None)
    if not callable(scalar_search):
        logger.error("No supported Milvus search function is available")
        return {}

    results: dict[int, list[int]] = {}
    for material_id, description, category in items:
        try:
            kwargs = _supported_kwargs(
                scalar_search,
                {
                    "category": category,
                    "top_k": 50,
                    "exclude_cpse": source_cpse_by_id.get(int(material_id)),
                    "embedding_cache": embedding_cache,
                },
            )
            hits = scalar_search(description, **kwargs)
            results[int(material_id)] = [int(hit) for hit in (hits or [])]
        except MiraRemoteEmbeddingError:
            raise
        except Exception:
            logger.warning(
                "Scalar Milvus retrieval failed for material %s; continuing without its vector hits",
                material_id,
                exc_info=True,
            )
            results[int(material_id)] = []
    return results


def _finish_failed_job(job_id: str | None, error: Exception) -> None:
    if job_id is None:
        return
    try:
        finish_job(job_id, error=str(error))
    except Exception:
        logger.exception("Failed to mark matching job %s as failed", job_id)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/compare")
def compare_materials(
    request: CompareRequest,
    current_user: User = Depends(get_current_active_user),
):
    """Score and classify a single candidate material pair."""
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
    Dataset-level matching.

    1. Convert all ingested materials to blocker objects.
    2. Build the block index (key → list of material IDs).
    3. For each material generate cross-CPSE candidates via blocking.
    4. Score and classify each unique candidate pair.
    5. Store results in the shared CANDIDATES store.

    Returns a summary: pairs evaluated, decisions breakdown, timing.
    """


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
            detail="Preparing materials and computing embeddings",
        )
        update_job(job_id, phase="embedding")

        existing_candidates = [] if request.overwrite else list(store.CANDIDATES)
        started_at = datetime.now(timezone.utc)

        # --- Build blocker objects & index maps ---
        blocker_objects = [_store_material_to_blocker(material) for material in materials]
        material_index: dict[int, dict[str, Any]] = {material["id"]: material for material in materials}
        material_cpse: dict[int, str] = {
            material["id"]: (material.get("cpse") or "CPSE_GENERIC").strip().upper()
            for material in materials
        }
        available_cpses = set(material_cpse.values())

        filtered_sources = blocker_objects
        source_cpse_filter = request.source_cpse.strip().upper() if request.source_cpse else None
        if source_cpse_filter:
            filtered_sources = [
                bo for bo in blocker_objects
                if material_cpse.get(bo.id) == source_cpse_filter
            ]

        # --- Build inverted block index and precompute keys ---
        block_index: dict[str, list[int]] = {}
        material_block_keys: dict[int, set[str]] = {}
        blocker_by_id: dict[int, MaterialForBlocking] = {}
        target_order: dict[int, int] = {}

        for idx, bo in enumerate(blocker_objects):
            blocker_by_id[bo.id] = bo
            target_order[bo.id] = idx
            keys = generate_block_keys(bo)
            material_block_keys[bo.id] = keys
            for key in keys:
                block_index.setdefault(key, []).append(bo.id)

        # --- Track already-evaluated pairs to avoid duplicates ---
        seen_pairs: set[tuple[int, int]] = {
            _pair_key(candidate["source_material_id"], candidate["target_material_id"])
            for candidate in existing_candidates
        }
        new_candidates_by_source: dict[int, int] = {}

        target_cpse_filter = request.target_cpse.strip().upper() if request.target_cpse else None

        if target_cpse_filter:
            matching_sources = [
                bo for bo in filtered_sources
                if target_cpse_filter in available_cpses
                and material_cpse.get(bo.id) != target_cpse_filter
            ]
        else:
            matching_sources = filtered_sources if len(available_cpses) > 1 else []

        source_cpses = {material_cpse[bo.id] for bo in matching_sources}
        target_cpses_needed = {
            cpse
            for cpse in available_cpses
            if any(
                cpse != source_cpse
                and (target_cpse_filter is None or cpse == target_cpse_filter)
                for source_cpse in source_cpses
            )
        }
        participant_ids = {bo.id for bo in matching_sources}
        participant_ids.update(
            material_id
            for material_id, cpse in material_cpse.items()
            if cpse in target_cpses_needed
        )
        participant_descriptions = [
            material_index[material_id].get("normalized_description")
            or material_index[material_id].get("description")
            or ""
            for material_id in sorted(participant_ids)
        ]
        embedding_cache = precompute_embeddings(
            participant_descriptions,
            batch_size=EMBED_BATCH_SIZE,
        )

        new_candidates: list[dict[str, Any]] = []
        total_pairs_evaluated = 0
        total_sources = len(matching_sources)
        update_job(job_id, phase="scoring", total=total_sources)

        # Report at most ~100 times so the polling endpoint stays cheap.
        report_every = max(1, total_sources // 100)

        for idx, source_bo in enumerate(matching_sources):
            if idx % report_every == 0:
                update_job(
                    job_id,
                    processed=idx,
                                        detail=f"Scoring {material_index[source_bo.id]['material_code']} ({idx} of {total_sources})",
                )

            source_keys = material_block_keys[source_bo.id]
            s_cpse = material_cpse.get(source_bo.id, "CPSE_GENERIC")
            if target_cpse_filter is not None:
                if s_cpse == target_cpse_filter or target_cpse_filter not in available_cpses:
                    continue
            elif len(available_cpses) < 2:
                continue

            def eligible_target(target_id: int, source_cpse: str = s_cpse) -> bool:
                candidate_cpse = material_cpse.get(target_id, "CPSE_GENERIC")
                return candidate_cpse != source_cpse and (
                    target_cpse_filter is None or candidate_cpse == target_cpse_filter
                )

            raw_candidates = blocking_generate_candidates(
                source_bo,
                block_index=block_index,
                target_map=blocker_by_id,
                target_order=target_order,
                source_keys=source_keys,
                target_filter=eligible_target,
            )

            # Cap cross-CPSE candidates per source material
            raw_candidates = raw_candidates[: request.max_candidates_per_material]

            for target_bo in raw_candidates:
                pk = _pair_key(source_bo.id, target_bo.id)
                if pk in seen_pairs:
                    continue
                seen_pairs.add(pk)
                total_pairs_evaluated += 1

                source_mat = material_index[source_bo.id]
                target_mat = material_index[target_bo.id]

                result = classify_match(source_mat, target_mat, embedding_cache=embedding_cache)

                engine_dec = result["decision"]
                # HIGH_CONFIDENCE is the engine's RECOMMENDATION only -- it still
                # requires human approval. Only DIFFERENT is excluded from review.
                review_st = "DIFFERENT" if engine_dec == "DIFFERENT" else "PENDING"

                candidate: dict[str, Any] = {
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
                    "engine_decision": engine_dec,
                    "review_status": review_st,
                    "reviewer_id": None,
                    "reviewer_comments": None,
                    "reviewed_at": None,
                    "created_at": started_at.isoformat(),
                }
                new_candidates.append(candidate)
                new_candidates_by_source[source_bo.id] = new_candidates_by_source.get(source_bo.id, 0) + 1

        # --- Additional candidates from vector search (Milvus) ---
        # Runs AFTER the rule-based blocking above, and only ever ADDS
        # candidates -- never removes or changes anything the rule-based loop
        # already found. If Milvus is unavailable, this is skipped silently.
        vector_items = [
            (
                source_bo.id,
                material_index[source_bo.id].get("normalized_description")
                or material_index[source_bo.id].get("description", ""),
                material_index[source_bo.id].get("category"),
            )
            for source_bo in matching_sources
        ]
        try:
            vector_results = _search_vector_candidates(
                vector_items,
                embedding_cache,
                material_cpse,
            )
        except MiraRemoteEmbeddingError:
            raise
        except Exception:
            logger.warning(
                "Vector candidate retrieval failed; continuing with rule-based candidates",
                exc_info=True,
            )
            vector_results = {}

        for source_bo in matching_sources:
            if new_candidates_by_source.get(source_bo.id, 0) >= request.max_candidates_per_material:
                continue
            source_mat = material_index[source_bo.id]
            for target_id in vector_results.get(source_bo.id, []):
                if target_id == source_bo.id or target_id not in material_index:
                    continue

                target_mat = material_index[target_id]
                target_cpse = (target_mat.get("cpse") or "CPSE_GENERIC").strip().upper()
                source_cpse = (source_mat.get("cpse") or "CPSE_GENERIC").strip().upper()

                if source_cpse == target_cpse:
                    continue
                if target_cpse_filter is not None and target_cpse != target_cpse_filter:
                    continue
                if new_candidates_by_source.get(source_bo.id, 0) >= request.max_candidates_per_material:
                    break

                pk = _pair_key(source_bo.id, target_id)
                if pk in seen_pairs:
                    continue
                seen_pairs.add(pk)
                total_pairs_evaluated += 1

                result = classify_match(source_mat, target_mat, embedding_cache=embedding_cache)
                engine_dec = result["decision"]
                # HIGH_CONFIDENCE is the engine's RECOMMENDATION only -- it still
                # requires human approval. Only DIFFERENT is excluded from review.
                review_st = "DIFFERENT" if engine_dec == "DIFFERENT" else "PENDING"

                candidate = {
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
                    "engine_decision": engine_dec,
                    "review_status": review_st,
                    "reviewer_id": None,
                    "reviewer_comments": None,
                    "reviewed_at": None,
                    "created_at": started_at.isoformat(),
                }
                new_candidates.append(candidate)
                new_candidates_by_source[source_bo.id] = new_candidates_by_source.get(source_bo.id, 0) + 1

        update_job(job_id, phase="storing", processed=total_sources,
                   detail=f"Writing {len(new_candidates)} candidates")

        candidate_ids = (
            store.reserve_candidate_ids(len(new_candidates))
            if new_candidates
            else []
        )
        for candidate, candidate_id in zip(new_candidates, candidate_ids):
            candidate["id"] = candidate_id

        if request.overwrite:
            store.CANDIDATES.clear()
        if new_candidates:
            store.CANDIDATES.extend(new_candidates)

        # No auto-approval: every HIGH_CONFIDENCE / REVIEW candidate stays PENDING
        # until a human approves or rejects it via POST /api/review/queue/{id}/action.
        # The audit trail is therefore written by review.py only, with a real actor.

        finished_at = datetime.now(timezone.utc)
        elapsed_ms = int((finished_at - started_at).total_seconds() * 1000)

        decision_counts: dict[str, int] = {}
        for c in new_candidates:
            d = c["engine_decision"]
            decision_counts[d] = decision_counts.get(d, 0) + 1

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
        _finish_failed_job(job_id, exc)
        logger.warning("Matching stopped because the embedding service failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail=(
                "The MIRA embedding service is temporarily unavailable or timed out. "
                "No new matching candidates were committed. Please retry shortly."
            ),
            headers={"Retry-After": "30"},
        ) from exc
    except Exception as exc:
        _finish_failed_job(job_id, exc)
        raise
    finally:
        _MATCHING_RUN_LOCK.release()


@router.get("/candidates")
def list_candidates(
    decision: str | None = Query(None, description="Filter by engine_decision: HIGH_CONFIDENCE | REVIEW | DIFFERENT"),
    review_status: str | None = Query(None, description="Filter by review_status: PENDING | APPROVED | REJECTED"),
    cpse: str | None = Query(None, description="Filter pairs involving this CPSE"),
    min_score: float | None = Query(None, ge=0.0, le=1.0, description="Minimum final_score"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(get_current_active_user),
):
    """List all generated candidate pairs with optional filters."""
    filtered = store.CANDIDATES

    if decision:
        filtered = [c for c in filtered if c["engine_decision"] == decision.upper()]

    if review_status:
        filtered = [c for c in filtered if c["review_status"] == review_status.upper()]

    if cpse:
        cpse_upper = cpse.upper()
        filtered = [
            c for c in filtered
            if c["source_cpse"].upper() == cpse_upper
            or c["target_cpse"].upper() == cpse_upper
        ]

    if min_score is not None:
        filtered = [
            c for c in filtered
            if c["scores"].get("final_score", 0) >= min_score
        ]

    total = len(filtered)
    paginated = filtered[skip: skip + limit]

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
    """Retrieve a single candidate pair by ID."""
    for c in store.CANDIDATES:
        if c["id"] == candidate_id:
            return c
    raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found")


@router.get("/stats")
def matching_stats(current_user: User = Depends(get_current_active_user)):
    """
    Batch-level statistics useful for evaluation and the analytics dashboard.
    """
    if not store.CANDIDATES:
        return {
            "total_candidates": 0,
            "message": "No candidates yet. Run POST /api/matching/run-batch first.",
        }

    total = len(store.CANDIDATES)
    decision_counts: dict[str, int] = {}
    review_status_counts: dict[str, int] = {}
    scores = []

    for c in store.CANDIDATES:
        d = c["engine_decision"]
        decision_counts[d] = decision_counts.get(d, 0) + 1
        rs = c["review_status"]
        review_status_counts[rs] = review_status_counts.get(rs, 0) + 1
        scores.append(c["scores"].get("final_score", 0.0))

    scores.sort()
    n = len(scores)
    p50 = scores[n // 2] if n else 0.0
    p90 = scores[int(n * 0.90)] if n else 0.0
    p95 = scores[int(n * 0.95)] if n else 0.0

    n_materials = len(store.MATERIALS)
    theoretical_max = n_materials * (n_materials - 1) // 2
    blocking_reduction = (
        round(1.0 - total / theoretical_max, 4) if theoretical_max > 0 else None
    )

    reviewable = decision_counts.get("HIGH_CONFIDENCE", 0) + decision_counts.get("REVIEW", 0)
    automation_rate = (
        round(decision_counts.get("HIGH_CONFIDENCE", 0) / reviewable, 4)
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
    """Find and rank plausible existing CNMC candidate proposals for a material."""
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
    """Run existing-CNMC matching across all ingested materials against established CNMCs."""
    if not store.MATERIALS:
        raise HTTPException(status_code=400, detail="No materials ingested.")
    if not store.CNMC_REGISTRY:
        return {
            "status": "no_existing_cnmc",
            "materials_evaluated": len(store.MATERIALS),
            "proposals_generated": 0,
            "message": "No existing CNMCs in registry.",
            "proposals": [],
        }
    res = match_new_materials_against_cnmcs(
        list(store.MATERIALS),
        max_candidates_per_material=request.max_candidates_per_material,
        min_score=request.min_score,
        create_review_candidates=request.create_review_candidates,
        current_user=current_user,
    )
    return res
