"""CNMC code generation (CNMC-000001, CNMC-000002, ...).

Guarantees uniqueness by deriving the next sequence number from the
highest existing ``cnmc.id`` (flush-safe). Also builds the standardized
description + merged technical specs for a duplicate cluster.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.models.cnmc import CNMC
from app.services.cnmc_generator.taxonomy_mapper import map_to_taxonomy
from app.utils.constants import MAPPING_STATUS_ACTIVE, MAPPING_TYPE_MANUAL
from app.utils.helpers import group_count, utcnow

logger = get_logger("mira.cnmc")

_CODE_PREFIX = "CNMC-"


def next_code_for(max_id: int) -> str:
    """Pure helper: next CNMC code string for a given max id (testable)."""
    return f"{_CODE_PREFIX}{max(0, int(max_id) or 0) + 1:06d}"


def generate_cnmc_code(session: Session) -> str:
    """Allocate the next unique CNMC code (call inside an open transaction)."""
    from sqlalchemy import func

    current_max = session.query(func.max(CNMC.id)).scalar() or 0
    return next_code_for(int(current_max))


def _pick_representative_description(materials: List[Dict[str, Any]]) -> str:
    """Longest cleaned description wins (most informative variant)."""

    def _text(m: Dict[str, Any]) -> str:
        return m.get("cleaned_description") or m.get("description") or ""

    representative = max(materials, key=_text)
    return representative.get("cleaned_description") or representative.get("description") or ""


def _merge_attributes(materials: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Most-frequent non-None value per attribute key."""
    merged: Dict[str, Any] = {}
    keys: List[str] = []
    for m in materials:
        attrs = m.get("attributes") or {}
        for key, value in attrs.items():
            if key not in keys:
                keys.append(key)
            if value is not None:
                merged.setdefault(key, []).append(str(value).upper())
    result: Dict[str, Any] = {}
    for key in keys:
        values = merged.get(key) or []
        if values:
            result[key] = group_count(values).most_common(1)[0][0]
    return result


def create_cnmc_for_cluster(
    session: Session,
    materials: List[Dict[str, Any]],
    approved_by: Optional[int] = None,
    mapping_type: str = MAPPING_TYPE_MANUAL,
    commit: bool = True,
) -> CNMC:
    """Create a CNMC for a duplicate cluster and map all members to it.

    ``materials``: list of dicts with keys id, cpse_id, category,
    cleaned_description/description, attributes.
    """
    from app.models.mapping import Mapping

    if not materials:
        raise ValueError("At least one material is required to create a CNMC")

    category_values = [m.get("category") for m in materials if m.get("category")]
    category = group_count(category_values).most_common(1)[0][0] if category_values else None
    description = _pick_representative_description(materials)
    taxonomy = map_to_taxonomy(category)
    technical_specs = _merge_attributes(materials)

    cnmc = CNMC(
        cnmc_code=generate_cnmc_code(session),
        standardized_description=description,
        category=category,
        unspsc_code=taxonomy.get("unspsc_code"),
        nic_code=taxonomy.get("nic_code"),
        technical_specs=technical_specs,
        approved_by=approved_by,
        approved_at=utcnow() if approved_by else None,
    )
    session.add(cnmc)
    session.flush()  # assign cnmc.id

    # Map every cluster member that has no active mapping yet.
    for m in materials:
        existing = (
            session.query(Mapping)
            .filter(
                Mapping.material_id == m["id"],
                Mapping.status == MAPPING_STATUS_ACTIVE,
            )
            .first()
        )
        if existing is None:
            session.add(
                Mapping(
                    material_id=int(m["id"]),
                    cnmc_id=cnmc.id,
                    confidence_score=100.0,
                    mapping_type=mapping_type,
                    approved_by=approved_by,
                    approved_at=utcnow() if approved_by else None,
                    status=MAPPING_STATUS_ACTIVE,
                )
            )
    session.flush()  # make mappings visible to relationship loads pre-commit

    if commit:
        session.commit()
        session.refresh(cnmc)
    logger.info("Created CNMC %s for cluster of %d materials", cnmc.cnmc_code, len(materials))
    return cnmc

