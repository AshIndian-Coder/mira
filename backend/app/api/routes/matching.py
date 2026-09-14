"""
Matching routes.

POST /api/matching/compare   — single pair comparison (existing, unchanged)
POST /api/matching/run-batch — dataset-level: block → score → classify all
GET  /api/matching/candidates — list generated candidates with filters
GET  /api/matching/candidates/{id} — single candidate detail
GET  /api/matching/stats     — blocking / recall / score summary stats
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.matching.classifier import classify_match
from app.services.normalization.service import normalize_material_description
from app.services.parsing.service import parse_specifications
from app.services.blocking.service import (
    MaterialForBlocking,
    generate_block_keys,
    generate_candidates as blocking_generate_candidates,
)
from app import store

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
def compare_materials(request: CompareRequest):
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
def run_batch_matching(request: BatchRunRequest):
    """
    Dataset-level matching.

    1. Convert all ingested materials to blocker objects.
    2. Build the block index (key → list of material IDs).
    3. For each material generate candidates via blocking.
    4. Score and classify each unique candidate pair.
    5. Store results in the shared CANDIDATES store.

    Returns a summary: pairs evaluated, decisions breakdown, timing.
    """
    if not store.MATERIALS:
        raise HTTPException(
            status_code=400,
            detail="No materials ingested. Upload a CSV via POST /api/materials/upload first.",
        )

    if request.overwrite:
        store.CANDIDATES.clear()

    started_at = datetime.now(timezone.utc)

    # --- Build blocker objects ---
    blocker_objects = [_store_material_to_blocker(m) for m in store.MATERIALS]
    material_index: dict[int, dict[str, Any]] = {m["id"]: m for m in store.MATERIALS}

    # --- Build inverted block index ---
    block_index: dict[str, list[int]] = {}
    for bo in blocker_objects:
        for key in generate_block_keys(bo):
            block_index.setdefault(key, []).append(bo.id)

    # --- Track already-evaluated pairs to avoid duplicates ---
    seen_pairs: set[tuple[int, int]] = {
        _pair_key(c["source_material_id"], c["target_material_id"])
        for c in store.CANDIDATES
    }

    new_candidates: list[dict[str, Any]] = []
    total_pairs_evaluated = 0

    for source_bo in blocker_objects:
        raw_candidates = blocking_generate_candidates(source_bo, blocker_objects)

        # Cap per source material to avoid O(n²) explosion on large datasets
        raw_candidates = raw_candidates[: request.max_candidates_per_material]

        for target_bo in raw_candidates:
            source_mat = material_index[source_bo.id]
            target_mat = material_index[target_bo.id]

            # Batch harmonization is cross-CPSE only.
            if source_mat["cpse"].upper() == target_mat["cpse"].upper():
                continue

            pk = _pair_key(source_bo.id, target_bo.id)
            if pk in seen_pairs:
                continue
            seen_pairs.add(pk)
            total_pairs_evaluated += 1

            result = classify_match(source_mat, target_mat)

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
                "engine_decision": result["decision"],
                "review_status": "PENDING"
                if result["decision"] == "REVIEW"
                else result["decision"],
                "reviewer_id": None,
                "reviewer_comments": None,
                "reviewed_at": None,
                "created_at": started_at.isoformat(),
            }
            new_candidates.append(candidate)

    store.CANDIDATES.extend(new_candidates)

    finished_at = datetime.now(timezone.utc)
    elapsed_ms = int((finished_at - started_at).total_seconds() * 1000)

    decision_counts: dict[str, int] = {}
    for c in new_candidates:
        d = c["engine_decision"]
        decision_counts[d] = decision_counts.get(d, 0) + 1

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
    decision: str | None = Query(None, description="Filter by engine_decision: HIGH_CONFIDENCE | REVIEW | DIFFERENT"),
    review_status: str | None = Query(None, description="Filter by review_status: PENDING | APPROVED | REJECTED"),
    cpse: str | None = Query(None, description="Filter pairs involving this CPSE"),
    min_score: float | None = Query(None, ge=0.0, le=1.0, description="Minimum final_score"),
    skip: int = 0,
    limit: int = 50,
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
def get_candidate(candidate_id: int):
    """Retrieve a single candidate pair by ID."""
    for c in store.CANDIDATES:
        if c["id"] == candidate_id:
            return c
    raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found")


@router.get("/stats")
def matching_stats():
    """
    Batch-level statistics useful for evaluation and the analytics dashboard.

    Reports:
    - Total candidates and decision breakdown
    - Blocking reduction ratio (candidates vs theoretical O(n²))
    - Score distribution percentiles
    - Automation rate (HIGH_CONFIDENCE / total that aren't DIFFERENT)
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
