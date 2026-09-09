from pathlib import Path
import pymupdf


def extract_pdf_text(pdf_path: str | Path) -> list[dict]:
    """
    Extract text from every page while preserving provenance.
    """

    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    records = []

    with pymupdf.open(pdf_path) as document:
        for page_number, page in enumerate(document, start=1):
            text = page.get_text("text").strip()

            if not text:
                continue

            records.append(
                {
                    "source_file": pdf_path.name,
                    "page": page_number,
                    "text": text,
                }
            )

    return records
