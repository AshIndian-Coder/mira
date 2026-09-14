from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.ingestion.models import MaterialRecord


@dataclass
class ParsedDocument:
    """
    Source document after basic extraction.

    Adapters receive this representation rather than opening PDFs
    themselves. This keeps document extraction separate from
    material-record interpretation.
    """

    path: Path
    pages: list[dict[str, Any]]

    @property
    def filename(self) -> str:
        return self.path.name

    @property
    def full_text(self) -> str:
        return "\n".join(
            page.get("text", "")
            for page in self.pages
        )


class DocumentAdapter(ABC):
    """
    Interface implemented by every report-format adapter.
    """

    name: str = "unknown"

    @abstractmethod
    def can_handle(self, document: ParsedDocument) -> bool:
        """
        Return True when this adapter recognizes the document format.
        """
        raise NotImplementedError

    @abstractmethod
    def extract_records(
        self,
        document: ParsedDocument,
    ) -> list[MaterialRecord]:
        """
        Extract canonical material records from the document.
        """
        raise NotImplementedError
