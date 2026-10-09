"""
Matching routes.

POST /api/matching/compare   — single pair comparison (existing, unchanged)
POST /api/matching/run-batch — dataset-level: block → score → classify all
GET  /api/matching/candidates — list generated candidates with filters
GET  /api/matching/candidates/{id} — single candidate detail
GET  /api/matching/stats     — blocking / recall / score summary stats
"""

from datetime import datetime, timezone
import hashlib
from typing import Any

import numpy as np

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app import store
from app.core.rbac import require_permission
from app.core.security import get_current_active_user
from app.db_adapter import load_material_embeddings, upsert_material_embeddings
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
    EmbeddingCache,
    get_embedding_device,
    get_embedding_model_name,
    precompute_embeddings,
)
from app.services.matching.milvus_client import insert_material_embeddings
from app.services.matching.vector_search import search_similar_materials
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


    if not store.MATERIALS:
        raise HTTPException(
            status_code=400,
            detail="No materials ingested. Upload a CSV via POST /api/materials/upload first.",
        )

    job_id = create_job(
        "matching",
        total=len(store.MATERIALS),
        detail="Preparing matching run",
    )
    update_job(job_id, phase="preparing", indeterminate=True)

    try:
        if request.overwrite:
            store.CANDIDATES.clear()

        started_at = datetime.now(timezone.utc)

        # --- Build blocker objects & index maps ---
        blocker_objects = [_store_material_to_blocker(m) for m in store.MATERIALS]
        material_index: dict[int, dict[str, Any]] = {m["id"]: m for m in store.MATERIALS}
        material_cpse: dict[int, str] = {
            m["id"]: (m.get("cpse") or "CPSE_GENERIC").strip().upper()
            for m in store.MATERIALS
        }

        # Filter source materials if requested
        filtered_sources = blocker_objects
        if request.source_cpse:
            req_sc = request.source_cpse.strip().upper()
            filtered_sources = [bo for bo in blocker_objects if material_cpse.get(bo.id) == req_sc]

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
            _pair_key(c["source_material_id"], c["target_material_id"])
            for c in store.CANDIDATES
        }

        # Pre-partition blockers by CPSE for fast cross-CPSE target mapping
        cpse_blockers: dict[str, dict[int, MaterialForBlocking]] = {}
        for bo in blocker_objects:
            c = material_cpse.get(bo.id, "CPSE_GENERIC")
            cpse_blockers.setdefault(c, {})[bo.id] = bo

        target_map_by_source_cpse: dict[str, dict[int, MaterialForBlocking]] = {}
        for s_cpse in cpse_blockers:
            t_map: dict[int, MaterialForBlocking] = {}
            for t_cpse, t_dict in cpse_blockers.items():
                if t_cpse == s_cpse:
                    continue
                if request.target_cpse and t_cpse != request.target_cpse.strip().upper():
                    continue
                t_map.update(t_dict)
            target_map_by_source_cpse[s_cpse] = t_map

        all_descriptions = [
            m.get("normalized_description") or m.get("description") or ""
            for m in store.MATERIALS
        ]
        unique_descriptions = {description for description in all_descriptions if description}
        embedding_total = len(unique_descriptions)
        model_name = get_embedding_model_name()
        expected_hash_by_text = {
            text: hashlib.sha256(text.encode("utf-8")).hexdigest()
            for text in unique_descriptions
        }
        material_text_by_id = {
            int(m["id"]): (m.get("normalized_description") or m.get("description") or "").strip()
            for m in store.MATERIALS
        }
        saved_rows = load_material_embeddings()
        saved_by_id = {int(row["material_id"]): row for row in saved_rows}
        cached_embeddings: dict[str, np.ndarray] = {}
        valid_material_ids: set[int] = set()
        for material_id, text in material_text_by_id.items():
            saved = saved_by_id.get(material_id)
            if not saved or not text:
                continue
            vector = saved.get("embedding")
            if (
                saved.get("model_name") == model_name
                and saved.get("text_hash") == expected_hash_by_text.get(text)
                and isinstance(vector, list)
                and len(vector) == 1024
            ):
                cached_embeddings.setdefault(text, np.asarray(vector, dtype=np.float32))
                valid_material_ids.add(material_id)

        missing_descriptions = unique_descriptions.difference(cached_embeddings)
        cached_count = len(unique_descriptions) - len(missing_descriptions)
        update_job(
            job_id,
            phase="embedding",
            processed=0,
            total=max(embedding_total, 1),
            progress_percent=0,
            indeterminate=True,
            detail=(
                f"Using {cached_count} saved embeddings; loading model on {get_embedding_device()}…"
                if missing_descriptions
                else f"Loaded {cached_count} saved embeddings"
            ),
        )

        def _embed_progress(done: int, total: int) -> None:
            overall_done = cached_count + done
            update_job(
                job_id,
                processed=overall_done,
                total=max(embedding_total, 1),
                detail=f"Embeddings ready ({overall_done} of {embedding_total})",
                progress_percent=45 * (overall_done / embedding_total) if embedding_total else 45,
                indeterminate=False,
            )

        embedding_cache = EmbeddingCache(
            initial_embeddings=cached_embeddings,
            model_name=model_name,
        )
        embedding_cache.precompute(
            all_descriptions,
            batch_size=64,
            progress_callback=_embed_progress,
        )
        # Save newly-created or stale vectors before scoring, then send the same
        # vector payload to Milvus so retrieval and score calculations agree.
        embedding_rows_to_save = []
        vectors_by_id: dict[int, list[float]] = {}
        for material_id, text in material_text_by_id.items():
            vector = embedding_cache.get(text)
            if vector is None:
                continue
            vector_list = vector.tolist() if hasattr(vector, "tolist") else list(vector)
            vectors_by_id[material_id] = vector_list
            if material_id not in valid_material_ids:
                embedding_rows_to_save.append({
                    "material_id": material_id,
                    "model_name": model_name,
                    "text_hash": expected_hash_by_text[text],
                    "embedding": vector_list,
                })
        upsert_material_embeddings(embedding_rows_to_save)

        update_job(
            job_id,
            phase="scoring",
            processed=0,
            total=max(len(filtered_sources), 1),
            progress_percent=45,
            indeterminate=False,
            detail="Scoring candidate pairs",
        )
        new_candidates: list[dict[str, Any]] = []
        total_pairs_evaluated = 0

        total_sources = len(filtered_sources)

        # Report at most ~100 times so the polling endpoint stays cheap.
        report_every = max(1, (total_sources + 99) // 100)

        def _report_scoring(done: int) -> None:
            if done % report_every == 0 or done == total_sources:
                update_job(
                    job_id,
                    processed=done,
                    detail=f"Scoring materials ({done} of {total_sources})",
                    progress_percent=45 + 35 * (done / total_sources) if total_sources else 80,
                )

        for idx, source_bo in enumerate(filtered_sources):
            source_keys = material_block_keys[source_bo.id]
            s_cpse = material_cpse.get(source_bo.id, "CPSE_GENERIC")
            cross_target_map = target_map_by_source_cpse.get(s_cpse)
            if not cross_target_map:
                _report_scoring(idx + 1)
                continue

            raw_candidates = blocking_generate_candidates(
                source_bo,
                block_index=block_index,
                target_map=cross_target_map,
                target_order=target_order,
                source_keys=source_keys,
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
                    "id": store.next_candidate_id(),
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

            _report_scoring(idx + 1)

        # --- Additional candidates from vector search (Milvus) ---
        # Runs AFTER the rule-based blocking above, and only ever ADDS
        # candidates -- never removes or changes anything the rule-based loop
        # already found. If Milvus is unavailable, this is skipped silently.
        total_vec = len(blocker_objects)
        vec_report_every = max(1, (total_vec + 99) // 100)
        update_job(
            job_id,
            phase="vector_search",
            processed=0,
            total=max(total_vec, 1),
            progress_percent=80,
            indeterminate=False,
            detail="Syncing saved vectors to Milvus, then searching for extra candidates",
        )
        insert_material_embeddings([
            {
                "id": material_id,
                "description": material_text_by_id[material_id],
                "cpse": material_index[material_id].get("cpse") or "",
                "category": material_index[material_id].get("category") or "",
            }
            for material_id in vectors_by_id
        ], vectors_by_id=vectors_by_id)
        for v_idx, source_bo in enumerate(blocker_objects):
            source_mat = material_index[source_bo.id]
            try:
                vector_ids = search_similar_materials(
                    description=source_mat.get("normalized_description", ""),
                    category=source_mat.get("category"),
                    top_k=50,
                    embedding_cache=embedding_cache,
                )
            except Exception:
                vector_ids = []

            for target_id in vector_ids:
                if target_id == source_bo.id or target_id not in material_index:
                    continue

                target_mat = material_index[target_id]

                if source_mat["cpse"].upper() == target_mat["cpse"].upper():
                    continue

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
                    "id": store.next_candidate_id(),
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

            done = v_idx + 1
            if done % vec_report_every == 0 or done == total_vec:
                update_job(
                    job_id,
                    processed=done,
                    detail=f"Vector search ({done} of {total_vec})",
                    progress_percent=80 + 17 * (done / total_vec) if total_vec else 97,
                )

        update_job(
            job_id,
            phase="storing",
            processed=0,
            total=max(len(new_candidates), 1),
            progress_percent=97,
            indeterminate=True,
            detail=f"Saving {len(new_candidates)} candidate records…",
        )

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
            "materials_processed": len(store.MATERIALS),
            "candidate_pairs_evaluated": total_pairs_evaluated,
            "new_candidates_stored": len(new_candidates),
            "total_candidates": len(store.CANDIDATES),
            "decision_breakdown": decision_counts,
            "elapsed_ms": elapsed_ms,
        }
        finish_job(job_id, result=summary)
        return summary
    except Exception as exc:
        finish_job(job_id, error=str(exc))
        raise


@router.get("/candidates")
def list_candidates(
    decision: str | None = Query(None, description="Filter by engine_decision: HIGH_CONFIDENCE | REVIEW | DIFFERENT"),
    review_status: str | None = Query(None, description="Filter by review_status: PENDING | APPROVED | REJECTED"),
    cpse: str | None = Query(None, description="Filter pairs involving this CPSE"),
    min_score: float | None = Query(None, ge=0.0, le=1.0, description="Minimum final_score"),
    skip: int = 0,
    limit: int = 50,
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
