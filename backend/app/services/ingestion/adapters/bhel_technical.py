from pathlib import Path
import csv
import json
import re

import fitz


INPUT = Path("data/processed/bhel_materials_enriched.csv")
PDF = Path("data/raw/GAIL.pdf")
OUTPUT = Path("data/processed/bhel_materials_enriched.csv")


MATERIAL_CODES = [
    "HE9718814027",
    "HE9718814035",
    "HE9718814043",
    "HE9711823020",
    "HE9711823039",
    "HE9711823047",
    "HE9711823055",
]


def extract_technical_text(pdf_path: Path) -> str:
    doc = fitz.open(pdf_path)

    pages = []

    # Technical material information starts on page 3.
    for page_number in range(3, len(doc) + 1):
        text = doc[page_number - 1].get_text()

        if text:
            pages.append(text)

    return "\n".join(pages)


def build_code_metadata(text: str) -> dict[str, dict]:
    metadata = {
        code: {
            "material_grade": None,
            "specification": None,
            "drawing_number": None,
        }
        for code in MATERIAL_CODES
    }

    # Explicitly derived from the BHEL technical section.
    group_sa516 = [
        "HE9718814027",
        "HE9718814035",
        "HE9718814043",
        "HE9711823020",
        "HE9711823039",
        "HE9711823047",
    ]

    group_sa387 = [
        "HE9711823055",
    ]

    group_he51370 = group_sa516
    group_he51527 = group_sa387

    group_drawing_41622600340 = [
        "HE9718814027",
        "HE9718814035",
        "HE9718814043",
    ]

    group_drawing_31750102724 = [
        "HE9711823020",
        "HE9711823039",
        "HE9711823047",
        "HE9711823055",
    ]

    for code in group_sa516:
        metadata[code]["material_grade"] = "SA516 GR70"

    for code in group_sa387:
        metadata[code]["material_grade"] = "SA387 GR12 CL2"

    for code in group_he51370:
        metadata[code]["specification"] = "HE51370"

    for code in group_he51527:
        metadata[code]["specification"] = "HE51527"

    for code in group_drawing_41622600340:
        metadata[code]["drawing_number"] = "41622600340"

    for code in group_drawing_31750102724:
        metadata[code]["drawing_number"] = "31750102724"

    # Make sure the expected evidence actually exists
    # in the extracted PDF text.
    if "SA516 GR70" not in text:
        raise ValueError(
            "Expected SA516 GR70 evidence not found in BHEL PDF."
        )

    if "SA387 GR12 CL2" not in text:
        raise ValueError(
            "Expected SA387 GR12 CL2 evidence not found in BHEL PDF."
        )

    if "HE51370" not in text:
        raise ValueError(
            "Expected HE51370 evidence not found in BHEL PDF."
        )

    if "HE51527" not in text:
        raise ValueError(
            "Expected HE51527 evidence not found in BHEL PDF."
        )

    return metadata


def enrich():
    technical_text = extract_technical_text(PDF)
    metadata = build_code_metadata(technical_text)

    with INPUT.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:
        rows = list(csv.DictReader(file))

    input_codes = {
        row["material_code"]
        for row in rows
    }

    expected_codes = set(MATERIAL_CODES)

    if input_codes != expected_codes:
        raise ValueError(
            "BHEL base-record codes do not match "
            "the expected seven material codes.\n"
            f"Expected: {sorted(expected_codes)}\n"
            f"Found: {sorted(input_codes)}"
        )

    for row in rows:
        code = row["material_code"]
        info = metadata[code]

        row["material_grade"] = (
            info["material_grade"] or ""
        )

        existing_specs = {}

        if row.get("specifications"):
            try:
                existing_specs = json.loads(
                    row["specifications"]
                )
            except json.JSONDecodeError:
                existing_specs = {}

        existing_specs.update({
            "product_specification": info["specification"],
            "drawing_number": info["drawing_number"],
        })

        row["specifications"] = json.dumps(
            existing_specs,
            ensure_ascii=False,
        )

        # Preserve the technical provenance explicitly.
        row["other_attributes"] = json.dumps(
            {
                "technical_source": "BHEL RFQ technical section",
            },
            ensure_ascii=False,
        )

    with OUTPUT.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:

        fieldnames = list(rows[0].keys())

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)

    print(f"Enriched BHEL records: {len(rows)}")
    print(f"Saved: {OUTPUT}")

    for row in rows:
        print(
            row["material_code"],
            "→",
            row["material_grade"],
            "|",
            row["specifications"],
        )


if __name__ == "__main__":
    enrich()
