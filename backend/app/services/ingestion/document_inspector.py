from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.ingestion.adapters.base import ParsedDocument
from app.services.ingestion.pdf_extractor import extract_pdf_text


@dataclass(frozen=True)
class DocumentProfile:
    """
    Lightweight description of a source document.

    The inspector identifies the most likely document family without
    extracting material records itself.
    """

    filename: str
    page_count: int
    text_length: int
    cpse_hint: str | None
    report_type: str
    signals: dict[str, Any]


class DocumentInspector:
    """
    Identify report families using weighted document-level signals.

    Important design rule:
        If the evidence is ambiguous, return "unknown".

    It is safer to use the generic adapter than to send a document to
    the wrong CPSE-specific parser.
    """

    DETECTION_RULES = {
        "ntpc": {
            "strong": (
                "MATERIAL SHORT DESCRITION",
                "BASE UNIT OF MEASURE",
            ),
            "medium": (
                "MATERIAL SHORT DESCRIPTION",
            ),
        },
        "bhel": {
            "strong": (
                "RFQ",
                "HE971",
            ),
            "medium": (
                "DRAWING NO",
                "TECHNICAL SPECIFICATION",
            ),
        },
        "nalco": {
            "strong": (
                "MATERIAL DESCRIPTION",
                "NATIONAL ALUMINIUM COMPANY",
            ),
            "medium": (
                "MATERIAL CODE",
                "MATERIAL DESCRIPTION",
            ),
        },
        "bpcl": {
            "strong": (
                "MOC:",
                "KHIMLINE",
            ),
            "medium": (
                "LOCATION:",
                "TAG NO",
                "SL.NO:",
            ),
        },
    }

    def inspect(
        self,
        document: ParsedDocument,
    ) -> DocumentProfile:

        text = document.full_text
        upper = text.upper()

        scores: dict[str, int] = {}

        for report_type, rules in self.DETECTION_RULES.items():
            score = 0

            for signal in rules["strong"]:
                if signal in upper:
                    score += 5

            for signal in rules["medium"]:
                if signal in upper:
                    score += 2

            scores[report_type] = score

        best_type = None
        best_score = 0
        second_score = 0

        ranked = sorted(
            scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )

        if ranked:
            best_type, best_score = ranked[0][0], ranked[0][1]

        if len(ranked) > 1:
            second_score = ranked[1][1]

        # Do not make a decision on weak evidence.
        #
        # Also require a meaningful margin over the next-best detector.
        if best_score < 5:
            report_type = "unknown"
        elif best_score == second_score:
            report_type = "unknown"
        elif best_score - second_score < 2:
            report_type = "unknown"
        else:
            report_type = best_type

        signals: dict[str, Any] = {
            "scores": scores,
            "selected_score": best_score,
            "runner_up_score": second_score,
        }

        cpse_hint = self._infer_cpse(
            filename=document.filename,
            text=upper,
        )

        return DocumentProfile(
            filename=document.filename,
            page_count=len(document.pages),
            text_length=len(text),
            cpse_hint=cpse_hint,
            report_type=report_type,
            signals=signals,
        )

    @staticmethod
    def _infer_cpse(
        *,
        filename: str,
        text: str,
    ) -> str | None:

        combined = f"{filename.upper()} {text}"

        cpse_names = (
            "NTPC",
            "BHEL",
            "NALCO",
            "BPCL",
            "HPCL",
            "IOCL",
            "SAIL",
            "ONGC",
            "GAIL",
            "HCL",
            "MDL",
            "APGENCO",
            "CPCL",
        )

        for cpse in cpse_names:
            if cpse in combined:
                return cpse

        return None


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
