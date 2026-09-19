from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sentence_transformers import SentenceTransformer

BASE_DIR = Path(__file__).resolve().parent

DATA_PATH = BASE_DIR / "train_data" / "training" / "Training_Pairs_MIRA_FINAL.csv"
MODEL_DIR = BASE_DIR / "qwen_models" / "epoch1_frozen" / "best"
OUTPUT_DIR = BASE_DIR / "results" / "epoch2"

KEEP_CSV = OUTPUT_DIR / "hn_true_keep_all.csv"
REVIEW_CSV = OUTPUT_DIR / "hn_review_all.csv"
DROP_CSV = OUTPUT_DIR / "hn_drop_all.csv"
SUMMARY_JSON = OUTPUT_DIR / "all_hard_negative_audit_summary.json"

DEFAULT_MAX_SEQ_LENGTH = 256
DEFAULT_BATCH_SIZE = 4

HIGH_SCORE_THRESHOLD = 0.85
EXPECTED_EMBEDDING_DIM = 1024
LOW_SCORE_BOUNDARY = 0.70

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

MISSING_VALUES = {"", "-", "N/A", "NA", "NONE", "NULL", "UNKNOWN"}

GENERIC_MATERIAL_GRADES = {"SS", "CS", "GI", "AL", "CU"}


def is_hard_negative_pair_type(value: object) -> bool:
    if pd.isna(value):
        return False

    return str(value).strip().upper().startswith("HN_")


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

    return re.sub(r"[^A-Z0-9.]+", "", str(value).strip().upper())


def canonical_dimension(value: object) -> str:
    if is_missing_value(value):
        return ""

    text = str(value).strip().upper()

    match = re.fullmatch(r"DN\s*(\d+(?:\.\d+)?)", text)
    if match:
        return f"NB{match.group(1)}"

    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*NB", text)
    if match:
        return f"NB{match.group(1)}"

    return canonical_value(text)


def normalize_for_pair_identity(value: object) -> str:
    if is_missing_value(value):
        return ""

    text = str(value).strip().upper()

    text = re.sub(r"\bPN\s+[A-Z0-9][A-Z0-9._/-]*", " ", text)
    text = re.sub(r"\bMAKE\s+[A-Z0-9&._/-]+", " ", text)
    text = re.sub(r"\bFOR\s+UNIT\s*[-/]?\s*[A-Z0-9]+", " ", text)
    text = re.sub(r"\bOR\s+EQUIVALENT\b", " ", text)
    text = re.sub(r"\bSUPPLY\s+OF\b", " ", text)
    text = re.sub(r"\bSHORT\s+DESCRIPTION\s*:\s*", " ", text)
    text = re.sub(r"\bDN\s*(\d+(?:\.\d+)?)\b", r"NB\1", text)
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s*NB\b", r"NB\1", text)
    text = re.sub(r"[^A-Z0-9.]+", "", text)

    return text


CONFLICT_REASON_PATTERN = re.compile(
    r"conflicting\s+([a-z_]+):\s+a='([^']*)'\s+vs\s+b='([^']*)'",
    re.IGNORECASE,
)


def extract_explicit_conflict(reason: object) -> tuple[str, str, str] | None:
    if is_missing_value(reason):
        return None

    match = CONFLICT_REASON_PATTERN.search(str(reason))
    if match is None:
        return None

    return (
        match.group(1).strip().lower(),
        match.group(2).strip(),
        match.group(3).strip(),
    )


def dimension_visible(value: str, description: str) -> bool:
    text = description.upper()

    match = re.fullmatch(r"DN\s*(\d+(?:\.\d+)?)", value.upper())
    if match:
        number = match.group(1)
        return bool(
            re.search(rf"(?<![A-Z0-9])DN\s*{re.escape(number)}(?![A-Z0-9])", text)
            or re.search(rf"(?<![A-Z0-9]){re.escape(number)}\s*NB(?![A-Z0-9])", text)
        )

    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*NB", value.upper())
    if match:
        number = match.group(1)
        return bool(
            re.search(rf"(?<![A-Z0-9])DN\s*{re.escape(number)}(?![A-Z0-9])", text)
            or re.search(rf"(?<![A-Z0-9]){re.escape(number)}\s*NB(?![A-Z0-9])", text)
        )

    match = re.fullmatch(r"M\s*(\d+(?:\.\d+)?)\s*X\s*(\d+(?:\.\d+)?)", value.upper())
    if match:
        diameter, length = match.groups()
        return bool(
            re.search(
                rf"(?<![A-Z0-9])M\s*{re.escape(diameter)}\s*X\s*{re.escape(length)}(?![A-Z0-9])",
                text,
            )
        )

    return False


def size_or_model_visible(value: str, description: str) -> bool:
    text = description.upper()
    value_upper = value.strip().upper()

    if re.fullmatch(r"\d+(?:\.\d+)?", value_upper):
        return False

    if re.fullmatch(r"CAT\s*[-/]?\s*\d+(?:\.\d+)?", value_upper):
        number = re.search(r"\d+(?:\.\d+)?", value_upper).group(0)
        return bool(re.search(rf"\bCAT\s*[-/]?\s*{re.escape(number)}\b", text))

    if re.fullmatch(r"MS\s*[-/]?\s*\d+(?:\.\d+)?", value_upper):
        number = re.search(r"\d+(?:\.\d+)?", value_upper).group(0)
        return bool(re.search(rf"\bMS\s*[-/]?\s*{re.escape(number)}\b", text))

    if re.fullmatch(r"MODEL\s*[-:]?\s*[A-Z0-9._/-]+", value_upper):
        canonical = canonical_value(value_upper)
        return canonical in canonical_value(text)

    canonical = canonical_value(value_upper)
    if len(canonical) < 2:
        return False

    canonical_text = canonical_value(text)

    return bool(re.search(rf"(?<![A-Z0-9]){re.escape(canonical)}(?![A-Z0-9])", canonical_text))


def material_grade_visible(value: str, description: str) -> bool:
    text = description.upper()
    canonical = canonical_value(value)

    match = re.fullmatch(r"(SS|CS|GI|AL|CU)(\d{2,4})", canonical)
    if match:
        family, grade = match.groups()
        return bool(re.search(rf"(?<![A-Z0-9]){family}\s*[-/]?\s*{grade}(?![A-Z0-9])", text))

    if canonical in GENERIC_MATERIAL_GRADES:
        generic_present = bool(
            re.search(rf"(?<![A-Z0-9]){re.escape(canonical)}(?![A-Z0-9])", text)
        )
        specific_present = bool(
            re.search(
                rf"(?<![A-Z0-9]){re.escape(canonical)}\s*[-/]?\s*\d{{2,4}}(?![A-Z0-9])",
                text,
            )
        )
        return generic_present and not specific_present

    return bool(
        re.search(rf"(?<![A-Z0-9]){re.escape(value)}(?![A-Z0-9])", text, flags=re.IGNORECASE)
    )


def technical_value_visible(value: object, description: object, field: str) -> bool:
    if is_missing_value(value):
        return False

    description_text = "" if pd.isna(description) else str(description)
    value_text = str(value).strip().upper()

    if field == "dimensions":
        return dimension_visible(value_text, description_text)

    if field == "size_or_model":
        return size_or_model_visible(value_text, description_text)

    if field == "material_grade":
        return material_grade_visible(value_text, description_text)

    if field == "schedule":
        match = re.fullmatch(r"(?:SCH(?:EDULE)?)\s*(\d+)", value_text)
        if match:
            number = match.group(1)
            return bool(
                re.search(
                    rf"(?<![A-Z0-9])(?:SCH|SCHEDULE)\s*{re.escape(number)}(?![A-Z0-9])",
                    description_text,
                    flags=re.IGNORECASE,
                )
            )

    canonical = canonical_value(value_text)
    if not canonical:
        return False

    canonical_description = canonical_value(description_text)

    return bool(
        re.search(rf"(?<![A-Z0-9]){re.escape(canonical)}(?![A-Z0-9])", canonical_description)
    )


def classify_row(row: pd.Series) -> pd.Series:
    if int(row["label"]) != 0:
        return pd.Series(["REVIEW", "label_not_zero"])

    if not is_hard_negative_pair_type(row["pair_type"]):
        return pd.Series(["REVIEW", "pair_type_not_hn"])

    field = str(row["hard_negative_field"]).strip().lower()

    if field == "unrecognized_field":
        return pd.Series(["DROP", "critical_difference_not_text_visible"])

    if field not in LEARNABLE_FIELDS:
        return pd.Series(["REVIEW", "unsupported_hard_negative_field"])

    conflict = extract_explicit_conflict(row["hard_negative_reason"])
    if conflict is None:
        return pd.Series(["REVIEW", "no_explicit_conflict_values"])

    reason_field, value_a, value_b = conflict

    if reason_field != field:
        return pd.Series(["REVIEW", "reason_field_mismatch"])

    if is_missing_value(value_a) or is_missing_value(value_b):
        return pd.Series(["DROP", "one_side_missing_value"])

    if field == "dimensions":
        canonical_a = canonical_dimension(value_a)
        canonical_b = canonical_dimension(value_b)
    else:
        canonical_a = canonical_value(value_a)
        canonical_b = canonical_value(value_b)

    if canonical_a == canonical_b:
        return pd.Series(["DROP", "values_normalize_equal"])

    if field == "size_or_model":
        if re.fullmatch(r"\d+(?:\.\d+)?", value_a.strip()) or re.fullmatch(
            r"\d+(?:\.\d+)?", value_b.strip()
        ):
            desc_a = str(row["desc_a"])
            desc_b = str(row["desc_b"])

            if re.search(
                rf"\bFOR\s+UNIT\s*[-/]?\s*{re.escape(value_a.strip())}\b",
                desc_a,
                flags=re.IGNORECASE,
            ) or re.search(
                rf"\bFOR\s+UNIT\s*[-/]?\s*{re.escape(value_b.strip())}\b",
                desc_b,
                flags=re.IGNORECASE,
            ):
                return pd.Series(["REVIEW", "numeric_value_may_be_unit_reference"])

    visible_a = technical_value_visible(value_a, row["desc_a"], field)
    visible_b = technical_value_visible(value_b, row["desc_b"], field)

    if not visible_a or not visible_b:
        return pd.Series(["REVIEW", "conflict_not_explicitly_visible_in_text"])

    if field == "material_grade":
        grade_a = canonical_value(value_a)
        grade_b = canonical_value(value_b)

        generic_a = grade_a in GENERIC_MATERIAL_GRADES
        generic_b = grade_b in GENERIC_MATERIAL_GRADES

        if generic_a != generic_b:
            return pd.Series(["REVIEW", "generic_vs_specific_material_grade"])

    return pd.Series(["KEEP", "explicit_visible_technical_conflict"])


def load_model(model_dir: Path, max_seq_length: int) -> SentenceTransformer:
    if not model_dir.is_dir():
        raise FileNotFoundError(f"Frozen Epoch-1 model not found:\n{model_dir.resolve()}")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"\nLoading Epoch-1 model on {device}...")

    model = SentenceTransformer(str(model_dir), device=device)
    model.max_seq_length = max_seq_length
    model.eval()

    try:
        embedding_dimension = int(model.get_sentence_embedding_dimension())
    except (AttributeError, TypeError, ValueError):
        embedding_dimension = None

    if embedding_dimension is not None and embedding_dimension != EXPECTED_EMBEDDING_DIM:
        raise RuntimeError(
            f"Unexpected embedding dimension: {embedding_dimension}. "
            f"Expected {EXPECTED_EMBEDDING_DIM}."
        )

    print(f"Model device: {model.device}")

    return model


def encode_unique_descriptions(
    model: SentenceTransformer, texts: list[str], batch_size: int
) -> dict[str, np.ndarray]:
    if not texts:
        raise ValueError("No descriptions to encode.")

    print(f"Unique descriptions to encode: {len(texts):,}")

    with torch.inference_mode():
        embeddings = model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

    embeddings = np.asarray(embeddings, dtype=np.float32)

    if embeddings.ndim != 2:
        raise RuntimeError(f"Unexpected embedding shape: {embeddings.shape}")

    if embeddings.shape[1] != EXPECTED_EMBEDDING_DIM:
        raise RuntimeError(
            f"Unexpected embedding dimension: {embeddings.shape[1]}. "
            f"Expected {EXPECTED_EMBEDDING_DIM}."
        )

    if not np.isfinite(embeddings).all():
        raise RuntimeError("Embedding matrix contains NaN or infinite values.")

    return dict(zip(texts, embeddings))


def score_pairs(dataframe: pd.DataFrame, embedding_map: dict[str, np.ndarray]) -> np.ndarray:
    missing_a = ~dataframe["desc_a"].isin(embedding_map)
    missing_b = ~dataframe["desc_b"].isin(embedding_map)

    if missing_a.any() or missing_b.any():
        raise RuntimeError("Some descriptions are missing from the embedding cache.")

    embeddings_a = np.stack(dataframe["desc_a"].map(embedding_map).to_numpy()).astype(np.float32)
    embeddings_b = np.stack(dataframe["desc_b"].map(embedding_map).to_numpy()).astype(np.float32)

    scores = np.einsum("ij,ij->i", embeddings_a, embeddings_b)
    scores = np.asarray(scores, dtype=np.float32)

    if not np.isfinite(scores).all():
        raise RuntimeError("Similarity scores contain NaN or infinity.")

    return np.clip(scores, -1.0, 1.0)


def deduplicate_reverse_pairs(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe.copy()

    result = dataframe.copy()

    norm_a = result["desc_a"].map(normalize_for_pair_identity)
    norm_b = result["desc_b"].map(normalize_for_pair_identity)

    key_low = np.where(norm_a <= norm_b, norm_a, norm_b)
    key_high = np.where(norm_a <= norm_b, norm_b, norm_a)

    result["_reverse_pair_key"] = list(zip(key_low, key_high))

    result = (
        result.sort_values("epoch1_similarity", ascending=False)
        .drop_duplicates(subset=["_reverse_pair_key"], keep="first")
        .drop(columns=["_reverse_pair_key"])
    )

    return result


def value_counts(dataframe: pd.DataFrame, column: str) -> dict[str, int]:
    if dataframe.empty or column not in dataframe.columns:
        return {}

    values = (
        dataframe[column]
        .fillna("UNKNOWN")
        .astype(str)
        .str.strip()
        .replace("", "UNKNOWN")
    )

    return {str(key): int(value) for key, value in values.value_counts().to_dict().items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit all TRAIN hard negatives using the frozen Epoch-1 MIRA model."
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Sentence-transformer encoding batch size. Default: 4",
    )

    parser.add_argument(
        "--max-seq-length",
        type=int,
        default=DEFAULT_MAX_SEQ_LENGTH,
        help="Maximum sequence length. Default: 256",
    )

    parser.add_argument(
        "--threshold",
        type=float,
        default=HIGH_SCORE_THRESHOLD,
        help="Semantic similarity threshold used to mark especially difficult HNs. Default: 0.85",
    )

    args = parser.parse_args()

    if args.batch_size < 1:
        parser.error("--batch-size must be >= 1")

    if args.max_seq_length < 1:
        parser.error("--max-seq-length must be >= 1")

    if not (-1.0 <= args.threshold <= 1.0):
        parser.error("--threshold must be between -1 and 1")

    return args


def main() -> None:
    args = parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print("MIRA — ALL TRAIN HARD-NEGATIVE AUDIT")
    print("=" * 78)

    print("\nDataset:")
    print(DATA_PATH.resolve())

    print("\nFrozen Epoch-1 model:")
    print(MODEL_DIR.resolve())

    if not DATA_PATH.is_file():
        raise FileNotFoundError(f"Training dataset not found:\n{DATA_PATH.resolve()}")

    if not MODEL_DIR.is_dir():
        raise FileNotFoundError(f"Frozen Epoch-1 model not found:\n{MODEL_DIR.resolve()}")

    print("\nLoading training dataset...")

    dataframe = pd.read_csv(DATA_PATH, low_memory=False)

    if dataframe.empty:
        raise RuntimeError("Training dataset is empty.")

    missing_columns = {
        "desc_a",
        "desc_b",
        "label",
        "pair_type",
        "hard_negative_field",
        "hard_negative_reason",
        "split",
    } - set(dataframe.columns)

    if missing_columns:
        raise ValueError(
            "Dataset is missing required columns:\n"
            + "\n".join(f"  - {column}" for column in sorted(missing_columns))
        )

    dataframe["split"] = dataframe["split"].fillna("").astype(str).str.strip().str.lower()
    dataframe["label"] = pd.to_numeric(dataframe["label"], errors="raise").astype(int)

    invalid_labels = ~dataframe["label"].isin([0, 1])
    if invalid_labels.any():
        raise ValueError(f"Invalid labels found: {int(invalid_labels.sum())}")

    train_df = dataframe[dataframe["split"] == "train"].copy()
    if train_df.empty:
        raise RuntimeError("TRAIN split is empty.")

    hn_mask = train_df["pair_type"].map(is_hard_negative_pair_type)
    hn_df = train_df.loc[hn_mask].copy()

    if hn_df.empty:
        raise RuntimeError("No hard negatives found in TRAIN.")

    nonzero_hn_labels = hn_df["label"].to_numpy(dtype=np.int64) != 0
    if nonzero_hn_labels.any():
        raise ValueError(
            f"TRAIN HN rows must have label=0. Found {int(nonzero_hn_labels.sum())} invalid HNs."
        )

    hn_df["desc_a"] = (
        hn_df["desc_a"].fillna("").astype(str).map(lambda value: " ".join(value.strip().split()))
    )
    hn_df["desc_b"] = (
        hn_df["desc_b"].fillna("").astype(str).map(lambda value: " ".join(value.strip().split()))
    )

    if hn_df["desc_a"].eq("").any():
        raise ValueError("HN TRAIN contains empty desc_a values.")

    if hn_df["desc_b"].eq("").any():
        raise ValueError("HN TRAIN contains empty desc_b values.")

    print(f"\nTRAIN rows:       {len(train_df):,}")
    print(f"TRAIN HN rows:    {len(hn_df):,}")

    print("\nRunning strict technical audit...")

    hn_df[["audit_class", "audit_reason"]] = hn_df.apply(classify_row, axis=1)

    model = load_model(MODEL_DIR, args.max_seq_length)

    unique_texts = list(
        pd.unique(pd.concat([hn_df["desc_a"], hn_df["desc_b"]], ignore_index=True))
    )

    print(f"\nUnique HN descriptions: {len(unique_texts):,}")

    embedding_map = encode_unique_descriptions(model, unique_texts, args.batch_size)
    scores = score_pairs(hn_df, embedding_map)

    hn_df["epoch1_similarity"] = scores

    hn_df["difficulty_bucket"] = pd.cut(
        hn_df["epoch1_similarity"],
        bins=[-np.inf, LOW_SCORE_BOUNDARY, args.threshold, np.inf],
        labels=[
            f"LOWER_THAN_{LOW_SCORE_BOUNDARY:.2f}",
            f"{LOW_SCORE_BOUNDARY:.2f}_TO_{args.threshold:.2f}",
            f"GE_{args.threshold:.2f}",
        ],
        right=False,
    ).astype(str)

    keep = hn_df[hn_df["audit_class"] == "KEEP"].copy()
    review = hn_df[hn_df["audit_class"] == "REVIEW"].copy()
    drop = hn_df[hn_df["audit_class"] == "DROP"].copy()

    keep_before_dedup = len(keep)
    keep = deduplicate_reverse_pairs(keep)
    keep_after_dedup = len(keep)

    keep = keep.sort_values("epoch1_similarity", ascending=False)
    review = review.sort_values("epoch1_similarity", ascending=False)
    drop = drop.sort_values("epoch1_similarity", ascending=False)

    keep.to_csv(KEEP_CSV, index=False)
    review.to_csv(REVIEW_CSV, index=False)
    drop.to_csv(DROP_CSV, index=False)

    total_hn = len(hn_df)

    valid_keep_high_score = int((keep["epoch1_similarity"] >= args.threshold).sum())
    total_high_score = int((hn_df["epoch1_similarity"] >= args.threshold).sum())

    summary = {
        "dataset": {
            "path": str(DATA_PATH.resolve()),
            "train_rows": int(len(train_df)),
            "train_hard_negative_rows": int(total_hn),
            "dev_touched": False,
            "heldout_touched": False,
        },
        "model": {
            "path": str(MODEL_DIR.resolve()),
            "type": "Qwen3-Embedding-0.6B fine-tuned Epoch-1",
            "max_seq_length": int(args.max_seq_length),
            "embedding_dimension": EXPECTED_EMBEDDING_DIM,
        },
        "audit": {
            "keep_before_reverse_dedup": int(keep_before_dedup),
            "keep_after_reverse_dedup": int(keep_after_dedup),
            "review_rows": int(len(review)),
            "drop_rows": int(len(drop)),
        },
        "semantic_distribution": {
            "all_hn_ge_threshold_count": total_high_score,
            "all_hn_ge_threshold_rate": (
                float(total_high_score / total_hn) if total_hn else 0.0
            ),
            "clean_keep_ge_threshold_count": valid_keep_high_score,
            "clean_keep_ge_threshold_rate": (
                float(valid_keep_high_score / keep_after_dedup) if keep_after_dedup else 0.0
            ),
            "threshold": float(args.threshold),
            "all_hn_similarity_min": float(hn_df["epoch1_similarity"].min()),
            "all_hn_similarity_mean": float(hn_df["epoch1_similarity"].mean()),
            "all_hn_similarity_median": float(hn_df["epoch1_similarity"].median()),
            "all_hn_similarity_p90": float(hn_df["epoch1_similarity"].quantile(0.90)),
            "all_hn_similarity_max": float(hn_df["epoch1_similarity"].max()),
        },
        "keep_fields": value_counts(keep, "hard_negative_field"),
        "keep_difficulty_buckets": value_counts(keep, "difficulty_bucket"),
        "review_fields": value_counts(review, "hard_negative_field"),
        "review_reasons": value_counts(review, "audit_reason"),
        "drop_fields": value_counts(drop, "hard_negative_field"),
        "drop_reasons": value_counts(drop, "audit_reason"),
        "outputs": {
            "keep": str(KEEP_CSV.resolve()),
            "review": str(REVIEW_CSV.resolve()),
            "drop": str(DROP_CSV.resolve()),
            "summary": str(SUMMARY_JSON.resolve()),
        },
        "warning": (
            "KEEP/REVIEW/DROP are audit classifications, "
            "not automatic ground-truth relabels."
        ),
    }

    SUMMARY_JSON.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    del model
    del embedding_map

    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    print("\n" + "=" * 78)
    print("ALL HARD-NEGATIVE AUDIT COMPLETE")
    print("=" * 78)

    print(f"TRAIN HNs:                  {total_hn:,}")
    print(f"All HNs >= {args.threshold:.2f}:        {total_high_score:,}")
    print(f"KEEP before reverse dedup:  {keep_before_dedup:,}")
    print(f"KEEP after reverse dedup:   {keep_after_dedup:,}")
    print(f"REVIEW:                     {len(review):,}")
    print(f"DROP:                       {len(drop):,}")

    print(f"\nKEEP CSV:\n{KEEP_CSV.resolve()}")
    print(f"\nREVIEW CSV:\n{REVIEW_CSV.resolve()}")
    print(f"\nDROP CSV:\n{DROP_CSV.resolve()}")
    print(f"\nSUMMARY JSON:\n{SUMMARY_JSON.resolve()}")

    print("=" * 78)


if __name__ == "__main__":
    main()
