from __future__ import annotations

import gc
import hashlib
import json
import platform
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from sentence_transformers import SentenceTransformer
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"
EXPECTED_EMBEDDING_DIM = 1024
BATCH_SIZE = 16

NORMALIZE_EMBEDDINGS = True
THRESHOLD_MIN = 0.0
THRESHOLD_MAX = 1.0
THRESHOLD_STEP = 0.001

THRESHOLD_OBJECTIVE = "f1"

OBJECTIVE_FIELDS = {
    "f1": "f1",
    "precision": "precision",
    "recall": "recall",
    "accuracy": "accuracy",
}

BASE_DIR = Path(__file__).resolve().parent

DATA_PATH = (
    BASE_DIR
    / "train_data"
    / "training"
    / "Training_Pairs_MIRA_FINAL.csv"
)

RESULTS_DIR = BASE_DIR / "results"

RESULTS_JSON = (
    RESULTS_DIR / "baseline_results.json"
)

PAIR_SCORES_CSV = (
    RESULTS_DIR / "baseline_pair_scores.csv"
)

RUNTIME_JSON = (
    RESULTS_DIR / "baseline_runtime.json"
)

REQUIRED_COLUMNS = {
    "pair_id",
    "desc_a",
    "desc_b",
    "label",
    "pair_type",
    "split",
}

@dataclass
class MetricResult:
    threshold: float

    rows: int
    positive_rows: int
    negative_rows: int

    accuracy: float
    precision: float
    recall: float
    f1: float

    false_positive_rate: float
    false_negative_rate: float

    true_positive: int
    true_negative: int
    false_positive: int
    false_negative: int

    mean_positive_similarity: float
    mean_negative_similarity: float

    positive_similarity_p10: float
    positive_similarity_p50: float
    positive_similarity_p90: float

    negative_similarity_p10: float
    negative_similarity_p50: float
    negative_similarity_p90: float

    roc_auc: float | None

def clean_text(value: Any) -> str:
    if pd.isna(value):
        return ""

    return " ".join(
        str(value)
        .strip()
        .split()
    )


def safe_rate(
    numerator: int,
    denominator: int,
) -> float:
    if denominator == 0:
        return 0.0

    return float(
        numerator / denominator
    )


def percentile_or_nan(
    values: np.ndarray,
    percentile: float,
) -> float:
    if len(values) == 0:
        return float("nan")

    return float(
        np.percentile(
            values,
            percentile,
        )
    )


def sha256_file(path: Path) -> str:

    sha = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            sha.update(chunk)

    return sha.hexdigest()


def sanitize_for_json(value: Any) -> Any:

    if isinstance(value, float):
        if np.isnan(value) or np.isinf(value):
            return None
        return value

    if isinstance(value, dict):
        return {
            key: sanitize_for_json(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            sanitize_for_json(item)
            for item in value
        ]

    return value

def load_and_validate_dataset() -> pd.DataFrame:

    print("\n[1/8] Loading frozen dataset...")

    if not DATA_PATH.exists():
        raise FileNotFoundError(
            "\nFrozen dataset not found:\n"
            f"{DATA_PATH}\n"
        )

    df = pd.read_csv(
        DATA_PATH,
        low_memory=False,
    )

    missing_columns = (
        REQUIRED_COLUMNS
        - set(df.columns)
    )

    if missing_columns:
        raise ValueError(
            "Missing required columns:\n"
            + "\n".join(
                f"  - {column}"
                for column in sorted(
                    missing_columns
                )
            )
        )

    df["split"] = (
        df["split"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    df["label"] = (
        pd.to_numeric(
            df["label"],
            errors="raise",
        )
        .astype(int)
    )

    invalid_labels = ~df[
        "label"
    ].isin([0, 1])

    if invalid_labels.any():
        raise ValueError(
            f"Found {invalid_labels.sum()} "
            "rows with invalid labels."
        )

    df["desc_a"] = df[
        "desc_a"
    ].map(clean_text)

    df["desc_b"] = df[
        "desc_b"
    ].map(clean_text)

    if (
        df["desc_a"] == ""
    ).any():

        count = int(
            (df["desc_a"] == "").sum()
        )

        raise ValueError(
            f"desc_a contains {count} empty "
            "model inputs."
        )

    if (
        df["desc_b"] == ""
    ).any():

        count = int(
            (df["desc_b"] == "").sum()
        )

        raise ValueError(
            f"desc_b contains {count} empty "
            "model inputs."
        )

    expected_splits = {
        "train",
        "dev",
        "heldout",
    }

    actual_splits = set(
        df["split"].unique()
    )

    unexpected = (
        actual_splits
        - expected_splits
    )

    if unexpected:
        raise ValueError(
            "Unexpected split names: "
            + ", ".join(
                sorted(unexpected)
            )
        )

    print(
        f"Dataset rows: {len(df):,}"
    )

    print("\nSplit distribution:")
    print(
        df["split"]
        .value_counts()
        .to_string()
    )

    print("\nLabel distribution:")
    print(
        df["label"]
        .value_counts()
        .sort_index()
        .to_string()
    )

    return df

def load_qwen() -> SentenceTransformer:

    print(
        "\n[2/8] Loading UNTRAINED "
        "Qwen3-Embedding-0.6B..."
    )

    if not torch.cuda.is_available():
        raise RuntimeError(
            "\nCUDA is not available.\n"
            "This experiment is configured to "
            "run on your NVIDIA GPU."
        )

    gpu_name = (
        torch.cuda.get_device_name(0)
    )

    print(
        f"GPU: {gpu_name}"
    )

    print(
        f"PyTorch: {torch.__version__}"
    )

    print(
        f"CUDA runtime: "
        f"{torch.version.cuda}"
    )

    model = SentenceTransformer(
        MODEL_NAME,
        device="cuda",
    )

    print(
        f"Model device: {model.device}"
    )

    return model

def encode_unique_descriptions(
    model: SentenceTransformer,
    evaluation_df: pd.DataFrame,
) -> dict[str, np.ndarray]:

    print(
        "\n[3/8] Preparing evaluation descriptions..."
    )

    text_series = pd.concat(
        [
            evaluation_df["desc_a"],
            evaluation_df["desc_b"],
        ],
        ignore_index=True,
    )

    unique_texts = (
        pd.unique(
            text_series
        )
        .tolist()
    )

    print(
        f"Description occurrences: "
        f"{len(text_series):,}"
    )

    print(
        f"Unique descriptions: "
        f"{len(unique_texts):,}"
    )

    print(
        "\n[4/8] Encoding descriptions "
        "on RTX 5050..."
    )

    print(
        f"Batch size: {BATCH_SIZE}"
    )

    start = time.perf_counter()

    embeddings = model.encode(
        unique_texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=(
            NORMALIZE_EMBEDDINGS
        ),
    )

    elapsed = (
        time.perf_counter()
        - start
    )

    if embeddings.ndim != 2:
        raise RuntimeError(
            "Unexpected embedding shape: "
            f"{embeddings.shape}"
        )

    actual_dimension = (
        embeddings.shape[1]
    )

    if (
        actual_dimension
        != EXPECTED_EMBEDDING_DIM
    ):
        raise RuntimeError(
            "Unexpected Qwen embedding "
            f"dimension: {actual_dimension}\n"
            f"Expected: {EXPECTED_EMBEDDING_DIM}"
        )

    print(
        f"Encoding time: "
        f"{elapsed:.2f} seconds"
    )

    print(
        f"Embedding matrix: "
        f"{embeddings.shape}"
    )

    embedding_map = {
        text: embedding
        for text, embedding
        in zip(
            unique_texts,
            embeddings,
        )
    }

    # Free temporary arrays.
    del embeddings
    gc.collect()

    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return embedding_map

def score_pairs(
    pair_df: pd.DataFrame,
    embedding_map: dict[str, np.ndarray],
) -> np.ndarray:

    embeddings_a = np.asarray(
        [
            embedding_map[text]
            for text in pair_df["desc_a"]
        ],
        dtype=np.float32,
    )

    embeddings_b = np.asarray(
        [
            embedding_map[text]
            for text in pair_df["desc_b"]
        ],
        dtype=np.float32,
    )

    scores = np.einsum(
        "ij,ij->i",
        embeddings_a,
        embeddings_b,
    )

    # Numerical safety.
    scores = np.clip(
        scores,
        -1.0,
        1.0,
    )

    return scores.astype(
        np.float32
    )


def calculate_metrics(
    scores: np.ndarray,
    labels: np.ndarray,
    threshold: float,
) -> MetricResult:

    predictions = (
        scores >= threshold
    ).astype(np.int64)

    tn, fp, fn, tp = confusion_matrix(
        labels,
        predictions,
        labels=[0, 1],
    ).ravel()

    accuracy = accuracy_score(
        labels,
        predictions,
    )

    precision = precision_score(
        labels,
        predictions,
        zero_division=0,
    )

    recall = recall_score(
        labels,
        predictions,
        zero_division=0,
    )

    f1 = f1_score(
        labels,
        predictions,
        zero_division=0,
    )

    positive_scores = scores[
        labels == 1
    ]

    negative_scores = scores[
        labels == 0
    ]

    if len(np.unique(labels)) < 2:
        roc_auc = None
    else:
        roc_auc = float(
            roc_auc_score(
                labels,
                scores,
            )
        )

    return MetricResult(
        threshold=float(
            threshold
        ),

        rows=int(
            len(labels)
        ),

        positive_rows=int(
            (labels == 1).sum()
        ),

        negative_rows=int(
            (labels == 0).sum()
        ),

        accuracy=float(
            accuracy
        ),

        precision=float(
            precision
        ),

        recall=float(
            recall
        ),

        f1=float(
            f1
        ),

        false_positive_rate=safe_rate(
            fp,
            fp + tn,
        ),

        false_negative_rate=safe_rate(
            fn,
            fn + tp,
        ),

        true_positive=int(tp),
        true_negative=int(tn),
        false_positive=int(fp),
        false_negative=int(fn),

        mean_positive_similarity=(
            float(
                positive_scores.mean()
            )
            if len(positive_scores)
            else float("nan")
        ),

        mean_negative_similarity=(
            float(
                negative_scores.mean()
            )
            if len(negative_scores)
            else float("nan")
        ),

        positive_similarity_p10=(
            percentile_or_nan(
                positive_scores,
                10,
            )
        ),

        positive_similarity_p50=(
            percentile_or_nan(
                positive_scores,
                50,
            )
        ),

        positive_similarity_p90=(
            percentile_or_nan(
                positive_scores,
                90,
            )
        ),

        negative_similarity_p10=(
            percentile_or_nan(
                negative_scores,
                10,
            )
        ),

        negative_similarity_p50=(
            percentile_or_nan(
                negative_scores,
                50,
            )
        ),

        negative_similarity_p90=(
            percentile_or_nan(
                negative_scores,
                90,
            )
        ),

        roc_auc=roc_auc,
    )

def select_dev_threshold(
    scores: np.ndarray,
    labels: np.ndarray,
) -> MetricResult:

    print(
        "\n[5/8] Selecting similarity threshold "
        "using DEV only..."
    )

    if THRESHOLD_OBJECTIVE not in OBJECTIVE_FIELDS:
        raise ValueError(
            "Unsupported THRESHOLD_OBJECTIVE: "
            f"{THRESHOLD_OBJECTIVE!r}. "
            f"Expected one of: {sorted(OBJECTIVE_FIELDS)}"
        )

    objective_field = OBJECTIVE_FIELDS[
        THRESHOLD_OBJECTIVE
    ]

    best: MetricResult | None = None
    num_steps = (
        int(
            round(
                (THRESHOLD_MAX - THRESHOLD_MIN)
                / THRESHOLD_STEP
            )
        )
        + 1
    )

    thresholds = np.round(
        np.linspace(
            THRESHOLD_MIN,
            THRESHOLD_MAX,
            num_steps,
        ),
        6,
    )

    for threshold in thresholds:

        result = calculate_metrics(
            scores,
            labels,
            float(threshold),
        )

        if best is None:
            best = result
            continue
        current_key = (
            getattr(result, objective_field),
            -result.false_positive_rate,
            result.precision,
        )

        best_key = (
            getattr(best, objective_field),
            -best.false_positive_rate,
            best.precision,
        )

        if current_key > best_key:
            best = result

    if best is None:
        raise RuntimeError(
            "Could not determine a DEV threshold."
        )

    return best

HARD_NEGATIVE_PATTERN = re.compile(
    r"(?:^|[_\-\s])HN(?:[_\-\s]|$)"
)


def analyze_hard_negatives(
    heldout_df: pd.DataFrame,
    heldout_scores: np.ndarray,
    threshold: float,
) -> dict[str, Any]:

    pair_types = (
        heldout_df["pair_type"]
        .fillna("")
        .astype(str)
        .str.upper()
    )

    hard_mask = pair_types.str.contains(
        HARD_NEGATIVE_PATTERN,
        regex=True,
        na=False,
    )

    hard_df = heldout_df[
        hard_mask
    ].copy()

    if hard_df.empty:
        return {
            "rows": 0,
            "status": "NO_HARD_NEGATIVES_FOUND",
        }

    positions = np.flatnonzero(
        hard_mask.to_numpy()
    )

    hard_scores = (
        heldout_scores[
            positions
        ]
    )

    hard_labels = (
        hard_df["label"]
        .to_numpy(dtype=np.int64)
    )

    predictions = (
        hard_scores >= threshold
    ).astype(np.int64)

    negative_mask = (
        hard_labels == 0
    )

    false_high_confidence = (
        (
            predictions == 1
        )
        & negative_mask
    )

    negative_count = int(
        negative_mask.sum()
    )

    false_count = int(
        false_high_confidence.sum()
    )

    return {
        "rows": int(
            len(hard_df)
        ),
        "positive_rows": int(
            (hard_labels == 1).sum()
        ),
        "negative_rows": negative_count,

        "false_high_confidence_count":
            false_count,

        "false_high_confidence_rate":
            safe_rate(
                false_count,
                negative_count,
            ),

        "mean_similarity": float(
            hard_scores.mean()
        ),

        "p50_similarity": float(
            np.percentile(
                hard_scores,
                50,
            )
        ),

        "p90_similarity": float(
            np.percentile(
                hard_scores,
                90,
            )
        ),
    }

def subgroup_metrics(
    dataframe: pd.DataFrame,
    scores: np.ndarray,
    threshold: float,
    column: str,
    min_rows: int = 20,
) -> dict[str, Any]:
    if column not in dataframe.columns:
        return {}

    values = (
        dataframe[column]
        .fillna("UNKNOWN")
        .astype(str)
    )

    results: dict[str, Any] = {}

    for value in sorted(
        values.unique()
    ):

        mask = (
            values.to_numpy()
            == value
        )

        rows = int(
            mask.sum()
        )

        if rows < min_rows:
            results[value] = {
                "rows": rows,
                "status": "INSUFFICIENT_SAMPLE",
            }
            continue

        group_labels = (
            dataframe.loc[
                mask,
                "label",
            ]
            .to_numpy(
                dtype=np.int64
            )
        )

        group_scores = (
            scores[mask]
        )

        metrics = calculate_metrics(
            group_scores,
            group_labels,
            threshold,
        )

        results[value] = asdict(
            metrics
        )

    return results


def create_cpse_pair_column(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:

    output = dataframe.copy()

    if not {
        "cpse_a",
        "cpse_b",
    }.issubset(
        output.columns
    ):
        return output

    def canonical_pair(row: pd.Series) -> str:
        raw_a = row["cpse_a"]
        raw_b = row["cpse_b"]
        a = (
            "UNKNOWN"
            if pd.isna(raw_a)
            else str(raw_a).strip()
        )

        b = (
            "UNKNOWN"
            if pd.isna(raw_b)
            else str(raw_b).strip()
        )

        return " ↔ ".join(
            sorted(
                [a, b]
            )
        )

    output["_cpse_pair"] = (
        output.apply(
            canonical_pair,
            axis=1,
        )
    )

    return output

def save_pair_scores(
    heldout_df: pd.DataFrame,
    scores: np.ndarray,
    threshold: float,
) -> None:

    output = heldout_df.copy()

    output[
        "semantic_similarity"
    ] = scores

    output[
        "baseline_prediction"
    ] = (
        scores >= threshold
    ).astype(int)

    output[
        "correct_prediction"
    ] = (
        output[
            "baseline_prediction"
        ]
        == output["label"]
    )

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
        "split",
        "semantic_similarity",
        "baseline_prediction",
        "correct_prediction",
    ]

    existing_columns = [
        column
        for column in preferred_columns
        if column in output.columns
    ]

    output[
        existing_columns
    ].to_csv(
        PAIR_SCORES_CSV,
        index=False,
    )

    print(
        "\nPair-level baseline scores saved to:"
    )

    print(
        PAIR_SCORES_CSV
    )

def main() -> None:

    overall_start = (
        time.perf_counter()
    )

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 78)
    print(
        "MIRA — QWEN3-EMBEDDING-0.6B "
        "UNTRAINED BASELINE"
    )
    print("=" * 78)
    environment = {
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),

        "pytorch": torch.__version__,

        "cuda_available": bool(
            torch.cuda.is_available()
        ),

        "cuda_runtime": (
            torch.version.cuda
        ),

        "gpu": (
            torch.cuda.get_device_name(0)
            if torch.cuda.is_available()
            else None
        ),
    }

    print("\nEnvironment:")
    print(
        json.dumps(
            environment,
            indent=2,
        )
    )
    df = (
        load_and_validate_dataset()
    )

    dataset_sha256 = (
        sha256_file(
            DATA_PATH
        )
    )

    print(
        "\nFrozen dataset SHA-256:"
    )

    print(
        dataset_sha256
    )
    evaluation_df = df[
        df["split"].isin(
            ["dev", "heldout"]
        )
    ].copy()

    dev_df = df[
        df["split"] == "dev"
    ].copy()

    heldout_df = df[
        df["split"] == "heldout"
    ].copy()

    if dev_df.empty:
        raise RuntimeError(
            "DEV split is empty."
        )

    if heldout_df.empty:
        raise RuntimeError(
            "HELD-OUT split is empty."
        )

    print(
        f"\nDEV rows: "
        f"{len(dev_df):,}"
    )

    print(
        f"HELD-OUT rows: "
        f"{len(heldout_df):,}"
    )

    print(
        "\nTRAIN rows deliberately excluded "
        "from baseline:"
    )

    print(
        f"{int((df['split'] == 'train').sum()):,}"
    )
    model = load_qwen()
    embedding_map = (
        encode_unique_descriptions(
            model,
            evaluation_df,
        )
    )
    print(
        "\nScoring DEV pairs..."
    )

    dev_scores = score_pairs(
        dev_df,
        embedding_map,
    )

    dev_labels = (
        dev_df["label"]
        .to_numpy(
            dtype=np.int64
        )
    )

    dev_result = (
        select_dev_threshold(
            dev_scores,
            dev_labels,
        )
    )

    selected_threshold = (
        dev_result.threshold
    )

    print(
        "\nDEV-selected threshold:"
    )

    print(
        f"{selected_threshold:.3f}"
    )

    print(
        f"DEV F1: "
        f"{dev_result.f1:.4f}"
    )
    print(
        "\n[6/8] Evaluating BLIND HELD-OUT..."
    )

    heldout_scores = score_pairs(
        heldout_df,
        embedding_map,
    )

    heldout_labels = (
        heldout_df["label"]
        .to_numpy(
            dtype=np.int64
        )
    )

    heldout_result = (
        calculate_metrics(
            heldout_scores,
            heldout_labels,
            selected_threshold,
        )
    )

    print(
        "\nHELD-OUT BASELINE:"
    )

    print(
        json.dumps(
            sanitize_for_json(
                asdict(
                    heldout_result
                )
            ),
            indent=2,
        )
    )
    print(
        "\n[7/8] Analyzing hard negatives..."
    )

    hard_negative_result = (
        analyze_hard_negatives(
            heldout_df,
            heldout_scores,
            selected_threshold,
        )
    )

    print(
        json.dumps(
            sanitize_for_json(
                hard_negative_result
            ),
            indent=2,
        )
    )
    print(
        "\nCalculating per-category metrics..."
    )

    category_results = (
        subgroup_metrics(
            heldout_df,
            heldout_scores,
            selected_threshold,
            "category",
        )
    )
    heldout_with_cpse_pair = (
        create_cpse_pair_column(
            heldout_df
        )
    )

    print(
        "Calculating per-CPSE-pair metrics..."
    )

    cpse_pair_results = (
        subgroup_metrics(
            heldout_with_cpse_pair,
            heldout_scores,
            selected_threshold,
            "_cpse_pair",
        )
    )

    save_pair_scores(
        heldout_df,
        heldout_scores,
        selected_threshold,
    )

    total_seconds = (
        time.perf_counter()
        - overall_start
    )

    results = {

        "experiment": {
            "name": (
                "MIRA Qwen3-Embedding-0.6B "
                "untrained baseline"
            ),

            "status": "untrained",

            "semantic_only": True,

            "fine_tuning_applied": False,

            "training_data_used": False,

            "hybrid_matcher_used": False,

            "critical_gates_used": False,
        },

        "model": {
            "name": MODEL_NAME,

            "embedding_dimension":
                EXPECTED_EMBEDDING_DIM,

            "normalized_embeddings":
                NORMALIZE_EMBEDDINGS,

            "batch_size":
                BATCH_SIZE,

            "device": "cuda",

            "gpu":
                environment["gpu"],
        },

        "dataset": {
            "path": str(
                DATA_PATH
            ),

            "sha256":
                dataset_sha256,

            "total_rows":
                int(len(df)),

            "train_rows":
                int(
                    (
                        df["split"]
                        == "train"
                    ).sum()
                ),

            "dev_rows":
                int(
                    len(dev_df)
                ),

            "heldout_rows":
                int(
                    len(heldout_df)
                ),
        },

        "threshold_selection": {

            "selected_on":
                "dev",

            "objective":
                THRESHOLD_OBJECTIVE,

            "minimum":
                THRESHOLD_MIN,

            "maximum":
                THRESHOLD_MAX,

            "step":
                THRESHOLD_STEP,

            "selected_threshold":
                float(
                    selected_threshold
                ),
        },

        "dev_metrics":
            asdict(
                dev_result
            ),

        "heldout_metrics":
            asdict(
                heldout_result
            ),

        "hard_negative_metrics":
            hard_negative_result,

        "heldout_category_metrics":
            category_results,

        "heldout_cpse_pair_metrics":
            cpse_pair_results,

        "reproducibility": {

            "dataset_sha256":
                dataset_sha256,

            "model_name":
                MODEL_NAME,

            "pytorch":
                torch.__version__,

            "cuda_runtime":
                torch.version.cuda,

            "gpu":
                environment["gpu"],

            "python":
                sys.version,
        },

        "runtime": {
            "total_seconds":
                total_seconds,
        },

        "methodology_note": (
            "This result represents the "
            "UNTRAINED Qwen3-Embedding-0.6B "
            "semantic baseline. TRAIN data was "
            "excluded. DEV was used only for "
            "threshold selection. HELD-OUT was "
            "used only for baseline measurement. "
            "No MIRA hybrid matching algorithms "
            "or deterministic gates were applied."
        ),
    }

    RESULTS_JSON.write_text(
        json.dumps(
            sanitize_for_json(results),
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )

    RUNTIME_JSON.write_text(
        json.dumps(
            {
                "completed": True,
                "total_seconds":
                    total_seconds,
                "gpu":
                    environment["gpu"],
                "cuda_available":
                    environment[
                        "cuda_available"
                    ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n")
    print("=" * 78)
    print(
        "MIRA BASELINE EXPERIMENT COMPLETE"
    )
    print("=" * 78)

    print(
        f"Model:              {MODEL_NAME}"
    )

    print(
        f"GPU:                "
        f"{environment['gpu']}"
    )

    print(
        f"DEV threshold:      "
        f"{selected_threshold:.3f}"
    )

    print(
        f"HELD-OUT rows:      "
        f"{heldout_result.rows:,}"
    )

    print(
        f"Accuracy:           "
        f"{heldout_result.accuracy:.4f}"
    )

    print(
        f"Precision:          "
        f"{heldout_result.precision:.4f}"
    )

    print(
        f"Recall:             "
        f"{heldout_result.recall:.4f}"
    )

    print(
        f"F1:                 "
        f"{heldout_result.f1:.4f}"
    )

    print(
        f"False-positive rate:"
        f" {heldout_result.false_positive_rate:.4f}"
    )

    if (
        hard_negative_result.get(
            "rows",
            0,
        )
        > 0
    ):

        print(
            "Hard-negative "
            "false-HIGH_CONFIDENCE:"
            f" {hard_negative_result['false_high_confidence_rate']:.4f}"
        )

    print(
        "\nSaved:"
    )

    print(
        f"  {RESULTS_JSON}"
    )

    print(
        f"  {PAIR_SCORES_CSV}"
    )

    print(
        f"  {RUNTIME_JSON}"
    )

    print("=" * 78)

if __name__ == "__main__":
    main()
