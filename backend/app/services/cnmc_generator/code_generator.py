"""
CNMC (Common National Material Code) generation logic.
Generates unique CNMC codes for material clusters and creates the
corresponding CNMC + mapping records in the database.
CNMC code format: CNMC-XXXXXX (6-digit zero-padded sequential number)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.cnmc import CNMC
from app.models.mapping import Mapping
from app.models.user import User
from app.utils.constants import MAPPING_STATUS_ACTIVE, MAPPING_TYPE_AI_SUGGESTED
from app.utils.helpers import utcnow


class CNMCGenerator:
    """Generates CNMC codes and creates CNMC + mapping records."""

    def __init__(self, session: Optional[Session] = None):
        self.session = session

    def _get_session(self) -> Session:
        if self.session:
            return self.session
        from app.db.postgres import SessionLocal
        return SessionLocal()

    def generate_code(self) -> str:
        """Generate the next available CNMC code."""
        session = self._get_session()
        try:
            last_cnmc = session.query(CNMC).order_by(CNMC.id.desc()).first()
            if last_cnmc and last_cnmc.cnmc_code:
                try:
                    last_num = int(last_cnmc.cnmc_code.split("-")[1])
                    next_num = last_num + 1
                except (ValueError, IndexError):
                    next_num = 1
            else:
                next_num = 1

            return f"CNMC-{next_num:06d}"
        finally:
            if not self.session:
                session.close()

    def generate_from_cluster(
        self,
        cluster: Dict[str, Any],
        approved_by: Optional[int] = None,
        mapping_type: str = MAPPING_TYPE_AI_SUGGESTED,
        commit: bool = True,
    ) -> CNMC:
        """Generate a CNMC for a cluster of materials."""
        session = self._get_session()
        try:
            cnmc_code = self.generate_code()

            categories = cluster.get("categories", [])
            category = categories[0] if categories else None

            standardized_desc = self._generate_standardized_description(cluster)

            cnmc = CNMC(
                cnmc_code=cnmc_code,
                standardized_description=standardized_desc,
                category=category,
                created_at=utcnow(),
                approved_by=approved_by,
                approved_at=utcnow() if approved_by else None,
            )
            session.add(cnmc)
            session.flush()  # Get the CNMC ID

            mapping_ids = []
            for material in cluster.get("materials", []):
                material_id = material.get("id")
                if material_id:
                    mapping = Mapping(
                        material_id=material_id,
                        cnmc_id=cnmc.id,
                        confidence_score=100.0,
                        mapping_type=mapping_type,
                        approved_by=approved_by,
                        approved_at=utcnow() if approved_by else None,
                        status=MAPPING_STATUS_ACTIVE,
                    )
                    session.add(mapping)
                    session.flush()
                    mapping_ids.append(mapping.id)

            if commit:
                session.commit()

            cnmc.mappings = session.query(Mapping).filter(Mapping.cnmc_id == cnmc.id).all()

            return cnmc
        finally:
            if not self.session:
                session.close()

    def _generate_standardized_description(self, cluster: Dict[str, Any]) -> str:
        """Generate a standardized description from cluster materials."""
        materials = cluster.get("materials", [])
        if not materials:
            return "Unnamed Material Cluster"

        descriptions = [m.get("cleaned_description") or m.get("description") for m in materials if m]
        descriptions = [d for d in descriptions if d]

        if not descriptions:
            return "Unnamed Material Cluster"

        return descriptions[0]

    def create_cnmc_for_cluster(
        self,
        session: Session,
        material_dicts: List[Dict[str, Any]],
        approved_by: Optional[int] = None,
        mapping_type: str = MAPPING_TYPE_AI_SUGGESTED,
        commit: bool = False,
    ) -> CNMC:
        """Create a CNMC for a set of materials (used by review workflow)."""
        cluster = {
            "cluster_id": f"manual-{uuid.uuid4().hex[:8]}",
            "material_ids": [m.get("id") for m in material_dicts if m.get("id")],
            "materials": material_dicts,
            "size": len(material_dicts),
            "categories": list(set(m.get("category") for m in material_dicts if m.get("category"))),
            "cnmc_code": None,
            "cnmc_id": None,
        }

        return self.generate_from_cluster(
            cluster,
            approved_by=approved_by,
            mapping_type=mapping_type,
            commit=commit,
        )

    def generate_from_clusters(
        self,
        clusters: Dict[str, Dict[str, Any]],
        approved_by: Optional[int] = None,
        mapping_type: str = MAPPING_TYPE_AI_SUGGESTED,
        commit: bool = True,
    ) -> List[str]:
        """Generate CNMC codes for multiple clusters."""
        codes = []
        for cluster_id, cluster in clusters.items():
            if cluster.get("cnmc_code"):
                codes.append(cluster["cnmc_code"])
                continue

            try:
                cnmc = self.generate_from_cluster(
                    cluster,
                    approved_by=approved_by,
                    mapping_type=mapping_type,
                    commit=commit,
                )
                cluster["cnmc_code"] = cnmc.cnmc_code
                cluster["cnmc_id"] = cnmc.id
                codes.append(cnmc.cnmc_code)
            except Exception as e:
                print(f"Error generating CNMC for cluster {cluster_id}: {e}")

        return codes

    def get_next_available_code(self) -> str:
        """Get the next CNMC code without creating a record."""
        return self.generate_code()


def get_cnmc_generator(session: Optional[Session] = None) -> CNMCGenerator:
    """Get a CNMC generator instance."""
    return CNMCGenerator(session)
