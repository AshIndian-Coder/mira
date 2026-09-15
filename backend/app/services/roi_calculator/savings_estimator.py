"""Procurement & inventory savings estimation (ROI calculator).

Model
-----
For every duplicate group (a CNMC with 2+ mapped materials, or a pending
high-confidence cluster) we compare:

  Individual spend   = sum over members of (price_i x annual_qty_i)
  Consolidated spend = total_qty x min_price x (1 - BULK_DISCOUNT_RATE)

    procurement_savings = individual_spend - consolidated_spend

Inventory side: redundant SKUs keep ~SAFETY_STOCK_DAYS of stock each.
Redundant inventory value (all members except the cheapest) times the
annual CARRYING_COST_RATE gives the inventory holding savings.

The pure core (``estimate_savings_from_clusters``) is DB-free and fully
unit-testable; ``estimate_savings`` is the DB wrapper used by the API.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.config import settings
from app.core.logger import get_logger
from app.models.cnmc import CNMC
from app.models.mapping import Mapping
from app.models.material import Material
from app.utils.constants import MAPPING_STATUS_ACTIVE
from app.utils.helpers import format_inr, to_float

logger = get_logger("mira.roi")


def estimate_savings_from_clusters(
    clusters: Sequence[Dict[str, Any]],
    bulk_discount_rate: float = None,
    carrying_cost_rate: float = None,
    safety_stock_days: int = None,
) -> Dict[str, Any]:
    """Compute savings for duplicate clusters (pure function, no DB).

    Each cluster dict:
        {
          "name": str|None,               # CNMC code or label
          "materials": [
              {"price": float|None, "quantity": float|None}, ...  # >= 2
          ]
        }
    """
    bulk = settings.BULK_DISCOUNT_RATE if bulk_discount_rate is None else bulk_discount_rate
    carrying = settings.CARRYING_COST_RATE if carrying_cost_rate is None else carrying_cost_rate
    days = settings.SAFETY_STOCK_DAYS if safety_stock_days is None else safety_stock_days

    cluster_results: List[Dict[str, Any]] = []
    totals = {
        "procurement_savings": 0.0,
        "inventory_savings": 0.0,
        "sku_reduction": 0,
        "annual_spend_before": 0.0,
        "annual_spend_after": 0.0,
    }

    for cluster in clusters:
        members = [m for m in cluster.get("materials", []) if m]
        if len(members) < 2:
            continue

        priced = [
            (to_float(m.get("price")), to_float(m.get("quantity")))
            for m in members
        ]
        priced = [(p, q) for p, q in priced if p > 0 and q > 0]
        if len(priced) < 2:
            continue

        spend_before = sum(p * q for p, q in priced)
        total_qty = sum(q for _, q in priced)
        min_price = min(p for p, _ in priced)
        spend_after = total_qty * min_price * (1.0 - bulk)
        procurement_savings = max(0.0, spend_before - spend_after)

        # Redundant stock value: everything above the consolidated position
        # (keep only the cheapest member's stock at the aggregated volume).
        cheapest_qty = min((q for p, q in priced if p == min_price), default=0.0)
        redundant_value = max(
            0.0, sum(p * q for p, q in priced) - min_price * (total_qty - cheapest_qty)
        )
        inventory_savings = redundant_value * (days / 365.0) * carrying

        sku_reduction = len(priced) - 1

        cluster_results.append(
            {
                "name": cluster.get("name"),
                "member_count": len(members),
                "sku_reduction": sku_reduction,
                "annual_spend_before": round(spend_before, 2),
                "annual_spend_after": round(spend_after, 2),
                "procurement_savings": round(procurement_savings, 2),
                "inventory_savings": round(inventory_savings, 2),
                "total_savings": round(procurement_savings + inventory_savings, 2),
            }
        )
        totals["procurement_savings"] += procurement_savings
        totals["inventory_savings"] += inventory_savings
        totals["sku_reduction"] += sku_reduction
        totals["annual_spend_before"] += spend_before
        totals["annual_spend_after"] += spend_after

    total_savings = totals["procurement_savings"] + totals["inventory_savings"]
    result = {
        "mode": "approved_mappings" if any(c.get("name", "").startswith("CNMC") for c in cluster_results) else "potential",
        "cluster_count": len(cluster_results),
        "clusters": cluster_results,
        "totals": {
            "procurement_savings": round(totals["procurement_savings"], 2),
            "procurement_savings_inr": format_inr(totals["procurement_savings"]),
            "inventory_savings": round(totals["inventory_savings"], 2),
            "inventory_savings_inr": format_inr(totals["inventory_savings"]),
            "total_savings": round(total_savings, 2),
            "total_savings_inr": format_inr(total_savings),
            "sku_reduction": totals["sku_reduction"],
            "annual_spend_before": round(totals["annual_spend_before"], 2),
            "annual_spend_after": round(totals["annual_spend_after"], 2),
            "savings_percent_of_spend": (
                round(100.0 * total_savings / totals["annual_spend_before"], 2)
                if totals["annual_spend_before"] > 0
                else 0.0
            ),
        },
        "assumptions": {
            "bulk_discount_rate": bulk,
            "carrying_cost_rate": carrying,
            "safety_stock_days": days,
            "currency": "INR",
        },
    }
    return result


def _clusters_from_mappings(session: Session, category: Optional[str]) -> List[Dict[str, Any]]:
    """Build cluster inputs from active mappings (approved duplicates)."""
    query = (
        session.query(Mapping)
        .filter(Mapping.status == MAPPING_STATUS_ACTIVE)
        .join(CNMC, Mapping.cnmc_id == CNMC.id)
    )
    if category:
        query = query.filter(CNMC.category == category)
    mappings = query.all()

    by_cnmc: Dict[int, List[Mapping]] = {}
    for mapping in mappings:
        by_cnmc.setdefault(mapping.cnmc_id, []).append(mapping)

    clusters: List[Dict[str, Any]] = []
    for cnmc_id, group in by_cnmc.items():
        if len(group) < 2:
            continue
        material_ids = [g.material_id for g in group]
        materials = (
            session.query(Material).filter(Material.id.in_(material_ids)).all()
        )
        clusters.append(
            {
                "name": session.query(CNMC).filter(CNMC.id == cnmc_id).first().cnmc_code,
                "materials": [
                    {
                        "price": float(m.last_purchase_price)
                        if m.last_purchase_price is not None
                        else None,
                        "quantity": float(m.avg_annual_quantity)
                        if m.avg_annual_quantity is not None
                        else None,
                        "material_id": m.id,
                        "material_code": m.material_code,
                        "cpse_id": m.cpse_id,
                    }
                    for m in materials
                ],
            }
        )
    return clusters


def _clusters_from_suggestions(session: Session, category: Optional[str]) -> List[Dict[str, Any]]:
    """Fallback: pending high-confidence suggestions (potential savings)."""
    from app.models.match_suggestion import MatchSuggestion

    query = (
        session.query(MatchSuggestion)
        .filter(
            MatchSuggestion.status == "pending",
            MatchSuggestion.final_confidence >= Decimal("85.00"),
        )
        .order_by(MatchSuggestion.final_confidence.desc())
    )
    suggestions = query.all()

    # Simple pair-based clusters (one entry per accepted pair).
    clusters: List[Dict[str, Any]] = []
    seen = set()
    for suggestion in suggestions:
        key = (suggestion.material_1_id, suggestion.material_2_id)
        if key in seen:
            continue
        seen.add(key)
        materials = (
            session.query(Material)
            .filter(Material.id.in_([suggestion.material_1_id, suggestion.material_2_id]))
            .all()
        )
        if category and not all(
            (m.category or "").upper() == category.upper() for m in materials
        ):
            continue
        clusters.append(
            {
                "name": f"pending_pair_{suggestion.id}",
                "materials": [
                    {
                        "price": float(m.last_purchase_price)
                        if m.last_purchase_price is not None
                        else None,
                        "quantity": float(m.avg_annual_quantity)
                        if m.avg_annual_quantity is not None
                        else None,
                        "material_id": m.id,
                        "material_code": m.material_code,
                        "cpse_id": m.cpse_id,
                    }
                    for m in materials
                ],
            }
        )
    return clusters


def estimate_savings(
    session: Session,
    cpse_ids: Optional[Sequence[int]] = None,
    category: Optional[str] = None,
    mode: str = "approved",
) -> Dict[str, Any]:
    """DB wrapper for the API layer.

    mode="approved"  -> savings from approved mappings (realized path)
    mode="potential" -> includes pending high-confidence suggestions
    """
    if mode == "potential":
        clusters = _clusters_from_suggestions(session, category)
        if not clusters:
            clusters = _clusters_from_mappings(session, category)
    else:
        clusters = _clusters_from_mappings(session, category)

    if cpse_ids:
        allowed = {int(cid) for cid in cpse_ids}
        for cluster in clusters:
            cluster["materials"] = [
                m for m in cluster.get("materials", []) if m.get("cpse_id") in allowed
            ]
        clusters = [c for c in clusters if len(c.get("materials", [])) >= 2]

    result = estimate_savings_from_clusters(clusters)
    result["filters"] = {
        "cpse_ids": [int(c) for c in cpse_ids] if cpse_ids else None,
        "category": category,
        "mode": mode,
    }
    logger.info(
        "ROI estimated: %d clusters, total savings %.2f INR",
        result["cluster_count"],
        result["totals"]["total_savings"],
    )
    return result

