from __future__ import annotations

from typing import Any

from app.services.ingestion.llm.base import (
    LLMExtractionResult,
)
from app.services.ingestion.llm.service import (
    LLMExtractionService,
)
from app.services.ingestion.models import MaterialRecord


LLM_FIELD_MAP = {
    "material_grade": "material_grade",
    "manufacturer": "manufacturer",
    "manufacturer_part_number": "manufacturer_part_number",
    "model": "other_attributes",
    "dimensions": "dimensions",
}

def build_evidence_text(record: MaterialRecord) -> str:
    """
    Build the text supplied to the LLM from preserved source evidence.

    The resolver operates on evidence, not on any particular adapter.
    """
    raw_attributes = record.raw_attributes or {}

    parts: list[str] = []

    if record.description:
        parts.append(str(record.description))

    unmapped_lines = raw_attributes.get(
        "unmapped_lines",
        [],
    )

    if isinstance(unmapped_lines, list):
        parts.extend(
            str(line)
            for line in unmapped_lines
            if line is not None and str(line).strip()
        )

    return "\n".join(parts)

class LLMResolver:
    """
    Applies LLM candidate evidence conservatively.

    Existing deterministic values always take precedence.
    The LLM is only allowed to fill missing fields.
    """

    def __init__(
        self,
        service: LLMExtractionService | None = None,
    ) -> None:
        self.service = service or LLMExtractionService()

    def should_use_llm(self, record: MaterialRecord) -> bool:
        """
        Decide whether LLM extraction is justified.

        Missing fields alone do not trigger the LLM. Escalation requires
        evidence of ambiguity, low-confidence extraction, or explicit
        structured-field labels.
        """

        metadata = record.extraction_metadata or {}
        raw_attributes = record.raw_attributes or {}

        confidence = str(
            metadata.get("confidence", "")
        ).lower()

        if confidence in {"low", "medium"}:
            return True

        if raw_attributes.get("ambiguous_fields"):
            return True

        evidence = build_evidence_text(record).upper()

        recoverable_labels = (
            "MOC:",
            "MATERIAL GRADE:",
            "GRADE:",
            "MANUFACTURER:",
            "MAKE:",
            "BRAND:",
            "MODEL:",
            "PART NO:",
            "PART NUMBER:",
            "P/N:",
            "P.N.:",
            "DIMENSION:",
            "DIMENSIONS:",
        )

        return any(
            label in evidence
            for label in recoverable_labels
        )

    def resolve(
        self,
        record: MaterialRecord,
        evidence_text: str,
    ) -> MaterialRecord:

        if not self.service.enabled:
            return record

        if not self.should_use_llm(record):
            record.extraction_metadata = {
                **record.extraction_metadata,
                "llm_used": False,
                "llm_reason": "deterministic_fields_sufficient",
            }
            return record

        result = self.service.extract(evidence_text)

        self._apply_candidates(
            record,
            result,
        )

        record.extraction_metadata = {
            **record.extraction_metadata,
            "llm_used": True,
            "llm_provider": result.metadata.get(
                "provider"
            ),
            "llm_model": result.metadata.get(
                "model"
            ),
            "llm_metadata": result.metadata,
        }

        return record

    def _apply_candidates(
        self,
        record: MaterialRecord,
        result: LLMExtractionResult,
    ) -> None:

        for field, candidate in result.fields.items():

            if candidate is None:
                continue

            if isinstance(candidate, str):
                candidate = candidate.strip()

            if candidate == "":
                continue

            target = LLM_FIELD_MAP.get(field)

            if target is None:
                continue

            # ---------------------------------------------------------
            # Canonical fields
            # ---------------------------------------------------------
            if target in {
                "material_grade",
                "manufacturer",
                "manufacturer_part_number",
            }:

                existing = getattr(
                    record,
                    target,
                )

                if existing:
                    self._record_conflict(
                        record,
                        field,
                        existing,
                        candidate,
                    )
                    continue

                setattr(
                    record,
                    target,
                    candidate,
                )

            # ---------------------------------------------------------
            # Dimensions
            # ---------------------------------------------------------
            elif target == "dimensions":

                if record.dimensions is None:
                    record.dimensions = {
                        "llm_value": candidate,
                    }
                else:
                    self._record_conflict(
                        record,
                        field,
                        record.dimensions,
                        candidate,
                    )

            # ---------------------------------------------------------
            # Other attributes
            # ---------------------------------------------------------
            elif target == "other_attributes":

                if field == "model":
                    key = "model"
                else:
                    key = field

                existing = record.other_attributes.get(
                    key
                )

                if existing is None:
                    record.other_attributes[key] = (
                        candidate
                    )
                else:
                    self._record_conflict(
                        record,
                        field,
                        existing,
                        candidate,
                    )

    @staticmethod
    def _record_conflict(
        record: MaterialRecord,
        field: str,
        existing: Any,
        candidate: Any,
    ) -> None:

        conflicts = record.raw_attributes.setdefault(
            "llm_conflicts",
            [],
        )

        conflicts.append(
            {
                "field": field,
                "deterministic_value": existing,
                "llm_value": candidate,
            }
        )
