from __future__ import annotations

import gc
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sentence_transformers import SentenceTransformer

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parents[3]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DATA_PATH = BASE_DIR / "train_data" / "training" / "Training_Pairs_MIRA_FINAL.csv"
EPOCH1_MODEL_DIR = BASE_DIR / "qwen_models" / "epoch1_frozen" / "best"
RESULTS_DIR = BASE_DIR / "results" / "epoch2"
OUTPUT_CSV = RESULTS_DIR / "epoch1_train_hard_negative_failures.csv"
OUTPUT_JSON = RESULTS_DIR / "hard_negative_mining_summary.json"

MAX_SEQ_LENGTH = 256
BATCH_SIZE = 4

HIGH_SCORE_THRESHOLD = 0.85
EXPECTED_EMBEDDING_DIM = 1024

HARD_NEGATIVE_PATTERN = re.compile(r"(?:^|[_\-\s])HN(?:[_\-\s]|$)", re.IGNORECASE)

REQUIRED_COLUMNS = {"desc_a", "desc_b", "label", "split", "pair_type"}


def extract_hard_negative_mask(dataframe: pd.DataFrame) -> np.ndarray:
    pair_types = dataframe["pair_type"].fillna("").astype(str).str.strip()
    return pair_types.str.contains(HARD_NEGATIVE_PATTERN, na=False).to_numpy()


def normalize_descriptions(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = dataframe.copy()

    result["desc_a"] = (
        result["desc_a"].fillna("").astype(str).map(lambda value: " ".join(value.strip().split()))
    )
    result["desc_b"] = (
        result["desc_b"].fillna("").astype(str).map(lambda value: " ".join(value.strip().split()))
    )

    if (result["desc_a"] == "").any():
        raise ValueError("desc_a contains empty descriptions.")

    if (result["desc_b"] == "").any():
        raise ValueError("desc_b contains empty descriptions.")

    return result


def encode_unique_descriptions(model: SentenceTransformer, texts: list[str]) -> dict[str, np.ndarray]:
    if not texts:
        raise ValueError("No descriptions were provided for encoding.")

    print(f"Unique descriptions to encode: {len(texts):,}")

    embeddings = model.encode(
        texts,
        batch_size=BATCH_SIZE,
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
        raise RuntimeError("Model produced NaN or infinite embeddings.")

    return dict(zip(texts, embeddings))


def score_pairs(dataframe: pd.DataFrame, embedding_map: dict[str, np.ndarray]) -> np.ndarray:
    descriptions_a = dataframe["desc_a"]
    descriptions_b = dataframe["desc_b"]

    missing_a = ~descriptions_a.isin(embedding_map)
    missing_b = ~descriptions_b.isin(embedding_map)

    if missing_a.any() or missing_b.any():
        raise RuntimeError("Some descriptions are missing from the embedding cache.")

    embeddings_a = np.stack(descriptions_a.map(embedding_map).to_numpy()).astype(np.float32)
    embeddings_b = np.stack(descriptions_b.map(embedding_map).to_numpy()).astype(np.float32)

    scores = np.einsum("ij,ij->i", embeddings_a, embeddings_b)
    scores = np.asarray(scores, dtype=np.float32)

    if not np.isfinite(scores).all():
        raise RuntimeError("Similarity scores contain NaN or infinite values.")

    return np.clip(scores, -1.0, 1.0)


def value_counts_dict(dataframe: pd.DataFrame, column: str) -> dict[str, int]:
    if column not in dataframe.columns:
        return {}

    values = (
        dataframe[column]
        .fillna("UNKNOWN")
        .astype(str)
        .str.strip()
        .replace("", "UNKNOWN")
    )

    return {str(key): int(value) for key, value in values.value_counts().to_dict().items()}


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print("MIRA — EPOCH 1 TRAIN HARD-NEGATIVE MINER")
    print("=" * 78)

    print("\nDataset:")
    print(DATA_PATH.resolve())

    print("\nFrozen Epoch-1 model:")
    print(EPOCH1_MODEL_DIR.resolve())

    if not DATA_PATH.is_file():
        raise FileNotFoundError(f"Training dataset not found:\n{DATA_PATH.resolve()}")

    if not EPOCH1_MODEL_DIR.is_dir():
        raise FileNotFoundError(
            f"Frozen Epoch-1 model directory not found:\n{EPOCH1_MODEL_DIR.resolve()}"
        )

    print("\nLoading frozen dataset...")

    dataframe = pd.read_csv(DATA_PATH, low_memory=False)

    missing_columns = REQUIRED_COLUMNS - set(dataframe.columns)
    if missing_columns:
        raise ValueError(
            "Dataset is missing required columns:\n"
            + "\n".join(f"  - {column}" for column in sorted(missing_columns))
        )

    dataframe["split"] = dataframe["split"].fillna("").astype(str).str.strip().str.lower()
    dataframe["label"] = pd.to_numeric(dataframe["label"], errors="raise").astype(int)

    invalid_labels = ~dataframe["label"].isin([0, 1])
    if invalid_labels.any():
        raise ValueError(f"Found {int(invalid_labels.sum())} invalid labels.")

    train_df = dataframe[dataframe["split"] == "train"].copy()
    if train_df.empty:
        raise RuntimeError("TRAIN split is empty.")

    train_df = normalize_descriptions(train_df)

    hard_mask = extract_hard_negative_mask(train_df)
    hard_df = train_df.loc[hard_mask].copy()

    if hard_df.empty:
        raise RuntimeError("No HN rows were found in the TRAIN split.")

    invalid_hard_labels = hard_df["label"].to_numpy(dtype=np.int64) != 0
    if invalid_hard_labels.any():
        raise ValueError("Hard-negative TRAIN rows must all have label=0.")

    print(f"\nTRAIN rows:        {len(train_df):,}")
    print(f"TRAIN HN rows:     {len(hard_df):,}")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"\nLoading frozen Epoch-1 model on {device}...")

    model = SentenceTransformer(str(EPOCH1_MODEL_DIR), device=device)
    model.max_seq_length = MAX_SEQ_LENGTH
    model.eval()

    print(f"Model device: {model.device}")

    unique_texts = list(
        pd.unique(pd.concat([hard_df["desc_a"], hard_df["desc_b"]], ignore_index=True))
    )

    print(f"Unique HN descriptions: {len(unique_texts):,}")

    start = time.perf_counter()

    with torch.inference_mode():
        embedding_map = encode_unique_descriptions(model, unique_texts)

    encoding_seconds = time.perf_counter() - start
    print(f"\nEncoding time: {encoding_seconds:.2f} seconds")

    print("\nScoring TRAIN hard negatives...")
    scores = score_pairs(hard_df, embedding_map)
    hard_df["epoch1_similarity"] = scores

    failure_mask = hard_df["epoch1_similarity"] >= HIGH_SCORE_THRESHOLD
    failures = hard_df.loc[failure_mask].copy().sort_values("epoch1_similarity", ascending=False)

    total_hard_negatives = len(hard_df)
    failure_count = len(failures)
    failure_rate = failure_count / total_hard_negatives if total_hard_negatives > 0 else 0.0

    print(f"\nHard negatives total: {total_hard_negatives:,}")
    print(f"Hard negatives >= {HIGH_SCORE_THRESHOLD:.2f}: {failure_count:,}")
    print(f"False-high-score rate: {failure_rate:.4%}")

    preferred_columns = [
        "pair_id",
        "desc_a",
        "desc_b",
        "label",
        "pair_type",
        "difficulty",
        "category",
        "cpse_a",
        "cpse_b",
        "hard_negative_reason",
        "hard_negative_field",
        "source_a",
        "source_b",
        "dataset_version",
        "tmk_a",
        "tmk_b",
        "material_code_a",
        "material_code_b",
        "epoch1_similarity",
    ]

    existing_columns = [column for column in preferred_columns if column in failures.columns]
    if not existing_columns:
        raise RuntimeError("No output columns available for the failure CSV.")

    failures[existing_columns].to_csv(OUTPUT_CSV, index=False)

    all_hn_similarity = hard_df["epoch1_similarity"].to_numpy(dtype=np.float32)

    summary = {
        "model": {
            "type": "Qwen3-Embedding-0.6B fine-tuned Epoch-1",
            "path": str(EPOCH1_MODEL_DIR.resolve()),
            "max_seq_length": MAX_SEQ_LENGTH,
            "embedding_dimension": EXPECTED_EMBEDDING_DIM,
        },
        "dataset": {
            "path": str(DATA_PATH.resolve()),
            "train_rows": int(len(train_df)),
            "train_hard_negative_rows": int(total_hard_negatives),
            "dev_touched": False,
            "heldout_touched": False,
        },
        "mining": {
            "threshold": HIGH_SCORE_THRESHOLD,
            "false_high_score_count": int(failure_count),
            "false_high_score_rate": float(failure_rate),
            "similarity_min": float(all_hn_similarity.min()),
            "similarity_mean": float(all_hn_similarity.mean()),
            "similarity_median": float(np.median(all_hn_similarity)),
            "similarity_p90": float(np.percentile(all_hn_similarity, 90)),
            "similarity_max": float(all_hn_similarity.max()),
            "encoding_seconds": float(encoding_seconds),
        },
        "failure_breakdown": {
            "hard_negative_field": value_counts_dict(failures, "hard_negative_field"),
            "hard_negative_reason": value_counts_dict(failures, "hard_negative_reason"),
            "category": value_counts_dict(failures, "category"),
            "pair_type": value_counts_dict(failures, "pair_type"),
        },
        "outputs": {
            "failure_csv": str(OUTPUT_CSV.resolve()),
            "summary_json": str(OUTPUT_JSON.resolve()),
        },
    }

    OUTPUT_JSON.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )

    del model
    del embedding_map
    gc.collect()

    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    print("\n" + "=" * 78)
    print("HARD-NEGATIVE MINING FINISHED")
    print("=" * 78)
    print(f"Failures CSV:\n{OUTPUT_CSV.resolve()}")
    print(f"\nSummary JSON:\n{OUTPUT_JSON.resolve()}")
    print(f"\nFalse-high-score rate: {failure_rate:.4%}")
    print("=" * 78)


if __name__ == "__main__":
    main()

