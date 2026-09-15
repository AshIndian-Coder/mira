"""ROI calculator endpoints (SavingsCalculator page).

    GET /api/v1/roi/savings       Savings estimate (filters + mode)
    GET /api/v1/roi/summary       Headline numbers for the savings card
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_active_user
from app.db.postgres import get_db
from app.models.user import User
from app.services.roi_calculator.savings_estimator import estimate_savings

router = APIRouter(prefix="/roi", tags=["roi"])


def _parse_cpse_ids(raw: Optional[str]) -> Optional[List[int]]:
    if not raw:
        return None
    try:
        return [int(part) for part in raw.split(",") if part.strip()]
    except ValueError:
        return None


@router.get("/savings")
def savings(
    cpse_ids: Optional[str] = Query(
        default=None, description="Comma separated CPSE ids, e.g. '1,2,3'"
    ),
    category: Optional[str] = Query(default=None, description="Category filter, e.g. 'Bearing'"),
    mode: str = Query(
        default="approved",
        pattern="^(approved|potential)$",
        description="approved = realized via mappings; potential = includes pending high-confidence pairs",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Procurement + inventory savings for merged duplicate groups."""
    return estimate_savings(
        db,
        cpse_ids=_parse_cpse_ids(cpse_ids),
        category=category,
        mode=mode,
    )


@router.get("/summary")
def summary(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Quick headline (SavingsCard): realized + potential totals."""
    approved = estimate_savings(db, mode="approved")
    potential = estimate_savings(db, mode="potential")
    return {
        "realized": {
            "total_savings": approved["totals"]["total_savings"],
            "total_savings_inr": approved["totals"]["total_savings_inr"],
            "cluster_count": approved["cluster_count"],
            "sku_reduction": approved["totals"]["sku_reduction"],
        },
        "potential": {
            "total_savings": potential["totals"]["total_savings"],
            "total_savings_inr": potential["totals"]["total_savings_inr"],
            "cluster_count": potential["cluster_count"],
        },
    }
