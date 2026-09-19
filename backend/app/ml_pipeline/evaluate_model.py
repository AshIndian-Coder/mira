from __future__ import annotations

import gc
import json
import re
import time
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[3]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import torch
from sentence_transformers import SentenceTransformer

from backend.app.ml_pipeline.training_utils.dataset import (
    DEFAULT_DATA_PATH,
    load_pairs_dataframe,
)
from backend.app.ml_pipeline.training_utils.metrics import (
    calculate_binary_metrics,
    find_best_threshold,
    hard_negative_metrics,
    to_serializable,
)

MODEL_DIR = (
    Path(__file__).resolve().parent
    / "qwen_models"
    / "epoch1_frozen"
    / "best"
)

RESULTS_DIR = Path(__file__).resolve().parent / "results"

OUTPUT_PATH = RESULTS_DIR / "epoch1_heldout_evaluation.json"

MAX_SEQ_LENGTH = 256
BATCH_SIZE = 4

EXPECTED_EMBEDDING_DIM = 1024

HARD_NEGATIVE_PATTERN = re.compile(
    r"(?:^|[_\-\s])HN(?:[_\-\s]|$)",
    re.IGNORECASE,
)


def extract_hard_negative_mask(df: pd.DataFrame) -> np.ndarray:
    pair_types = (
        df["pair_type"]
        .fillna("")
        .astype(str)
        .str.upper()
    )

    return pair_types.str.contains(
        HARD_NEGATIVE_PATTERN,
        regex=True,
        na=False,
    ).to_numpy()


def encode_descriptions(
    model: SentenceTransformer,
    texts: list[str],
) -> dict[str, np.ndarray]:

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
        raise RuntimeError(
            f"Unexpected embedding shape: {embeddings.shape}"
        )

    if embeddings.shape[1] != EXPECTED_EMBEDDING_DIM:
        raise RuntimeError(
            "Unexpected embedding dimension: "
            f"{embeddings.shape[1]}. "
            f"Expected: {EXPECTED_EMBEDDING_DIM}"
        )

    return {
        text: embedding
        for text, embedding in zip(texts, embeddings)
    }


def score_pairs(
    df: pd.DataFrame,
    embedding_map: dict[str, np.ndarray],
) -> np.ndarray:

    missing_a = ~df["desc_a"].isin(embedding_map)
    missing_b = ~df["desc_b"].isin(embedding_map)

    if missing_a.any() or missing_b.any():
        raise KeyError(
            "Some descriptions are missing from the embedding "
            f"cache: {int(missing_a.sum() + missing_b.sum())} "
            "occurrences."
        )

    embeddings_a = np.stack(
        df["desc_a"].map(embedding_map).to_numpy()
    ).astype(np.float32)

    embeddings_b = np.stack(
        df["desc_b"].map(embedding_map).to_numpy()
    ).astype(np.float32)

    scores = np.einsum(
        "ij,ij->i",
        embeddings_a,
        embeddings_b,
    )

    return np.clip(scores, -1.0, 1.0).astype(np.float32)


def main() -> None:

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print("MIRA — EPOCH 1 HELD-OUT EVALUATION")
    print("=" * 78)

    print("\nModel:")
    print(MODEL_DIR.resolve())

    print("\nDataset:")
    print(Path(DEFAULT_DATA_PATH).resolve())

    if not MODEL_DIR.exists():
        raise FileNotFoundError(
            f"Frozen Epoch-1 model not found:\n"
            f"{MODEL_DIR.resolve()}"
        )

    if not Path(DEFAULT_DATA_PATH).exists():
        raise FileNotFoundError(
            f"Dataset not found:\n"
            f"{Path(DEFAULT_DATA_PATH).resolve()}"
        )

    print("\nLoading frozen MIRA dataset...")

    df = load_pairs_dataframe()

    dev_df = df[df["split"] == "dev"].copy()
    heldout_df = df[df["split"] == "heldout"].copy()

    print(f"DEV rows:      {len(dev_df):,}")
    print(f"HELD-OUT rows: {len(heldout_df):,}")

    if dev_df.empty:
        raise RuntimeError("DEV split is empty.")

    if heldout_df.empty:
        raise RuntimeError("HELD-OUT split is empty.")

    print("\nLoading frozen Epoch-1 model...")

    model = SentenceTransformer(
        str(MODEL_DIR),
        device="cuda" if torch.cuda.is_available() else "cpu",
    )

    model.max_seq_length = MAX_SEQ_LENGTH
    model.eval()

    print(f"Model device: {model.device}")

    evaluation_df = pd.concat(
        [dev_df, heldout_df],
        ignore_index=True,
    )

    unique_texts = list(
        pd.unique(
            pd.concat(
                [
                    evaluation_df["desc_a"],
                    evaluation_df["desc_b"],
                ],
                ignore_index=True,
            )
        )
    )

    start = time.perf_counter()

    with torch.no_grad():
        embedding_map = encode_descriptions(
            model,
            unique_texts,
        )

    encoding_seconds = time.perf_counter() - start

    print(f"\nEncoding time: {encoding_seconds:.2f} seconds")

    print("\n" + "-" * 78)
    print("DEV EVALUATION")
    print("-" * 78)

    dev_scores = score_pairs(dev_df, embedding_map)

    dev_labels = dev_df["label"].to_numpy(dtype=np.int64)

    dev_best = find_best_threshold(
        dev_scores,
        dev_labels,
        objective="f1",
    )

    dev_threshold = float(dev_best.threshold)

    dev_hn_mask = extract_hard_negative_mask(dev_df)

    if dev_hn_mask.any():
        invalid_hn_labels = dev_labels[dev_hn_mask] != 0

        if invalid_hn_labels.any():
            raise ValueError(
                "DEV hard-negative rows must have label=0."
            )

        dev_hn = hard_negative_metrics(
            dev_scores[dev_hn_mask],
            dev_labels[dev_hn_mask],
            0.85,
        )
    else:
        dev_hn = {
            "rows": 0,
            "status": "NO_HARD_NEGATIVES",
        }

    print(f"DEV threshold: {dev_threshold:.3f}")
    print(f"DEV F1:        {dev_best.f1:.4f}")
    print(f"DEV precision: {dev_best.precision:.4f}")
    print(f"DEV recall:    {dev_best.recall:.4f}")
    print(
        "DEV semantic HN-FHC @ 0.85: "
        f"{dev_hn.get('false_high_confidence_rate')}"
    )

    print("\n" + "-" * 78)
    print("BLIND HELD-OUT EVALUATION")
    print("-" * 78)

    heldout_scores = score_pairs(heldout_df, embedding_map)

    heldout_labels = heldout_df["label"].to_numpy(dtype=np.int64)

    heldout_metrics = calculate_binary_metrics(
        heldout_scores,
        heldout_labels,
        dev_threshold,
    )

    heldout_hn_mask = extract_hard_negative_mask(heldout_df)
    if heldout_hn_mask.any():

        invalid_hn_labels = heldout_labels[heldout_hn_mask] != 0

        if invalid_hn_labels.any():
            raise ValueError(
                "HELD-OUT hard-negative rows must have label=0."
            )

        heldout_hn = hard_negative_metrics(
            heldout_scores[heldout_hn_mask],
            heldout_labels[heldout_hn_mask],
            0.85,
        )

    else:
        heldout_hn = {
            "rows": 0,
            "status": "NO_HARD_NEGATIVES",
        }

    print(f"Frozen DEV threshold: {dev_threshold:.3f}")
    print(f"HELD-OUT rows:       {heldout_metrics.rows:,}")
    print(f"HELD-OUT F1:         {heldout_metrics.f1:.4f}")
    print(f"HELD-OUT precision:  {heldout_metrics.precision:.4f}")
    print(f"HELD-OUT recall:     {heldout_metrics.recall:.4f}")
    print(f"HELD-OUT accuracy:   {heldout_metrics.accuracy:.4f}")
    print(
        "HELD-OUT FPR:        "
        f"{heldout_metrics.false_positive_rate}"
    )
    print(
        "HELD-OUT FNR:        "
        f"{heldout_metrics.false_negative_rate}"
    )
    print(f"HELD-OUT ROC-AUC:    {heldout_metrics.roc_auc}")
    print(
        "HELD-OUT semantic HN-FHC @ 0.85:     "
        f"{heldout_hn.get('false_high_confidence_rate')}"
    )

    embedding_dimension = int(
        next(iter(embedding_map.values())).shape[0]
    )

    result = {
        "model": {
            "path": str(MODEL_DIR.resolve()),
            "type": "Qwen3-Embedding-0.6B fine-tuned Epoch-1",
            "embedding_dimension": embedding_dimension,
        },
        "dataset": {
            "path": str(Path(DEFAULT_DATA_PATH).resolve()),
            "train_rows_excluded": int(
                (df["split"] == "train").sum()
            ),
            "dev_rows": int(len(dev_df)),
            "heldout_rows": int(len(heldout_df)),
        },
        "evaluation_protocol": {
            "threshold_selection": "DEV",
            "threshold_objective": "F1",
            "heldout_threshold_frozen": True,
        },
        "dev": {
            "threshold": dev_threshold,
            "metrics": to_serializable(dev_best),
            "hard_negative_metrics": to_serializable(dev_hn),
        },
        "heldout": {
            "threshold_used": dev_threshold,
            "metrics": to_serializable(heldout_metrics),
            "hard_negative_metrics": to_serializable(heldout_hn),
        },
        "runtime": {
            "encoding_seconds": encoding_seconds,
        },
    }

    OUTPUT_PATH.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        ),
        encoding="utf-8",
    )

    del model
    gc.collect()

    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    print("\n" + "=" * 78)
    print("EPOCH 1 HELD-OUT EVALUATION FINISHED")
    print("=" * 78)
    print("Report saved to:")
    print(OUTPUT_PATH.resolve())
    print("=" * 78)


if __name__ == "__main__":
    main()