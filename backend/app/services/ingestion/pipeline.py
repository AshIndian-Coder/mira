from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.ingestion.adapters.base import ParsedDocument
from app.services.ingestion.adapters.bhel import parse_bhel_pdf
from app.services.ingestion.adapters.nalco import parse_nalco_pdf
from app.services.ingestion.adapters.generic import GenericAdapter
from app.services.ingestion.document_inspector import DocumentInspector
from app.services.ingestion.pdf_extractor import extract_pdf_text
from app.services.ingestion.validation import validate_batch
from app.services.ingestion.models import MaterialRecord
from app.services.ingestion.enrichment import enrich_records
from app.services.ingestion.llm.resolver import (LLMResolver, build_evidence_text,)


@dataclass
class IngestionResult:
    """
    Complete result of processing one source document.
    """

    source_file: str
    report_type: str
    cpse_hint: str | None

    records: list[MaterialRecord]

    validation: dict[str, Any]

    extraction_metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "report_type": self.report_type,
            "cpse_hint": self.cpse_hint,
            "record_count": len(self.records),
            "records": [
                record.to_dict()
                for record in self.records
            ],
            "validation": self.validation,
            "extraction_metadata": self.extraction_metadata,
        }


class IngestionPipeline:
    """
    Single entry point for document ingestion.

    Specialized adapters are preferred when the document inspector
    identifies a known report family. If a specialized adapter cannot
    extract any records, the generic adapter is used as a fallback.
    """

    def __init__(self) -> None:
        self.inspector = DocumentInspector()
        self.generic_adapter = GenericAdapter()
        self.llm_resolver = LLMResolver()

    def ingest(
        self,
        pdf_path: str | Path,
    ) -> IngestionResult:

        path = Path(pdf_path)

        if not path.exists():
            raise FileNotFoundError(
                f"PDF not found: {path}"
            )

        # -------------------------------------------------------------
        # 1. Extract source document
        # -------------------------------------------------------------
        pages = extract_pdf_text(path)

        document = ParsedDocument(
            path=path,
            pages=pages,
        )

        # -------------------------------------------------------------
        # 2. Inspect document
        # -------------------------------------------------------------
        profile = self.inspector.inspect(document)

        # -------------------------------------------------------------
        # 3. Select adapter
        # -------------------------------------------------------------
        records = self._extract_records(
            document=document,
            report_type=profile.report_type,
        )

        # -------------------------------------------------------------
        # 4. Enrich canonical records
        # -------------------------------------------------------------
        records = enrich_records(records)

        # -------------------------------------------------------------
        # 5. Optional LLM fallback
        #
        # Deterministic extraction remains authoritative.
        # The resolver only escalates records where there is useful
        # evidence of missing or uncertain structured information.
        # LLM failures must never stop ingestion.
        # -------------------------------------------------------------
        for record in records:
            evidence_text = build_evidence_text(record)

            if not self.llm_resolver.should_use_llm(record):
                continue

            try:
                self.llm_resolver.resolve(
                    record,
                    evidence_text,
                )
            except Exception as exc:
                record.extraction_metadata = {
                    **record.extraction_metadata,
                    "llm_used": False,
                    "llm_error": str(exc),
                }

        # -------------------------------------------------------------
        # 6. Validate enriched records
        # -------------------------------------------------------------
        validation = validate_batch(records)

        return IngestionResult(
            source_file=path.name,
            report_type=profile.report_type,
            cpse_hint=profile.cpse_hint,
            records=records,
            validation=validation,
            extraction_metadata={
                "pages_extracted": len(pages),
                "document_profile": {
                    "report_type": profile.report_type,
                    "cpse_hint": profile.cpse_hint,
                    "signals": profile.signals,
                },
                "llm_provider": getattr(
                    self.llm_resolver.service.provider,
                    "name",
                    "none",
                ),
                "llm_enabled": self.llm_resolver.service.enabled,
            },
        )

    def _extract_records(
        self,
        *,
        document: ParsedDocument,
        report_type: str,
    ) -> list[MaterialRecord]:

        specialized_records: list[MaterialRecord] = []

        # -------------------------------------------------------------
        # 1. Try the specialized adapter selected by the inspector.
        #
        # A classification is a preference, not a guarantee that the
        # adapter can actually extract this document.
        # -------------------------------------------------------------
        if report_type == "bhel":
            specialized_records = parse_bhel_pdf(document.path)

        elif report_type == "nalco":
            specialized_records = parse_nalco_pdf(document.path)

        elif report_type == "ntpc":
            from app.services.ingestion.ntpc_parser import (
                parse_ntpc_pdf,
            )

            raw_records = parse_ntpc_pdf(document.path)

            specialized_records = [
                MaterialRecord(
                    cpse=record["cpse"],
                    material_code=record["material_code"],
                    description=record["description"],
                    unit=record.get("unit"),
                    quantity=record.get("quantity"),
                    source_file=record.get("source_file"),
                    source_page=record.get("source_page"),
                    extraction_metadata={
                        "adapter": "ntpc_legacy",
                        "confidence": "medium",
                    },
                )
                for record in raw_records
            ]

        # -------------------------------------------------------------
        # 2. Accept specialized extraction only if it actually
        #    produced records.
        # -------------------------------------------------------------
        if specialized_records:
            return specialized_records

        # -------------------------------------------------------------
        # 3. Generic fallback.
        #
        # This protects us from:
        #   - incorrect document classification
        #   - incomplete specialized adapters
        #   - new report variants
        #   - unfamiliar CPSE formats
        # -------------------------------------------------------------
        generic_records = self.generic_adapter.extract_records(
            document
        )

        return generic_records


def ingest_pdf(
    pdf_path: str | Path,
) -> IngestionResult:
    """
    Convenience API for callers that do not need to instantiate the
    pipeline explicitly.
    """

    return IngestionPipeline().ingest(pdf_path)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Run MIRA document ingestion."
    )

    parser.add_argument(
        "pdf",
        help="Path to source PDF",
    )

    args = parser.parse_args()

    result = ingest_pdf(args.pdf)

    print("=" * 70)
    print("MIRA INGESTION")
    print("=" * 70)

    print(f"Source       : {result.source_file}")
    print(f"Report type  : {result.report_type}")
    print(f"CPSE hint    : {result.cpse_hint}")
    print(f"Records      : {len(result.records)}")

    print()
    print("VALIDATION")
    print("-" * 70)

    validation = result.validation

    print(
        f"Valid        : {validation['valid_records']}"
    )
    print(
        f"Invalid      : {validation['invalid_records']}"
    )
    print(
        f"Validation   : {validation['validation_rate']:.2%}"
    )

    print()
    print("SAMPLE RECORDS")
    print("-" * 70)

    for record in result.records[:5]:
        print(
            record.material_code,
            "→",
            record.description,
        )


if __name__ == "__main__":
    main()