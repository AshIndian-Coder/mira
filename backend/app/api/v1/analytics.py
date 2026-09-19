"""
Analytics route.

GET /api/analytics/overview    — dashboard-level KPIs
GET /api/analytics/by-cpse     — material and match counts per CPSE
GET /api/analytics/categories  — category distribution
GET /api/analytics/scores      — score histogram buckets
"""

from fastapi import APIRouter, Depends

from app import store
from app.core.security import get_current_active_user
from app.models.user import User

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/overview")
def analytics_overview(current_user: User = Depends(get_current_active_user)):
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
def analytics_by_cpse(current_user: User = Depends(get_current_active_user)):
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
def analytics_categories(current_user: User = Depends(get_current_active_user)):
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
def analytics_score_distribution(current_user: User = Depends(get_current_active_user)):
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


@router.get("/data-quality")
def analytics_data_quality(current_user: User = Depends(get_current_active_user)):
    """
    Data-quality breakdown computed directly from ingested materials in the master store.
    Measures field completeness, specification parsing yield, and CPSE data health.
    """
    total = len(store.MATERIALS)
    if total == 0:
        return {
            "total_materials": 0,
            "with_parsed_specs": 0,
            "parsed_specs_rate": 0.0,
            "missing_description": 0,
            "missing_category": 0,
            "missing_material_grade": 0,
            "missing_dimensions": 0,
            "missing_pressure_rating": 0,
            "parsing_failures": 0,
            "completeness_score": 0.0,
            "by_cpse_quality": [],
        }

    with_parsed_specs = 0
    missing_desc = 0
    missing_cat = 0
    missing_grade = 0
    missing_dim = 0
    missing_pressure = 0
    parsing_failures = 0

    cpse_stats: dict[str, dict[str, int]] = {}

    for m in store.MATERIALS:
        cpse = m.get("cpse") or "CPSE_GENERIC"
        if cpse not in cpse_stats:
            cpse_stats[cpse] = {
                "total": 0,
                "with_parsed_specs": 0,
                "missing_grade": 0,
                "missing_dimensions": 0,
                "missing_pressure": 0,
            }
        cpse_stats[cpse]["total"] += 1

        desc = (m.get("description") or "").strip()
        if not desc:
            missing_desc += 1

        cat = (m.get("category") or "").strip()
        if not cat or cat.upper() in ("GENERAL", "UNCATEGORISED", "UNKNOWN"):
            missing_cat += 1

        parsed = m.get("parsed_specifications") or {}
        if parsed and any(v is not None for v in parsed.values()):
            with_parsed_specs += 1
            cpse_stats[cpse]["with_parsed_specs"] += 1
        else:
            parsing_failures += 1

        grade = m.get("material_grade") or parsed.get("material_grade")
        if not grade:
            missing_grade += 1
            cpse_stats[cpse]["missing_grade"] += 1

        dim = m.get("dimensions") or parsed.get("dimensions") or parsed.get("nominal_bore") or parsed.get("dimension_tokens")
        if not dim:
            missing_dim += 1
            cpse_stats[cpse]["missing_dimensions"] += 1

        pressure = parsed.get("pressure_rating")
        if not pressure:
            missing_pressure += 1
            cpse_stats[cpse]["missing_pressure"] += 1

    desc_rate = (total - missing_desc) / total
    cat_rate = (total - missing_cat) / total
    parsed_rate = with_parsed_specs / total
    grade_rate = (total - missing_grade) / total
    completeness_score = round(
        (desc_rate * 0.3 + cat_rate * 0.2 + parsed_rate * 0.3 + grade_rate * 0.2), 4
    )

    by_cpse_quality = [
        {
            "cpse": c,
            "total_materials": s["total"],
            "with_parsed_specs": s["with_parsed_specs"],
            "parsed_specs_rate": round(s["with_parsed_specs"] / s["total"], 4) if s["total"] else 0.0,
            "missing_grade": s["missing_grade"],
            "missing_dimensions": s["missing_dimensions"],
            "missing_pressure": s["missing_pressure"],
        }
        for c, s in sorted(cpse_stats.items())
    ]

    return {
        "total_materials": total,
        "with_parsed_specs": with_parsed_specs,
        "parsed_specs_rate": round(with_parsed_specs / total, 4),
        "missing_description": missing_desc,
        "missing_category": missing_cat,
        "missing_material_grade": missing_grade,
        "missing_dimensions": missing_dim,
        "missing_pressure_rating": missing_pressure,
        "parsing_failures": parsing_failures,
        "completeness_score": completeness_score,
        "by_cpse_quality": by_cpse_quality,
    }
