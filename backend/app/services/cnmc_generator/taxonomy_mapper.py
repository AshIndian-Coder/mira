"""
Taxonomy mapping service for CNMC codes.
Maps materials to standard taxonomies:
  * UNSPSC (United Nations Standard Products and Services Code)
  * NIC (National Industrial Classification)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.utils.constants import KNOWN_UOMS


class TaxonomyMapper:
    """Maps material descriptions to UNSPSC/NIC codes."""

    UNSPSC_MAPPINGS: Dict[str, Dict[str, Any]] = {
        "Bearing": {
            "unspsc_code": "31161500",
            "unspsc_description": "Ball and Roller Bearings",
            "nic_code": "3312",
            "nic_description": "Bearing and Gear Manufacturing",
        },
        "Valve": {
            "unspsc_code": "31211500",
            "unspsc_description": "Valves, Flow Controls and Filters",
            "nic_code": "3324",
            "nic_description": "Plumbing Fixture and Valve Manufacturing",
        },
        "Pipe": {
            "unspsc_code": "31211600",
            "unspsc_description": "Pipe and Tube Fittings",
            "nic_code": "3324",
            "nic_description": "Plumbing Fixture and Valve Manufacturing",
        },
        "Fastener": {
            "unspsc_code": "31161700",
            "unspsc_description": "Fasteners and Retainers",
            "nic_code": "3326",
            "nic_description": "Hardware Manufacturing",
        },
        "Gasket": {
            "unspsc_code": "31211700",
            "unspsc_description": "Seals and Gaskets",
            "nic_code": "3324",
            "nic_description": "Plumbing Fixture and Valve Manufacturing",
        },
        "Cable": {
            "unspsc_code": "36121500",
            "unspsc_description": "Power and Lighting Cables",
            "nic_code": "3353",
            "nic_description": "Wiring Device Manufacturing",
        },
        "Electrical Connector": {
            "unspsc_code": "36121600",
            "unspsc_description": "Electrical Connectors and Terminals",
            "nic_code": "3353",
            "nic_description": "Wiring Device Manufacturing",
        },
        "Switch": {
            "unspsc_code": "36121700",
            "unspsc_description": "Electrical Switches and Controls",
            "nic_code": "3353",
            "nic_description": "Wiring Device Manufacturing",
        },
        "Transformer": {
            "unspsc_code": "36121800",
            "unspsc_description": "Transformers and Inductors",
            "nic_code": "3353",
            "nic_description": "Wiring Device Manufacturing",
        },
        "Fastener": {
            "unspsc_code": "31161700",
            "unspsc_description": "Fasteners and Retainers",
            "nic_code": "3326",
            "nic_description": "Hardware Manufacturing",
        },
    }

    CATEGORY_KEYWORDS: Dict[str, List[str]] = {
        "Bearing": [
            "bearing", "ball bearing", "roller bearing", "needle bearing",
            "brg", "brng", "bearing ball", "6205", "6305", "6206", "6204",
        ],
        "Valve": [
            "valve", "vlv", "gate valve", "globe valve", "ball valve",
            "check valve", "butterfly valve", "150nb", "200nb", "pn16", "pn25",
        ],
        "Pipe": [
            "pipe", "steelpipe", "sch40", "schedule 40", "dn50", "dn80",
            "2 inch", "50mm", "89mm", "150nb", "cs pipe", "carbon steel pipe",
        ],
        "Fastener": [
            "bolt", "nut", "washer", "fastener", "hex bolt", "m16", "m20",
            "m24", "grade 8.8", "grade 10.9", "ms bolt", "cs bolt",
        ],
        "Gasket": [
            "gasket", "flat gasket", "gsx", "flange gasket", "150nb gasket",
        ],
        "Cable": [
            "cable", "power cable", "3 core", "3x2.5", "4x4", "sqmm",
            "copper cable", "aluminium cable",
        ],
        "Electrical Connector": [
            "connector", "electrical connector", "11kv", "33kv", "terminal",
            "junction box", "cable connector",
        ],
        "Switch": [
            "switch", "11kv switch", "vacuum switch", "air break switch",
        ],
        "Transformer": [
            "transformer", "33kv transformer", "500kva", "power transformer",
        ],
    }

    def __init__(self):
        pass

    def classify_category(self, description: str, existing_category: Optional[str] = None) -> str:
        """Determine the category of a material from its description."""
        if existing_category:
            return existing_category

        desc_lower = (description or "").lower()
        best_match: Optional[str] = None
        best_score = 0

        for category, keywords in self.CATEGORY_KEYWORDS.items():
            score = 0
            for keyword in keywords:
                if keyword in desc_lower:
                    score += 1
            if score > best_score:
                best_score = score
                best_match = category

        return best_match or "General"

    def get_unspsc_code(self, category: str) -> Optional[Dict[str, Any]]:
        """Get UNSPSC code for a category."""
        return self.UNSPSC_MAPPINGS.get(category)

    def get_nic_code(self, category: str) -> Optional[str]:
        """Get NIC code for a category."""
        mapping = self.UNSPSC_MAPPINGS.get(category)
        return mapping.get("nic_code") if mapping else None

    def map_to_taxonomy(
        self,
        description: str,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Map a material to UNSPSC and NIC taxonomies."""
        detected_category = self.classify_category(description, category)

        mapping = self.get_unspsc_code(detected_category) or {}

        return {
            "category": detected_category,
            "unspsc_code": mapping.get("unspsc_code"),
            "unspsc_description": mapping.get("unspsc_description"),
            "nic_code": mapping.get("nic_code"),
            "nic_description": mapping.get("nic_description"),
            "confidence": 1.0 if detected_category == category else 0.8,
        }

    def batch_map(
        self,
        materials: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Map multiple materials to taxonomy codes."""
        results = []
        for material in materials:
            description = material.get("description") or material.get("cleaned_description") or ""
            category = material.get("category")
            taxonomy = self.map_to_taxonomy(description, category)
            results.append({
                "material_id": material.get("id"),
                "material_code": material.get("material_code"),
                "description": description,
                "taxonomy": taxonomy,
            })
        return results

    def suggest_category(self, description: str) -> List[Tuple[str, float]]:
        """Suggest categories for a description with confidence scores."""
        desc_lower = (description or "").lower()
        suggestions: List[Tuple[str, float]] = []

        for category, keywords in self.CATEGORY_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in desc_lower)
            if score > 0:
                confidence = min(1.0, score / len(keywords))
                suggestions.append((category, confidence))

        suggestions.sort(key=lambda x: x[1], reverse=True)
        return suggestions


def get_taxonomy_mapper() -> TaxonomyMapper:
    """Get a taxonomy mapper instance."""
    return TaxonomyMapper()
