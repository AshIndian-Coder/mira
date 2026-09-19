from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent

INPUT_CSV = (
    BASE_DIR
    / "results"
    / "epoch2"
    / "epoch1_train_hard_negative_failures.csv"
)

OUTPUT_DIR = (
    BASE_DIR
    / "results"
    / "epoch2"
)

KEEP_CSV = OUTPUT_DIR / "hn_true_keep.csv"
REVIEW_CSV = OUTPUT_DIR / "hn_review.csv"
DROP_CSV = OUTPUT_DIR / "hn_drop.csv"
SUMMARY_JSON = OUTPUT_DIR / "strict_hn_audit_summary.json"

REQUIRED_COLUMNS = {
    "pair_id",
    "desc_a",
    "desc_b",
    "label",
    "pair_type",
    "hard_negative_field",
    "hard_negative_reason",
    "epoch1_similarity",
}

CONFLICT_REASON_PATTERN = re.compile(
    r"conflicting\s+([a-z_]+):\s+"
    r"a='([^']*)'\s+vs\s+b='([^']*)'",
    re.IGNORECASE,
)

LEARNABLE_FIELDS = {
    "dimensions",
    "size_or_model",
    "material_grade",
    "schedule",
    "standard",
    "end_connection",
    "pressure_rating",
    "voltage_class",
}


MISSING_VALUES = {
    "",
    "-",
    "N/A",
    "NA",
    "NONE",
    "NULL",
    "UNKNOWN",
}


GENERIC_MATERIAL_GRADES = {
    "SS",
    "CS",
    "GI",
    "AL",
    "CU",
}

def is_missing_value(value: object) -> bool:
    if value is None:
        return True

    try:
        missing = pd.isna(value)
        if isinstance(missing, bool) and missing:
            return True
    except (TypeError, ValueError):
        pass

    return str(value).strip().upper() in MISSING_VALUES


def canonical_value(value: object) -> str:
    if is_missing_value(value):
        return ""

    return re.sub(
        r"[^A-Z0-9.]+",
        "",
        str(value).strip().upper(),
    )


def canonical_dimension(value: object) -> str:
    if is_missing_value(value):
        return ""

    text = str(value).strip().upper()

    match = re.fullmatch(
        r"DN\s*(\d+(?:\.\d+)?)",
        text,
    )

    if match:
        return f"NB{match.group(1)}"

    match = re.fullmatch(
        r"(\d+(?:\.\d+)?)\s*NB",
        text,
    )

    if match:
        return f"NB{match.group(1)}"

    return canonical_value(text)

def extract_explicit_conflict(
    reason: object,
) -> tuple[str, str, str] | None:

    if is_missing_value(reason):
        return None

    match = CONFLICT_REASON_PATTERN.search(
        str(reason)
    )

    if match is None:
        return None

    return (
        match.group(1).strip().lower(),
        match.group(2).strip(),
        match.group(3).strip(),
    )

def strip_non_spec_metadata(
    description: object,
) -> str:

    text = "" if description is None else str(description).upper()

    text = re.sub(
        r"\bPN\s+[A-Z0-9][A-Z0-9._/-]*",
        " ",
        text,
    )

    text = re.sub(
        r"\bMAKE\s+[A-Z0-9&._/-]+",
        " ",
        text,
    )

    text = re.sub(
        r"\bFOR\s+UNIT\s*[-/]?\s*[A-Z0-9]+",
        " ",
        text,
    )

    return text

def dimension_visible(
    value: str,
    description: str,
) -> bool:

    text = description.upper()

    # DN80
    match = re.fullmatch(
        r"DN\s*(\d+(?:\.\d+)?)",
        value.upper(),
    )

    if match:
        number = match.group(1)

        return bool(
            re.search(
                rf"(?<![A-Z0-9])"
                rf"DN\s*{re.escape(number)}"
                rf"(?![A-Z0-9])",
                text,
            )
            or
            re.search(
                rf"(?<![A-Z0-9])"
                rf"{re.escape(number)}\s*NB"
                rf"(?![A-Z0-9])",
                text,
            )
        )

    match = re.fullmatch(
        r"(\d+(?:\.\d+)?)\s*NB",
        value.upper(),
    )

    if match:
        number = match.group(1)

        return bool(
            re.search(
                rf"(?<![A-Z0-9])"
                rf"DN\s*{re.escape(number)}"
                rf"(?![A-Z0-9])",
                text,
            )
            or
            re.search(
                rf"(?<![A-Z0-9])"
                rf"{re.escape(number)}\s*NB"
                rf"(?![A-Z0-9])",
                text,
            )
        )

    match = re.fullmatch(
        r"M\s*(\d+(?:\.\d+)?)"
        r"\s*X\s*"
        r"(\d+(?:\.\d+)?)",
        value.upper(),
    )

    if match:
        diameter, length = match.groups()

        return bool(
            re.search(
                rf"(?<![A-Z0-9])"
                rf"M\s*{re.escape(diameter)}"
                rf"\s*X\s*{re.escape(length)}"
                rf"(?![A-Z0-9])",
                text,
            )
        )

    return False

def size_or_model_visible(
    value: str,
    description: str,
) -> bool:

    text = description.upper()
    value_upper = value.strip().upper()

    if re.fullmatch(
        r"\d+(?:\.\d+)?",
        value_upper,
    ):

        number = re.escape(value_upper)

        patterns = (
            rf"(?<![A-Z0-9])"
            rf"CAT\s*[-/]\s*{number}"
            rf"(?![A-Z0-9])",

            rf"(?<![A-Z0-9])"
            rf"MS\s*[-/]\s*{number}"
            rf"(?![A-Z0-9])",

            rf"(?<![A-Z0-9])"
            rf"MODEL\s*[-:]?\s*{number}"
            rf"(?![A-Z0-9])",

            rf"(?<![A-Z0-9])"
            rf"TYPE\s*[-:]?\s*{number}"
            rf"(?![A-Z0-9])",

            rf"(?<![A-Z0-9])"
            rf"{number}\s*(?:MT|KG|TONS?|T)"
            rf"(?![A-Z0-9])",
        )

        return any(
            re.search(
                pattern,
                text,
            )
            for pattern in patterns
        )

    token = canonical_value(
        value_upper
    )

    if len(token) < 2:
        return False

    canonical_text = canonical_value(
        text
    )

    return bool(
        re.search(
            rf"(?<![A-Z0-9])"
            rf"{re.escape(token)}"
            rf"(?![A-Z0-9])",
            canonical_text,
        )
    )

def material_grade_visible(
    value: str,
    description: str,
) -> bool:

    text = description.upper()

    value_canonical = canonical_value(
        value
    )

    match = re.fullmatch(
        r"(SS|CS|GI|AL|CU)(\d{2,4})",
        value_canonical,
    )

    if match:
        family, grade = match.groups()

        return bool(
            re.search(
                rf"(?<![A-Z0-9])"
                rf"{family}"
                rf"\s*[-/]?\s*"
                rf"{grade}"
                rf"(?![A-Z0-9])",
                text,
            )
        )

    if value_canonical in GENERIC_MATERIAL_GRADES:

        generic_visible = bool(
            re.search(
                rf"(?<![A-Z0-9])"
                rf"{re.escape(value_canonical)}"
                rf"(?![A-Z0-9])",
                text,
            )
        )

        specific_grade_present = bool(
            re.search(
                rf"(?<![A-Z0-9])"
                rf"{re.escape(value_canonical)}"
                rf"\s*[-/]?\s*"
                rf"\d{{2,4}}"
                rf"(?![A-Z0-9])",
                text,
            )
        )

        return (
            generic_visible
            and not specific_grade_present
        )

    return bool(
        re.search(
            rf"(?<![A-Z0-9])"
            rf"{re.escape(value)}"
            rf"(?![A-Z0-9])",
            text,
            re.IGNORECASE,
        )
    )

def technical_value_visible(
    value: object,
    description: object,
    field: str,
) -> bool:

    if is_missing_value(value):
        return False

    description_text = strip_non_spec_metadata(
        description
    )

    value_text = str(value).strip().upper()

    if field == "dimensions":
        return dimension_visible(
            value_text,
            description_text,
        )

    if field == "size_or_model":
        return size_or_model_visible(
            value_text,
            description_text,
        )

    if field == "material_grade":
        return material_grade_visible(
            value_text,
            description_text,
        )

    if field == "schedule":

        match = re.fullmatch(
            r"SCH\s*(\d+)",
            value_text,
        )

        if match:

            number = match.group(1)

            return bool(
                re.search(
                    rf"(?<![A-Z0-9])"
                    rf"(?:SCH\s*{number}"
                    rf"|SCHEDULE\s*{number})"
                    rf"(?![A-Z0-9])",
                    description_text,
                    re.IGNORECASE,
                )
            )

    canonical = canonical_value(
        value_text
    )

    if not canonical:
        return False

    canonical_description = canonical_value(
        description_text
    )

    return bool(
        re.search(
            rf"(?<![A-Z0-9])"
            rf"{re.escape(canonical)}"
            rf"(?![A-Z0-9])",
            canonical_description,
        )
    )

def numeric_unit_reference(
    value: str,
    description: object,
) -> bool:

    if not re.fullmatch(
        r"\d+(?:\.\d+)?",
        value.strip(),
    ):
        return False

    return bool(
        re.search(
            rf"\bFOR\s+UNIT\s*[-/]?\s*"
            rf"{re.escape(value.strip())}\b",
            str(description),
            re.IGNORECASE,
        )
    )

def classify_row(
    row: pd.Series,
) -> tuple[str, str]:

    if int(row["label"]) != 0:
        return (
            "REVIEW",
            "label_not_zero",
        )

    pair_type = (
        str(row["pair_type"])
        .strip()
        .upper()
    )

    if not pair_type.startswith("HN_"):
        return (
            "REVIEW",
            "pair_type_not_hn",
        )

    field = (
        str(row["hard_negative_field"])
        .strip()
        .lower()
    )

    if field == "unrecognized_field":
        return (
            "DROP",
            "critical_difference_not_text_visible",
        )

    if field not in LEARNABLE_FIELDS:
        return (
            "REVIEW",
            "unsupported_hard_negative_field",
        )

    conflict = extract_explicit_conflict(
        row["hard_negative_reason"]
    )

    if conflict is None:
        return (
            "REVIEW",
            "no_explicit_conflict_values",
        )

    reason_field, value_a, value_b = conflict

    if reason_field != field:
        return (
            "REVIEW",
            "reason_field_mismatch",
        )

    if (
        is_missing_value(value_a)
        or is_missing_value(value_b)
    ):
        return (
            "DROP",
            "one_side_missing_value",
        )

    if field == "dimensions":

        canonical_a = canonical_dimension(
            value_a
        )

        canonical_b = canonical_dimension(
            value_b

        )

    else:

        canonical_a = canonical_value(
            value_a
        )

        canonical_b = canonical_value(
            value_b
        )

    if canonical_a == canonical_b:
        return (
            "DROP",
            "values_normalize_equal",
        )

    if (
        numeric_unit_reference(
            value_a,
            row["desc_a"],
        )
        or
        numeric_unit_reference(
            value_b,
            row["desc_b"],
        )
    ):
        return (
            "REVIEW",
            "numeric_value_may_be_unit_reference",
        )

    visible_a = technical_value_visible(
        value_a,
        row["desc_a"],
        field,
    )

    visible_b = technical_value_visible(
        value_b,
        row["desc_b"],
        field,
    )

    if not visible_a or not visible_b:
        return (
            "REVIEW",
            "conflict_not_explicitly_visible_in_text",
        )

    if field == "material_grade":

        grade_a = canonical_value(
            value_a
        )

        grade_b = canonical_value(
            value_b
        )

        generic_a = (
            grade_a
            in GENERIC_MATERIAL_GRADES
        )

        generic_b = (
            grade_b
            in GENERIC_MATERIAL_GRADES
        )

        if generic_a != generic_b:
            return (
                "REVIEW",
                "generic_vs_specific_material_grade",
            )

    return (
        "KEEP",
        "explicit_visible_technical_conflict",
    )

def value_counts(
    dataframe: pd.DataFrame,
    column: str,
) -> dict[str, int]:

    if (
        dataframe.empty
        or column not in dataframe.columns
    ):
        return {}

    values = (
        dataframe[column]
        .fillna("UNKNOWN")
        .astype(str)
        .str.strip()
        .replace("", "UNKNOWN")
    )

    return {
        str(key): int(value)
        for key, value
        in values.value_counts().items()
    }

def main() -> None:

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not INPUT_CSV.is_file():
        raise FileNotFoundError(
            "Mined hard-negative CSV not found:\n"
            f"{INPUT_CSV.resolve()}"
        )

    print("=" * 78)
    print("MIRA — STRICT HARD-NEGATIVE AUDIT")
    print("=" * 78)

    print("\nInput:")
    print(
        INPUT_CSV.resolve()
    )

    print(
        "\nLoading mined hard negatives..."
    )

    df = pd.read_csv(
        INPUT_CSV,
        low_memory=False,
    )

    if df.empty:
        raise ValueError(
            "Input hard-negative file is empty."
        )

    missing_columns = (
        REQUIRED_COLUMNS
        - set(df.columns)
    )

    if missing_columns:
        raise ValueError(
            "Input is missing required columns:\n"
            + "\n".join(
                f"  - {column}"
                for column
                in sorted(missing_columns)
            )
        )

    df["label"] = (
        pd.to_numeric(
            df["label"],
            errors="raise",
        )
        .astype(int)
    )

    invalid_labels = (
        ~df["label"].isin([0, 1])
    )

    if invalid_labels.any():
        raise ValueError(
            "Input contains invalid labels: "
            f"{int(invalid_labels.sum())}"
        )

    df["epoch1_similarity"] = (
        pd.to_numeric(
            df["epoch1_similarity"],
            errors="raise",
        )
        .astype(float)
    )

    if not df["epoch1_similarity"].between(
        -1.0,
        1.0,
    ).all():
        raise ValueError(
            "epoch1_similarity contains values "
            "outside [-1, 1]."
        )

    results = [
        classify_row(row)
        for _, row in df.iterrows()
    ]

    df["audit_class"] = [
        result[0]
        for result in results
    ]

    df["audit_reason"] = [
        result[1]
        for result in results
    ]

    keep = (
        df[df["audit_class"] == "KEEP"]
        .sort_values(
            "epoch1_similarity",
            ascending=False,
        )
        .copy()
    )

    review = (
        df[df["audit_class"] == "REVIEW"]
        .sort_values(
            "epoch1_similarity",
            ascending=False,
        )
        .copy()
    )

    drop = (
        df[df["audit_class"] == "DROP"]
        .sort_values(
            "epoch1_similarity",
            ascending=False,
        )
        .copy()
    )

    keep.to_csv(
        KEEP_CSV,
        index=False,
    )

    review.to_csv(
        REVIEW_CSV,
        index=False,
    )

    drop.to_csv(
        DROP_CSV,
        index=False,
    )

    summary = {
        "input": str(
            INPUT_CSV.resolve()
        ),
        "input_rows": int(
            len(df)
        ),
        "counts": {
            "KEEP": int(
                len(keep)
            ),
            "REVIEW": int(
                len(review)
            ),
            "DROP": int(
                len(drop)
            ),
        },
        "keep_fields": value_counts(
            keep,
            "hard_negative_field",
        ),
        "keep_reasons": value_counts(
            keep,
            "audit_reason",
        ),
        "review_fields": value_counts(
            review,
            "hard_negative_field",
        ),
        "review_reasons": value_counts(
            review,
            "audit_reason",
        ),
        "drop_fields": value_counts(
            drop,
            "hard_negative_field",
        ),
        "drop_reasons": value_counts(
            drop,
            "audit_reason",
        ),
        "policy": {
            "unrecognized_field": "DROP",
            "missing_conflict_value": "DROP",
            "normalized_equal": "DROP",
            "unit_reference_numeric": "REVIEW",
            "unsupported_field": "REVIEW",
            "both_conflict_values_visible": "KEEP",
            "generic_vs_specific_material_grade": "REVIEW",
            "ambiguous_conflict": "REVIEW",
        },
        "warning": (
            "KEEP/REVIEW/DROP are audit classifications "
            "and are not automatic ground-truth relabels."
        ),
        "outputs": {
            "keep": str(
                KEEP_CSV.resolve()
            ),
            "review": str(
                REVIEW_CSV.resolve()
            ),
            "drop": str(
                DROP_CSV.resolve()
            ),
            "summary": str(
                SUMMARY_JSON.resolve()
            ),
        },
    }

    SUMMARY_JSON.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # Final output
    # --------------------------------------------------------

    print("\n" + "=" * 78)
    print("STRICT AUDIT COMPLETE")
    print("=" * 78)

    print(
        f"Input rows:       {len(df):,}"
    )

    print(
        f"KEEP candidates:  {len(keep):,}"
    )

    print(
        f"REVIEW rows:      {len(review):,}"
    )

    print(
        f"DROP candidates:  {len(drop):,}"
    )

    print("\nKEEP:")
    print(
        KEEP_CSV.resolve()
    )

    print("\nREVIEW:")
    print(
        REVIEW_CSV.resolve()
    )

    print("\nDROP:")
    print(
        DROP_CSV.resolve()
    )

    print("\nSUMMARY:")
    print(
        SUMMARY_JSON.resolve()
    )

    print("=" * 78)


if __name__ == "__main__":
    main()