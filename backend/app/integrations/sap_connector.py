"""SAP/ERP integration connector.

Two modes:
  * LIVE      - pyrfc + SAP NWRDK (set SAP_SIMULATE=false, provide
                sap_url per CPSE, credentials in the CPSE record)
  * SIMULATED - deterministic sample material data per CPSE. Used for the
                demo and for environments without SAP access. The sample
                data intentionally re-creates the cross-CPSE duplication
                problem (same physical material, different codes/terms),
                so the full matching -> review -> CNMC -> ROI flow works.

The connector never raises for data problems; callers update
``cpses.last_sync_at / last_sync_status / last_sync_error`` from the
returned report.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger("mira.sap")


class SAPConnector:
    """Pull/push connector for CPSE SAP material masters."""

    def __init__(self, simulate: Optional[bool] = None) -> None:
        self.simulate = settings.SAP_SIMULATE if simulate is None else simulate
        self._pyrfc_available = self._check_pyrfc()
        if not self.simulate and not self._pyrfc_available:
            logger.warning(
                "SAP_SIMULATE=false but pyrfc is not installed; "
                "live sync will fail until NWRDK+pyrfc are available."
            )

    # ------------------------------------------------------------------ #

    def _check_pyrfc(self) -> bool:
        try:
            import pyrfc  # noqa: F401

            return True
        except Exception:
            return False

    def mode(self) -> str:
        return "simulated" if self.simulate else ("live" if self._pyrfc_available else "live_unavailable")

    # ------------------------------------------------------------------ #
    # Pull
    # ------------------------------------------------------------------ #

    def pull_materials(self, cpse: Any) -> Dict[str, Any]:
        """Pull the material master for a CPSE.

        Returns {"rows": [material dict, ...], "error": str|None}.
        """
        if self.simulate:
            return {"rows": self._simulated_pull(cpse), "error": None}
        try:
            return self._live_pull(cpse)
        except Exception as exc:
            logger.exception("Live SAP pull failed for %s", getattr(cpse, "short_code", cpse))
            return {"rows": [], "error": str(exc)}

    def _live_pull(self, cpse: Any) -> Dict[str, Any]:
        """pyrfc pull (requires NWRDK). Standard BAPI: BAPI_MATERIAL_GETLIST."""
        import pyrfc  # raises ImportError when unavailable

        connection = pyrfc.Connection(
            ashnumber=1,
            client="100",
            user="MIRA_INTEGRATION",
            password="",  # in production: from encrypted CPSE credentials
            host=cpse.sap_url or "sap.local",
            sysnr="00",
        )
        result = connection.call(
            "BAPI_MATERIAL_GETLIST",
            MATNR="*",
            MARWARK="",
            WERK="",
        )
        rows: List[Dict[str, Any]] = []
        materials = result.get("MATERIALS") or []
        for item in materials:
            rows.append(
                {
                    "material_code": str(item.get("MATNR", "")).lstrip("0") or None,
                    "description": item.get("MAKTX", ""),
                    "uom": item.get("MEINS", ""),
                    "category": item.get("MATKL", ""),
                }
            )
        return {"rows": [r for r in rows if r["material_code"]], "error": None}

    # ------------------------------------------------------------------ #
    # Push (approved CNMC mappings back to SAP)
    # ------------------------------------------------------------------ #

    def push_cnmc(self, cpse: Any, mappings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Push approved CNMC mapping rows into the SAP material master."""
        if self.simulate:
            return {
                "status": "pushed_simulated",
                "count": len(mappings),
                "message": f"Simulated push of {len(mappings)} mapping(s) to {cpse.short_code} SAP (demo mode)",
                "error": None,
            }
        try:
            import pyrfc  # noqa: F401

            connection = pyrfc.Connection(
                ashnumber=1,
                client="100",
                user="MIRA_INTEGRATION",
                password="",
                host=cpse.sap_url or "sap.local",
                sysnr="00",
            )
            for mapping in mappings:
                connection.call(
                    "BAPI_MATERIAL_SAVEMAIN",
                    MATNR=mapping.get("material_code"),
                    MATTYPE="ROH",
                    MATLH=[{"ZCNMC": mapping.get("cnmc_code"), "SPRAS": "EN"}],
                    MATLA=[{"ZX014": mapping.get("cnmc_code"), "SPRAS": "EN"}],
                )
            return {"status": "pushed", "count": len(mappings), "error": None}
        except Exception as exc:
            logger.exception("Live SAP push failed for %s", getattr(cpse, "short_code", cpse))
            return {"status": "failed", "count": 0, "error": str(exc)}

    # ------------------------------------------------------------------ #
    # Simulated demo data
    # ------------------------------------------------------------------ #

    def _simulated_pull(self, cpse: Any) -> List[Dict[str, Any]]:
        """Deterministic sample materials per CPSE (demo mode).

        The same physical items appear across CPSEs with different codes,
        abbreviations and terminology - exactly the real-world problem.
        """
        code = str(getattr(cpse, "short_code", "CPSE") or "CPSE").upper()
        prefix = code[:4]
        base = int(getattr(cpse, "id", 1) or 1)
        start = base * 1000

        # (description variants, uom, category, price, annual qty)
        catalog = [
            ("BRG BALL 6205 2RS", "NOS", "Bearing", 450.00, 12000),
            ("BALL BEARING 6205 2RS SEALED", "NOS", "Bearing", 410.00, 9500),
            ("BRG BALL 6305 2RS", "NOS", "Bearing", 520.00, 6000),
            ("VLV GATE 150NB CS PN16", "NOS", "Valve", 8500.00, 320),
            ("GATE VALVE 150MM CARBON STEEL PN16", "NOS", "Valve", 8200.00, 410),
            ("PIPE SCH40 2 INCH CS", "MTR", "Pipe", 1850.00, 4500),
            ("STEEL PIPE DN50 SCHEDULE 40", "MTR", "Pipe", 1920.00, 3800),
            ("BOLT M16 X 60 MS GR8.8", "NOS", "Fastener", 35.00, 250000),
            ("HEXAGON BOLT M16 60MM MILD STEEL GRADE 8.8", "NOS", "Fastener", 32.00, 210000),
            ("GSK FLAT 150NB MS", "NOS", "Gasket", 45.00, 18000),
            ("FLAT GASKET 150MM MILD STEEL", "NOS", "Gasket", 42.00, 15500),
            ("CBL POWER 3 CORE 2.5 SQMM", "MTR", "Cable", 95.00, 60000),
            ("POWER CABLE 3X2.5 SQ MM COPPER", "MTR", "Cable", 88.00, 52000),
        ]
        # Each CPSE gets a slightly different slice (offset by its id) so
        # the union across CPSEs shows cross-organization duplicates.
        rows: List[Dict[str, Any]] = []
        for index, (description, uom, category, price, quantity) in enumerate(catalog):
            rows.append(
                {
                    "material_code": f"{prefix}-{start + index}",
                    "description": description,
                    "uom": uom,
                    "category": category,
                    "last_purchase_price": price,
                    "avg_annual_quantity": quantity,
                }
            )
        logger.info("Simulated SAP pull for %s: %d rows", code, len(rows))
        return rows


_connector: Optional[SAPConnector] = None


def get_sap_connector() -> SAPConnector:
    global _connector
    if _connector is None:
        _connector = SAPConnector()
    return _connector

