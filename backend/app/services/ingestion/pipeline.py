from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.ingestion.adapters.base import ParsedDocument
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
    records: list[MaterialRecord]

    validation: dict[str, Any]

    extraction_metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "report_type": self.report_type,
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

    Documents are parsed through the generic adapter so that ingestion
    remains independent of CPSE-specific or tender-specific layouts.
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
        # 3. Extract material records
        # -------------------------------------------------------------
        records = self._extract_records(
            document=document,
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
            report_type="generic",
            records=records,
            validation=validation,
            extraction_metadata={
                "pages_extracted": len(pages),
                "document_profile": {
                    "report_type": "generic",
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
    ) -> list[MaterialRecord]:
        """
        Extract material records using the generic adapter.

        PDF extraction and material detection remain format-agnostic.
        CPSE identity is not inferred during generic document ingestion.
        """
        return self.generic_adapter.extract_records(
            document,
        )


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
    print(f"Parser       : {result.report_type}")
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