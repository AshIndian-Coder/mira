from copy import deepcopy
from typing import Any

from app.services.ingestion.extraction.fields import extract_labeled_fields
from app.services.ingestion.extraction.identifiers import extract_part_number
from app.services.ingestion.models import MaterialRecord
from app.services.normalization.service import normalize_material_description
from app.services.parsing.service import parse_specifications


def enrich_record(record: MaterialRecord) -> MaterialRecord:
    """
    Convert an extracted MaterialRecord into a richer canonical record.

    Extraction and interpretation remain separate:
      - adapter finds the record
      - field extractor finds explicitly labeled fields
      - specification parser interprets technical description + evidence
      - normalization prepares text for matching

    Unknown information is preserved.
    """

    description = record.description or ""

    # -------------------------------------------------------------
    # 1. Extract identifiers from the original description
    #
    # Identifier extraction must happen before normalization so
    # part numbers are preserved exactly as found in the source.
    # -------------------------------------------------------------
    if not record.manufacturer_part_number:
        record.manufacturer_part_number = extract_part_number(
            description
        )

    # -------------------------------------------------------------
    # 2. Normalize description
    # -------------------------------------------------------------
    record.normalized_description = (
        normalize_material_description(description)
    )

    # -------------------------------------------------------------
    # 3. Collect preserved source evidence
    #
    # The generic adapter may preserve technical lines that were
    # not part of the material description.
    # -------------------------------------------------------------
    raw_lines = record.raw_attributes.get(
        "unmapped_lines",
        [],
    )

    if not isinstance(raw_lines, list):
        raw_lines = []

    # -------------------------------------------------------------
    # 4. Build technical specification context
    #
    # Parse both the material description and nearby preserved
    # evidence. The original description itself remains unchanged.
    # -------------------------------------------------------------
    specification_context = "\n".join(
        [description, *raw_lines]
    )

    parsed = parse_specifications(
        specification_context
    )

    record.parsed_specifications = deepcopy(parsed)

    # -------------------------------------------------------------
    # 5. Preserve structured material grade
    # -------------------------------------------------------------
    if not record.material_grade:
        parsed_grade = parsed.get("material_grade")

        if parsed_grade:
            record.material_grade = parsed_grade

    # -------------------------------------------------------------
    # 6. Dimensions
    # -------------------------------------------------------------
    if record.dimensions is None:
        dimensions = parsed.get("dimensions")

        if dimensions:
            record.dimensions = dimensions

    # -------------------------------------------------------------
    # 7. Extract explicitly labeled fields
    #
    # The adapter has already preserved nearby source lines in
    # raw_attributes. Use those lines as additional evidence.
    # -------------------------------------------------------------
    labeled = extract_labeled_fields(raw_lines)

    if not record.material_grade:
        record.material_grade = labeled.get(
            "material_grade"
        )

    if not record.manufacturer_part_number:
        record.manufacturer_part_number = labeled.get(
            "manufacturer_part_number"
        )

    # -------------------------------------------------------------
    # 8. Add non-canonical labeled fields to other_attributes
    # -------------------------------------------------------------
    for key, value in labeled.items():

        if key in {
            "material_grade",
            "manufacturer_part_number",
        }:
            continue

        if value is None or value == "":
            continue

        record.other_attributes.setdefault(
            key,
            value,
        )

    # -------------------------------------------------------------
    # 9. Preserve all parsed technical specifications.
    #
    # `specifications` is for downstream canonical technical data,
    # while `parsed_specifications` retains the complete parser output.
    # -------------------------------------------------------------
    for key, value in parsed.items():

        if value is None:
            continue

        if key in {
            "material_grade",
            "dimensions",
        }:
            continue

        record.specifications.setdefault(
            key,
            value,
        )

    # -------------------------------------------------------------
    # 10. Record enrichment metadata
    # -------------------------------------------------------------
    record.extraction_metadata = {
        **record.extraction_metadata,
        "enriched": True,
        "normalization": "normalize_material_description",
        "specification_parser": "parse_specifications",
        "labeled_field_extraction": bool(labeled),
        "identifier_extraction": bool(
            record.manufacturer_part_number
        ),
    }

    return record


def enrich_records(
    records: list[MaterialRecord],
) -> list[MaterialRecord]:
    """
    Enrich a batch of material records.
    """

    return [
        enrich_record(record)
        for record in records
    ]
