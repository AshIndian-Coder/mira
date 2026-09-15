"""
Analytics route.

GET /api/analytics/overview    — dashboard-level KPIs
GET /api/analytics/by-cpse     — material and match counts per CPSE
GET /api/analytics/categories  — category distribution
GET /api/analytics/scores      — score histogram buckets
"""

from fastapi import APIRouter

from app import store

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/overview")
def analytics_overview():
    """High-level KPIs for the dashboard header cards."""
    total_materials = len(store.MATERIALS)
    total_candidates = len(store.CANDIDATES)

    high_confidence = sum(
        1 for c in store.CANDIDATES if c["engine_decision"] == "HIGH_CONFIDENCE"
    )
    review_pending = sum(
        1 for c in store.CANDIDATES
        if c["engine_decision"] == "REVIEW" and c["review_status"] == "PENDING"
    )
    approved = sum(
        1 for c in store.CANDIDATES if c["review_status"] == "APPROVED"
    )
    rejected = sum(
        1 for c in store.CANDIDATES if c["review_status"] == "REJECTED"
    )

    # Automation rate: pairs resolved without human (HC) / all actionable pairs
    actionable = high_confidence + sum(
        1 for c in store.CANDIDATES if c["engine_decision"] == "REVIEW"
    )
    automation_rate = round(high_confidence / actionable, 4) if actionable else None

    cpse_count = len({m["cpse"] for m in store.MATERIALS})

    return {
        "total_materials": total_materials,
        "cpse_count": cpse_count,
        "total_candidate_pairs": total_candidates,
        "high_confidence": high_confidence,
        "review_pending": review_pending,
        "approved": approved,
        "rejected": rejected,
        "automation_rate": automation_rate,
    }


@router.get("/by-cpse")
def analytics_by_cpse():
    """Per-CPSE breakdown: material count and involvement in candidate pairs."""
    cpse_materials: dict[str, int] = {}
    for m in store.MATERIALS:
        cpse_materials[m["cpse"]] = cpse_materials.get(m["cpse"], 0) + 1

    cpse_candidates: dict[str, int] = {}
    for c in store.CANDIDATES:
        for cpse in (c["source_cpse"], c["target_cpse"]):
            cpse_candidates[cpse] = cpse_candidates.get(cpse, 0) + 1

    rows = []
    for cpse, mat_count in sorted(cpse_materials.items()):
        rows.append({
            "cpse": cpse,
            "material_count": mat_count,
            "candidate_pair_involvements": cpse_candidates.get(cpse, 0),
        })

    return {"cpse_breakdown": rows}


@router.get("/categories")
def analytics_categories():
    """Category distribution of ingested materials."""
    counts: dict[str, int] = {}
    for m in store.MATERIALS:
        cat = m.get("category") or "Uncategorised"
        counts[cat] = counts.get(cat, 0) + 1

    rows = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    return {
        "category_distribution": [
            {"category": cat, "count": cnt} for cat, cnt in rows
        ]
    }


@router.get("/scores")
def analytics_score_distribution():
    """
    Final-score histogram in 0.1-wide buckets.
    Useful for tuning thresholds and spotting score distribution shape.
    """
    buckets = {f"{i/10:.1f}-{(i+1)/10:.1f}": 0 for i in range(10)}

    for c in store.CANDIDATES:
        score = c["scores"].get("final_score", 0.0)
        bucket_idx = min(int(score * 10), 9)
        key = f"{bucket_idx/10:.1f}-{(bucket_idx + 1)/10:.1f}"
        buckets[key] = buckets.get(key, 0) + 1

    return {
        "total_candidates": len(store.CANDIDATES),
        "score_histogram": [
            {"bucket": k, "count": v} for k, v in buckets.items()
        ],
    }
