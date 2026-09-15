"""
Duplicate group (cluster) engine for MIRA match suggestions.

Groups approved HIGH_CONFIDENCE matches into equivalence clusters (each
cluster corresponds to one CNMC). The cluster engine is the bridge between
the AI matching layer and the CNMC generation layer.

Cluster rules:
  * A cluster is built from approved matches (status = approved).
  * Two materials are in the same cluster if there is an approved match
    path between them (transitive closure).
  * Each cluster gets a CNMC code from the CNMC generator.
  * Clusters are stable: re-running the engine with the same approved
    matches produces the same clusters.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from app.db.postgres import SessionLocal
from app.models.match_suggestion import MatchSuggestion
from app.models.material import Material
from app.utils.constants import SUGGESTION_STATUS_APPROVED


class ClusterEngine:
    """Builds and manages equivalence clusters from approved matches."""

    def __init__(self) -> None:
        self._clusters: Dict[str, Dict[str, Any]] = {}
        self._material_to_cluster: Dict[int, str] = {}

    def build_clusters(self, session=None) -> Dict[str, Dict[str, Any]]:
        """Rebuild all clusters from approved matches in the database."""
        db = session or SessionLocal()
        try:
            approved_suggestions = (
                db.query(MatchSuggestion)
                .filter(MatchSuggestion.status == SUGGESTION_STATUS_APPROVED)
                .all()
            )

            adjacency: Dict[int, Set[int]] = defaultdict(set)
            materials: Set[int] = set()

            for suggestion in approved_suggestions:
                m1_id = suggestion.material_1_id
                m2_id = suggestion.material_2_id
                if m1_id and m2_id:
                    adjacency[m1_id].add(m2_id)
                    adjacency[m2_id].add(m1_id)
                    materials.add(m1_id)
                    materials.add(m2_id)

            visited: Set[int] = set()
            clusters = []

            for material_id in materials:
                if material_id in visited:
                    continue
                component = self._bfs(material_id, adjacency, visited)
                clusters.append(component)

            self._clusters = {}
            self._material_to_cluster = {}

            for cluster_materials in clusters:
                cluster_id = str(uuid.uuid4())
                material_details = self._load_material_details(db, cluster_materials)
                cluster = {
                    "cluster_id": cluster_id,
                    "material_ids": sorted(cluster_materials),
                    "materials": material_details,
                    "size": len(cluster_materials),
                    "categories": self._extract_categories(material_details),
                    "cnmc_code": None,
                    "cnmc_id": None,
                }
                self._clusters[cluster_id] = cluster
                for mat_id in cluster_materials:
                    self._material_to_cluster[mat_id] = cluster_id

            return self._clusters

        finally:
            if session is None:
                db.close()

    def _bfs(self, start: int, adjacency: Dict[int, Set[int]], visited: Set[int]) -> List[int]:
        """Breadth-first search to find connected component."""
        component: List[int] = []
        queue = [start]
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            component.append(node)
            for neighbor in adjacency.get(node, set()):
                if neighbor not in visited:
                    queue.append(neighbor)
        return component

    def _load_material_details(self, db: SessionLocal, material_ids: List[int]) -> List[Dict[str, Any]]:
        """Load material details for a list of material IDs."""
        materials = db.query(Material).filter(Material.id.in_(material_ids)).all()
        return [
            {
                "id": material.id,
                "cpse_id": material.cpse_id,
                "material_code": material.material_code,
                "description": material.description,
                "cleaned_description": material.cleaned_description,
                "attributes": dict(material.attributes or {}),
                "category": material.category,
                "uom_normalized": material.uom_normalized,
            }
            for material in materials
        ]

    def _extract_categories(self, materials: List[Dict[str, Any]]) -> List[str]:
        """Extract unique categories from materials."""
        categories: Set[str] = set()
        for material in materials:
            if material.get("category"):
                categories.add(material["category"])
        return sorted(categories)

    def get_clusters(self) -> Dict[str, Dict[str, Any]]:
        """Return all clusters (rebuilds from DB if needed)."""
        if not self._clusters:
            self.build_clusters()
        return self._clusters

    def get_cluster_for_material(self, material_id: int) -> Optional[Dict[str, Any]]:
        """Get the cluster containing a material."""
        cluster_id = self._material_to_cluster.get(material_id)
        if cluster_id:
            return self._clusters.get(cluster_id)
        self.build_clusters()
        return self._material_to_cluster.get(material_id)

    def get_cluster_by_id(self, cluster_id: str) -> Optional[Dict[str, Any]]:
        """Get a cluster by ID."""
        return self._clusters.get(cluster_id)

    def add_to_cluster(
        self,
        material_id: int,
        material_name: str,
        category: Optional[str] = None,
        session=None,
    ) -> Optional[str]:
        """Add a material to an existing cluster or create a new one."""
        db = session or SessionLocal()
        try:
            existing_cluster_id = self._material_to_cluster.get(material_id)

            if existing_cluster_id:
                cluster = self._clusters[existing_cluster_id]
                for material in cluster["materials"]:
                    if material["id"] == material_id:
                        if material_name:
                            material["description"] = material_name
                        if category:
                            material["category"] = category
                        break
                return existing_cluster_id

            cluster_id = str(uuid.uuid4())
            cluster = {
                "cluster_id": cluster_id,
                "material_ids": [material_id],
                "materials": [
                    {
                        "id": material_id,
                        "cpse_id": None,
                        "material_code": None,
                        "description": material_name,
                        "cleaned_description": material_name,
                        "attributes": {},
                        "category": category,
                        "uom_normalized": None,
                    }
                ],
                "size": 1,
                "categories": [category] if category else [],
                "cnmc_code": None,
                "cnmc_id": None,
            }
            self._clusters[cluster_id] = cluster
            self._material_to_cluster[material_id] = cluster_id
            return cluster_id

        finally:
            if session is None:
                db.close()

    def merge_clusters(self, cluster_id_1: str, cluster_id_2: str, session=None) -> str:
        """Merge two clusters into one."""
        db = session or SessionLocal()
        try:
            cluster1 = self._clusters.get(cluster_id_1)
            cluster2 = self._clusters.get(cluster_id_2)

            if not cluster1 or not cluster2:
                raise ValueError("One or both clusters not found")

            if cluster1["size"] >= cluster2["size"]:
                base_cluster = cluster1
                other_cluster = cluster2
                base_id = cluster_id_1
            else:
                base_cluster = cluster2
                other_cluster = cluster1
                base_id = cluster_id_2

            for material in other_cluster["materials"]:
                if material["id"] not in base_cluster["material_ids"]:
                    base_cluster["material_ids"].append(material["id"])
                    base_cluster["materials"].append(material)

            base_cluster["size"] = len(base_cluster["material_ids"])
            base_cluster["categories"] = self._extract_categories(base_cluster["materials"])

            for mat_id in other_cluster["material_ids"]:
                self._material_to_cluster[mat_id] = base_id

            del self._clusters[cluster_id_2]

            return base_id

        finally:
            if session is None:
                db.close()

    def get_unclustered_materials(self, session=None) -> List[Dict[str, Any]]:
        """Get materials that are not in any cluster."""
        db = session or SessionLocal()
        try:
            clustered_ids = set(self._material_to_cluster.keys())
            unclustered = (
                db.query(Material)
                .filter(~Material.id.in_(clustered_ids))
                .filter(Material.status == "active")
                .all()
            )
            return [
                {
                    "id": m.id,
                    "cpse_id": m.cpse_id,
                    "material_code": m.material_code,
                    "description": m.description,
                    "category": m.category,
                }
                for m in unclustered
            ]
        finally:
            if session is None:
                db.close()

    def get_cluster_stats(self) -> Dict[str, Any]:
        """Get statistics about current clusters."""
        clusters = self.get_clusters()
        total_materials = sum(c["size"] for c in clusters.values())
        total_clusters = len(clusters)
        avg_size = total_materials / total_clusters if total_clusters > 0 else 0

        by_category: Dict[str, int] = defaultdict(int)
        for cluster in clusters.values():
            for cat in cluster["categories"]:
                by_category[cat] += 1

        return {
            "total_clusters": total_clusters,
            "total_materials_clustered": total_materials,
            "average_cluster_size": round(avg_size, 2),
            "by_category": dict(by_category),
        }


def get_cluster_engine() -> ClusterEngine:
    """Get a cluster engine instance."""
    return ClusterEngine()
