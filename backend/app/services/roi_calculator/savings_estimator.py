from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.cnmc import CNMC
from app.models.mapping import Mapping
from app.models.match_suggestion import MatchSuggestion
from app.models.material import Material
from app.utils.constants import MAPPING_STATUS_ACTIVE, SUGGESTION_STATUS_APPROVED, SUGGESTION_STATUS_PENDING
from app.utils.helpers import to_decimal, to_float

logger = logging.getLogger("mira.roi")


def estimate_savings(
    db: Session,
    cpse_ids: Optional[List[int]] = None,
    category: Optional[str] = None,
    mode: str = "approved",
) -> Dict[str, Any]:
    """Estimate savings from duplicate material consolidation.

    Args:
        db: Database session
        cpse_ids: Filter by CPSE IDs (comma-separated in API)
        category: Filter by category
        mode: "approved" for realized savings, "potential" for includes pending

    Returns:
        Dictionary with savings estimates and cluster details
    """
    clusters = _get_clusters(db, cpse_ids=cpse_ids, category=category, mode=mode)

    cluster_savings = []
    total_savings = Decimal("0")
    total_savings_inr = Decimal("0")
    total_sku_reduction = 0

    for cluster in clusters:
        savings = _calculate_cluster_savings(cluster)
        if savings["total_savings"] > 0:
            cluster_savings.append(savings)
            total_savings += savings["total_savings"]
            total_savings_inr += savings["total_savings_inr"]
            total_sku_reduction += savings["sku_reduction"]

    return {
        "totals": {
            "total_savings": float(total_savings),
            "total_savings_inr": float(total_savings_inr),
            "sku_reduction": total_sku_reduction,
        },
        "cluster_count": len(cluster_savings),
        "clusters": cluster_savings,
    }


def _get_clusters(
    db: Session,
    cpse_ids: Optional[List[int]] = None,
    category: Optional[str] = None,
    mode: str = "approved",
) -> List[Dict[str, Any]]:
    """Get clusters (CNMCs with 2+ materials) for savings estimation."""
    subquery = (
        db.query(Mapping.cnmc_id)
        .join(Material, Mapping.material_id == Material.id)
        .filter(Mapping.status == MAPPING_STATUS_ACTIVE)
        .filter(Material.status == "active")
    )

    if cpse_ids:
        subquery = subquery.filter(Material.cpse_id.in_(cpse_ids))

    if category:
        subquery = subquery.filter(Material.category == category)

    subquery = subquery.group_by(Mapping.cnmc_id).having(__import__("sqlalchemy").func.count(Mapping.id) >= 2)
    cnmc_ids = [row[0] for row in subquery.all()]

    if not cnmc_ids:
        return []

    cNickmps = (
        db.query(CNMC)
        .filter(CNMC.id.in_(cnmc_ids))
        .all()
    )

    clusters = []
    for cnmc in cNickmps:
        mappings = (
            db.query(Mapping)
            .join(Material, Mapping.material_id == Material.id)
            .filter(Mapping.cnmc_id == cnmc.id)
            .filter(Mapping.status == MAPPING_STATUS_ACTIVE)
            .filter(Material.status == "active")
        )

        if cpse_ids:
            mappings = mappings.filter(Material.cpse_id.in_(cpse_ids))

        if category:
            mappings = mappings.filter(Material.category == category)

        mappings = mappings.all()

        if len(mappings) < 2:
            continue

        materials = [mapping.material for mapping in mappings if mapping.material]

        if len(materials) < 2:
            continue

        if mode == "potential":
            pending_suggestions = (
                db.query(MatchSuggestion)
                .filter(MatchSuggestion.status == SUGGESTION_STATUS_PENDING)
                .filter(MatchSuggestion.final_confidence >= 0.85)
            )

            cnmc_cpses = set(m.cpse_id for m in materials if m.cpse_id)
            if cnmc_cpses:
                pending_suggestions = pending_suggestions.filter(
                    __import__("sqlalchemy").or_(
                        MatchSuggestion.material_1.has(Material.cpse_id.in_(cnmc_cpses)),
                        MatchSuggestion.material_2.has(Material.cpse_id.in_(cnmc_cpses)),
                    )
                )

            pending_suggestions = pending_suggestions.all()

            for suggestion in pending_suggestions:
                m1 = suggestion.material_1
                m2 = suggestion.material_2
                if m1 and m1 not in materials and m1.status == "active":
                    materials.append(m1)
                if m2 and m2 not in materials and m2.status == "active":
                    materials.append(m2)

        cluster = {
            "cnmc_id": cnmc.id,
            "cnmc_code": cnmc.cnmc_code,
            "standardized_description": cnmc.standardized_description,
            "category": cnmc.category,
            "materials": [
                {
                    "id": m.id,
                    "cpse_id": m.cpse_id,
                    "material_code": m.material_code,
                    "description": m.description,
                    "last_purchase_price": to_decimal(m.last_purchase_price),
                    "avg_annual_quantity": to_decimal(m.avg_annual_quantity),
                }
                for m in materials
            ],
            "material_count": len(materials),
        }
        clusters.append(cluster)

    return clusters


def _calculate_cluster_savings(cluster: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate savings for a single cluster."""
    materials = cluster.get("materials", [])
    if len(materials) < 2:
        return {
            "cnmc_code": cluster.get("cnmc_code"),
            "category": cluster.get("category"),
            "material_count": len(materials),
            "total_savings": Decimal("0"),
            "total_savings_inr": Decimal("0"),
            "sku_reduction": 0,
            "details": [],
        }

    details = []
    total_savings = Decimal("0")
    total_savings_inr = Decimal("0")
    total_annual_spend = Decimal("0")
    total_quantity = Decimal("0")

    for material in materials:
        price = material.get("last_purchase_price") or Decimal("0")
        quantity = material.get("avg_annual_quantity") or Decimal("0")

        annual_spend = price * quantity
        total_annual_spend += annual_spend
        total_quantity += quantity

        detail = {
            "material_id": material.get("id"),
            "material_code": material.get("material_code"),
            "description": material.get("description"),
            "annual_spend": float(annual_spend),
            "annual_spend_inr": float(annual_spend),
            "price": float(price) if price else 0,
            "quantity": float(quantity) if quantity else 0,
        }
        details.append(detail)

    bulk_discount_rate = Decimal(str(settings.BULK_DISCOUNT_RATE))
    bulk_savings = total_annual_spend * bulk_discount_rate

    safety_stock_days = settings.SAFETY_STOCK_DAYS
    carrying_cost_rate = Decimal(str(settings.CARRYING_COST_RATE))

    if len(materials) > 1:
        avg_annual_spend = total_annual_spend / len(materials)
        avg_daily_spend = avg_annual_spend / Decimal("365")
        safety_stock_value = avg_daily_spend * Decimal(str(safety_stock_days))
        sku_reduction = len(materials) - 1
        carrying_savings = safety_stock_value * sku_reduction * carrying_cost_rate
    else:
        sku_reduction = 0
        carrying_savings = Decimal("0")

    procurement_savings = total_annual_spend * Decimal("0.02") * sku_reduction

    total_cluster_savings = bulk_savings + carrying_savings + procurement_savings

    return {
        "cnmc_code": cluster.get("cnmc_code"),
        "category": cluster.get("category"),
        "material_count": len(materials),
        "total_savings": total_cluster_savings,
        "total_savings_inr": total_cluster_savings,
        "sku_reduction": sku_reduction,
        "details": details,
        "breakdown": {
            "bulk_discount_savings": float(bulk_savings),
            "carrying_cost_savings": float(carrying_savings),
            "procurement_overhead_savings": float(procurement_savings),
            "bulk_discount_rate": settings.BULK_DISCOUNT_RATE,
            "carrying_cost_rate": settings.CARRYING_COST_RATE,
            "safety_stock_days": settings.SAFETY_STOCK_DAYS,
        },
    }


def estimate_savings_from_clusters(clusters: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Estimate savings from pre-built cluster data (without DB access)."""
    total_savings = Decimal("0")
    total_savings_inr = Decimal("0")
    total_sku_reduction = 0
    cluster_count = 0
    details = []

    for cluster in clusters:
        materials = cluster.get("materials", [])
        if len(materials) < 2:
            continue

        cluster_savings = Decimal("0")
        cluster_quantity = Decimal("0")
        cluster_details = []

        for material in materials:
            price = to_decimal(material.get("last_purchase_price")) or Decimal("0")
            quantity = to_decimal(material.get("avg_annual_quantity")) or Decimal("0")
            annual_spend = price * quantity
            cluster_savings += annual_spend
            cluster_quantity += quantity

            cluster_details.append({
                "material_id": material.get("id"),
                "material_code": material.get("material_code"),
                "description": material.get("description"),
                "annual_spend": float(annual_spend),
            })

        bulk_discount_rate = Decimal(str(settings.BULK_DISCOUNT_RATE))
        bulk_savings = cluster_savings * bulk_discount_rate

        if len(materials) > 1:
            sku_reduction = len(materials) - 1
            avg_annual_spend = cluster_savings / len(materials)
            avg_daily_spend = avg_annual_spend / Decimal("365")
            safety_stock_value = avg_daily_spend * Decimal(str(settings.SAFETY_STOCK_DAYS))
            carrying_cost_rate = Decimal(str(settings.CARRYING_COST_RATE))
            carrying_savings = safety_stock_value * sku_reduction * carrying_cost_rate
            procurement_savings = cluster_savings * Decimal("0.02") * sku_reduction
        else:
            sku_reduction = 0
            carrying_savings = Decimal("0")
            procurement_savings = Decimal("0")

        cluster_total = bulk_savings + carrying_savings + procurement_savings
        total_savings += cluster_total
        total_savings_inr += cluster_total
        total_sku_reduction += sku_reduction
        cluster_count += 1

        details.append({
            "cnmc_code": cluster.get("cnmc_code"),
            "category": cluster.get("category"),
            "material_count": len(materials),
            "total_savings": float(cluster_total),
            "sku_reduction": sku_reduction,
            "breakdown": {
                "bulk_discount_savings": float(bulk_savings),
                "carrying_cost_savings": float(carrying_savings),
                "procurement_overhead_savings": float(procurement_savings),
            },
            "materials": cluster_details,
        })

    return {
        "totals": {
            "total_savings": float(total_savings),
            "total_savings_inr": float(total_savings_inr),
            "sku_reduction": total_sku_reduction,
        },
        "cluster_count": cluster_count,
        "clusters": details,
    }
