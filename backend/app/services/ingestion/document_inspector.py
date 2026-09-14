from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.ingestion.adapters.base import ParsedDocument
from app.services.ingestion.pdf_extractor import extract_pdf_text


@dataclass(frozen=True)
class DocumentProfile:
    """
    Lightweight description of a source document.

    The inspector performs generic document-level profiling only.
    It does not identify a CPSE or select a CPSE-specific parser.
    """

    filename: str
    page_count: int
    text_length: int
    signals: dict[str, Any]


class DocumentInspector:
    """
    Perform generic document-level inspection.

    The inspector intentionally avoids organization-specific or
    tender-specific detection. Material extraction is handled by the
    generic adapter.
    """

    def inspect(
        self,
        document: ParsedDocument,
    ) -> DocumentProfile:

        text = document.full_text

        signals: dict[str, Any] = {
            "has_text": bool(text.strip()),
            "line_count": sum(
                len(page.get("text", "").splitlines())
                for page in document.pages
            ),
        }

        return DocumentProfile(
            filename=document.filename,
            page_count=len(document.pages),
            text_length=len(text),
            signals=signals,
        )


def inspect_pdf(
    pdf_path: str | Path,
) -> tuple[ParsedDocument, DocumentProfile]:

    path = Path(pdf_path)

    pages = extract_pdf_text(path)

    document = ParsedDocument(
        path=path,
        pages=pages,
    )

    profile = DocumentInspector().inspect(document)

    return document, profile
