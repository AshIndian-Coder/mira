"""Dashboard & analytics endpoints (OverviewDashboard page).

    GET /api/v1/dashboard/stats              Headline numbers
    GET /api/v1/dashboard/trends             Duplicates found over time
    GET /api/v1/dashboard/category-heatmap   Duplicate distribution by category
    GET /api/v1/dashboard/cpse-comparison    Cross-CPSE analytics
"""
from __future__ import annotations

from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, desc, func
from sqlalchemy.orm import Session

from app.core.security import get_current_active_user
from app.db.postgres import get_db
from app.models.cnmc import CNMC
from app.models.cpse import Cpse
from app.models.mapping import Mapping
from app.models.match_suggestion import MatchSuggestion
from app.models.material import Material
from app.models.user import User
from app.utils.constants import MAPPING_STATUS_ACTIVE, SUGGESTION_STATUS_APPROVED, SUGGESTION_STATUS_PENDING, SUGGESTION_STATUS_REJECTED
from app.utils.helpers import utcnow

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
def stats(db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    """Overall system stats for the headline StatCards."""
    total_materials = db.query(func.count(Material.id)).filter(Material.status == "active").scalar() or 0
    total_cpse = db.query(func.count(Cpse.id)).filter(Cpse.is_active == True).scalar() or 0  # noqa: E712
    total_cnmc = db.query(func.count(CNMC.id)).scalar() or 0
    total_mappings = db.query(func.count(Mapping.id)).filter(Mapping.status == MAPPING_STATUS_ACTIVE).scalar() or 0

    pending = db.query(func.count(MatchSuggestion.id)).filter(MatchSuggestion.status == SUGGESTION_STATUS_PENDING).scalar() or 0
    approved = db.query(func.count(MatchSuggestion.id)).filter(MatchSuggestion.status == SUGGESTION_STATUS_APPROVED).scalar() or 0
    rejected = db.query(func.count(MatchSuggestion.id)).filter(MatchSuggestion.status == SUGGESTION_STATUS_REJECTED).scalar() or 0

    high_confidence = (
        db.query(func.count(MatchSuggestion.id))
        .filter(
            MatchSuggestion.status == SUGGESTION_STATUS_PENDING,
            MatchSuggestion.final_confidence >= 85.0,
        )
        .scalar()
        or 0
    )

    # Duplicate groups = CNMCs with 2+ active mappings
    sub = (
        db.query(Mapping.cnmc_id)
        .filter(Mapping.status == MAPPING_STATUS_ACTIVE)
        .group_by(Mapping.cnmc_id)
        .having(func.count(Mapping.id) >= 2)
        .subquery()
    )
    duplicate_groups = db.query(func.count(sub.c.cnmc_id)).select_from(sub).scalar() or 0

    avg_quality = (
        db.query(func.avg(Material.data_quality_score))
        .filter(Material.status == "active", Material.data_quality_score.isnot(None))
        .scalar()
        or 0
    )

    return {
        "total_materials": int(total_materials),
        "total_cpse": int(total_cpse),
        "total_cnmc": int(total_cnmc),
        "total_mappings": int(total_mappings),
        "pending_matches": int(pending),
        "approved_matches": int(approved),
        "rejected_matches": int(rejected),
        "high_confidence_pending": int(high_confidence),
        "duplicate_groups": int(duplicate_groups),
        "avg_data_quality": round(float(avg_quality), 1),
        "generated_at": utcnow().isoformat(),
    }


@router.get("/trends")
def trends(
    days: int = Query(default=30, ge=7, le=365),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Daily duplicates-found trend (DuplicateTrendChart page)."""
    since = utcnow() - timedelta(days=days)
    rows = (
        db.query(
            func.date(MatchSuggestion.created_at).label("day"),
            MatchSuggestion.status,
            func.count(MatchSuggestion.id),
        )
        .filter(MatchSuggestion.created_at >= since)
        .group_by(func.date(MatchSuggestion.created_at), MatchSuggestion.status)
        .order_by(func.date(MatchSuggestion.created_at))
        .all()
    )
    by_day: dict = {}
    for day, status, count in rows:
        entry = by_day.setdefault(
            day.isoformat() if hasattr(day, "isoformat") else str(day),
            {"date": str(day), "created": 0, "approved": 0, "rejected": 0},
        )
        entry[status] = entry.get(status, 0) + int(count)
    return {"days": days, "series": list(by_day.values())}


@router.get("/category-heatmap")
def category_heatmap(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Materials + duplicate pairs per category (CategoryHeatmap page)."""
    material_counts = (
        db.query(Material.category, func.count(Material.id))
        .filter(Material.status == "active", Material.category.isnot(None))
        .group_by(Material.category)
        .all()
    )
    duplicate_pairs = (
        db.query(MatchSuggestion.status, func.count(MatchSuggestion.id))
        .group_by(MatchSuggestion.status)
        .all()
    )
    status_totals = {status: int(count) for status, count in duplicate_pairs}

    # pairs per category (via material_1's category as proxy)
    per_category = (
        db.query(Material.category, func.count(MatchSuggestion.id))
        .join(MatchSuggestion, MatchSuggestion.material_1_id == Material.id)
        .filter(Material.category.isnot(None))
        .group_by(Material.category)
        .all()
    )
    pair_by_category = {category: int(count) for category, count in per_category if category}

    items = []
    for category, count in material_counts:
        items.append(
            {
                "category": category,
                "materials": int(count),
                "duplicate_pairs": pair_by_category.get(category, 0),
            }
        )
    items.sort(key=lambda item: item["duplicate_pairs"], reverse=True)
    return {"items": items, "totals": status_totals}


@router.get("/cpse-comparison")
def cpse_comparison(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Cross-CPSE analytics (table on the dashboard)."""
    cpses = db.query(Cpse).filter(Cpse.is_active == True).order_by(Cpse.short_code).all()  # noqa: E712
    rows = []
    for cpse in cpses:
        materials = db.query(func.count(Material.id)).filter(
            Material.cpse_id == cpse.id, Material.status == "active"
        ).scalar() or 0
        mapped = (
            db.query(func.count(Mapping.id))
            .join(Material)
            .filter(Material.cpse_id == cpse.id, Mapping.status == MAPPING_STATUS_ACTIVE)
            .scalar()
            or 0
        )
        pending = (
            db.query(func.count(MatchSuggestion.id))
            .join(Material, (MatchSuggestion.material_1_id == Material.id) | (MatchSuggestion.material_2_id == Material.id))
            .filter(Material.cpse_id == cpse.id, MatchSuggestion.status == SUGGESTION_STATUS_PENDING)
            .scalar()
            or 0
        )
        avg_quality = (
            db.query(func.avg(Material.data_quality_score))
            .filter(Material.cpse_id == cpse.id, Material.data_quality_score.isnot(None))
            .scalar()
            or 0
        )
        rows.append(
            {
                "cpse_id": cpse.id,
                "name": cpse.name,
                "short_code": cpse.short_code,
                "materials": int(materials),
                "mapped": int(mapped),
                "pending_matches": int(pending),
                "avg_data_quality": round(float(avg_quality), 1),
                "last_sync_at": cpse.last_sync_at.isoformat() if cpse.last_sync_at else None,
                "last_sync_status": cpse.last_sync_status,
            }
        )
    return {"items": rows}

