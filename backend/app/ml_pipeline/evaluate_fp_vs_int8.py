from __future__ import annotations

import gc
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from sentence_transformers import SentenceTransformer
from transformers import BitsAndBytesConfig

from backend.app.ml_pipeline.training_utils.dataset import (
    ALLOWED_HN_TYPES,
    load_pairs_dataframe,
    normalize_pair_type,
)
from backend.app.ml_pipeline.training_utils.metrics import (
    BinaryMetrics,
    calculate_binary_metrics,
    find_best_threshold,
    hard_negative_metrics,
)

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parents[2]

DATA_PATH = (
    BASE_DIR
    / "train_data"
    / "training"
    / "Training_Pairs_MIRA_FINAL.csv"
)

FP_MODEL = (
    BASE_DIR
    / "qwen_models"
    / "epoch2_finetuned"
    / "best"
)

INT8_MODEL = (
    BASE_DIR
    / "qwen_models"
    / "qwen_quantized"
)

RESULT_PATH = (
    BASE_DIR
    / "results"
    / "epoch2_training"
    / "epoch2_fp_vs_int8_evaluation.json"
)

MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"
SOURCE_STEP = 13678

EXPECTED_EMBEDDING_DIM = 1024

DEV_EXPECTED_ROWS = 5_228
HELDOUT_EXPECTED_ROWS = 5_284

EVAL_BATCH_SIZE = 8

HN_THRESHOLD = 0.85

INT8_THRESHOLD = 6.0

F1_RETENTION_TARGET = 0.95

EXPECTED_DATASET_SHA256 = (
    "fb01ca6f3aa349c2168251d6a38537d3043b57a0655f2127f1cc6b2c15584126"
)

def print_header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def directory_size_bytes(path: Path) -> int:
    if not path.exists():
        raise FileNotFoundError(f"Directory does not exist: {path}")

    return sum(
        file.stat().st_size
        for file in path.rglob("*")
        if file.is_file()
    )


def human_size(num_bytes: int) -> str:
    return f"{num_bytes / (1024 ** 3):.2f} GiB"


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def validate_environment() -> None:
    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA is unavailable. "
            "This evaluation requires the NVIDIA GPU."
        )

    gpu_name = torch.cuda.get_device_name(0)
    gpu_memory = (
        torch.cuda.get_device_properties(0).total_memory
        / (1024 ** 3)
    )

    print(f"GPU:                {gpu_name}")
    print(f"VRAM:               {gpu_memory:.2f} GB")
    print(f"PyTorch:            {torch.__version__}")
    print(f"CUDA runtime:       {torch.version.cuda}")

    print(f"Project root:       {PROJECT_ROOT}")
    print(f"Dataset:            {DATA_PATH}")
    print(f"Full precision:     {FP_MODEL}")
    print(f"INT8:               {INT8_MODEL}")


def validate_paths() -> None:
    if not DATA_PATH.is_file():
        raise FileNotFoundError(
            f"Frozen evaluation dataset not found:\n{DATA_PATH}"
        )

    if not FP_MODEL.is_dir():
        raise FileNotFoundError(
            f"Full-precision model not found:\n{FP_MODEL}"
        )

    if not INT8_MODEL.is_dir():
        raise FileNotFoundError(
            f"INT8 model not found:\n{INT8_MODEL}"
        )

    if not any(FP_MODEL.iterdir()):
        raise RuntimeError(
            f"Full-precision model directory is empty:\n{FP_MODEL}"
        )

    if not any(INT8_MODEL.iterdir()):
        raise RuntimeError(
            f"INT8 model directory is empty:\n{INT8_MODEL}"
        )


def load_dataset() -> pd.DataFrame:
    print_header("LOADING FROZEN EVALUATION DATASET")

    dataset_hash = sha256_file(DATA_PATH)

    print(f"Dataset SHA-256:    {dataset_hash}")

    if dataset_hash != EXPECTED_DATASET_SHA256:
        raise RuntimeError(
            "Dataset SHA-256 mismatch.\n"
            f"Expected: {EXPECTED_DATASET_SHA256}\n"
            f"Actual:   {dataset_hash}\n"
            "Refusing to evaluate against a different dataset snapshot."
        )

    dataframe = load_pairs_dataframe(
        DATA_PATH,
        require_unique_pair_ids=True,
    )

    required_columns = {
        "desc_a",
        "desc_b",
        "label",
        "split",
        "pair_type",
    }

    missing = required_columns.difference(dataframe.columns)

    if missing:
        raise RuntimeError(
            f"Dataset is missing required columns: {sorted(missing)}"
        )

    dev = dataframe[dataframe["split"] == "dev"]

    heldout = dataframe[dataframe["split"] == "heldout"]

    if len(dev) != DEV_EXPECTED_ROWS:
        raise RuntimeError(
            f"Unexpected DEV row count: {len(dev)} "
            f"(expected {DEV_EXPECTED_ROWS})"
        )

    if len(heldout) != HELDOUT_EXPECTED_ROWS:
        raise RuntimeError(
            f"Unexpected HELD-OUT row count: {len(heldout)} "
            f"(expected {HELDOUT_EXPECTED_ROWS})"
        )

    print(f"Total rows:         {len(dataframe):,}")
    print(f"DEV rows:           {len(dev):,}")
    print(f"HELD-OUT rows:      {len(heldout):,}")

    return dataframe

def load_model(
    model_path: Path,
    *,
    quantized: bool,
) -> SentenceTransformer:

    print_header(
        "LOADING INT8 MODEL"
        if quantized
        else "LOADING FULL-PRECISION MODEL"
    )

    if quantized:
        quantization_config = BitsAndBytesConfig(
            load_in_8bit=True,
            llm_int8_threshold=INT8_THRESHOLD,
        )

        model = SentenceTransformer(
            str(model_path),
            model_kwargs={
                "quantization_config": quantization_config,
                "device_map": {"": 0},
            },
        )

    else:
        model = SentenceTransformer(
            str(model_path),
            device="cuda",
        )

    model.eval()

    return model


def count_int8_layers(model: SentenceTransformer) -> int:
    import bitsandbytes as bnb

    return sum(
        isinstance(module, bnb.nn.Linear8bitLt)
        for module in model.modules()
    )


def validate_model_runtime(
    model: SentenceTransformer,
    *,
    quantized: bool,
) -> None:

    # Confirm encoder dimensionality.
    probe = model.encode(
        ["MIRA model validation"],
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )

    probe = np.asarray(
        probe,
        dtype=np.float32,
    )

    if probe.shape != (1, EXPECTED_EMBEDDING_DIM):
        raise RuntimeError(
            "Unexpected embedding shape: "
            f"{probe.shape}; expected "
            f"(1, {EXPECTED_EMBEDDING_DIM})"
        )

    if not np.isfinite(probe).all():
        raise RuntimeError(
            "Model produced non-finite validation embeddings."
        )

    print(
        f"Embedding dimension: {probe.shape[1]}"
    )

    if quantized:
        int8_layers = count_int8_layers(model)

        print(
            f"INT8 Linear8bitLt layers: {int8_layers}"
        )

        if int8_layers <= 0:
            raise RuntimeError(
                "INT8 model loaded but zero "
                "Linear8bitLt layers were detected."
            )

def encode_split(
    model: SentenceTransformer,
    frame: pd.DataFrame,
    split_name: str,
) -> tuple[np.ndarray, np.ndarray, float]:

    print()
    print(
        f"Encoding {split_name.upper()}..."
    )

    unique_texts = list(
        pd.unique(
            pd.concat(
                [
                    frame["desc_a"],
                    frame["desc_b"],
                ],
                ignore_index=True,
            )
        )
    )

    print(
        f"Unique texts:       {len(unique_texts):,}"
    )

    started = time.perf_counter()

    with torch.inference_mode():
        embeddings = model.encode(
            unique_texts,
            batch_size=EVAL_BATCH_SIZE,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

    if torch.cuda.is_available():
        torch.cuda.synchronize()

    elapsed = time.perf_counter() - started

    embeddings = np.asarray(
        embeddings,
        dtype=np.float32,
    )

    expected_shape = (
        len(unique_texts),
        EXPECTED_EMBEDDING_DIM,
    )

    if embeddings.shape != expected_shape:
        raise RuntimeError(
            f"{split_name.upper()} embedding shape mismatch: "
            f"{embeddings.shape} != {expected_shape}"
        )

    if not np.isfinite(embeddings).all():
        raise RuntimeError(
            f"{split_name.upper()} embeddings contain "
            "NaN or infinite values."
        )

    embedding_map = dict(
        zip(unique_texts, embeddings)
    )

    scores = np.fromiter(
        (
            float(
                np.dot(
                    embedding_map[row.desc_a],
                    embedding_map[row.desc_b],
                )
            )
            for row in frame.itertuples(index=False)
        ),
        dtype=np.float32,
        count=len(frame),
    )

    labels = frame["label"].to_numpy(
        dtype=np.int64
    )

    if not np.isfinite(scores).all():
        raise RuntimeError(
            f"{split_name.upper()} scores contain "
            "NaN or infinite values."
        )

    print(
        f"Encoding time:      {elapsed:.2f}s"
    )

    return scores, labels, elapsed

def hard_negative_metrics_at_085(
    frame: pd.DataFrame,
    scores: np.ndarray,
    labels: np.ndarray,
) -> dict[str, Any]:

    hard_mask = (
        frame["pair_type"]
        .map(normalize_pair_type)
        .isin(ALLOWED_HN_TYPES)
        .to_numpy()
    )

    if not hard_mask.any():
        return {
            "rows": 0,
            "negative_rows": 0,
            "false_high_confidence_count": 0,
            "false_high_confidence_rate": None,
            "threshold": HN_THRESHOLD,
            "status": "NO_HARD_NEGATIVES",
        }

    return hard_negative_metrics(
        scores[hard_mask],
        labels[hard_mask],
        HN_THRESHOLD,
    )


def metrics_to_dict(metrics: BinaryMetrics) -> dict[str, Any]:
    return {
        "threshold": float(metrics.threshold),
        "rows": int(metrics.rows),
        "positive_rows": int(metrics.positive_rows),
        "negative_rows": int(metrics.negative_rows),
        "accuracy": float(metrics.accuracy),
        "precision": float(metrics.precision),
        "recall": float(metrics.recall),
        "f1": float(metrics.f1),
        "roc_auc": (
            None
            if metrics.roc_auc is None
            else float(metrics.roc_auc)
        ),
        "false_positive_rate": (
            None
            if metrics.false_positive_rate is None
            else float(metrics.false_positive_rate)
        ),
        "false_negative_rate": (
            None
            if metrics.false_negative_rate is None
            else float(metrics.false_negative_rate)
        ),
        "true_positive": int(metrics.true_positive),
        "true_negative": int(metrics.true_negative),
        "false_positive": int(metrics.false_positive),
        "false_negative": int(metrics.false_negative),
        "mean_positive_similarity": (
            None
            if metrics.mean_positive_similarity is None
            else float(metrics.mean_positive_similarity)
        ),
        "mean_negative_similarity": (
            None
            if metrics.mean_negative_similarity is None
            else float(metrics.mean_negative_similarity)
        ),
    }


def evaluate_at_threshold(
    frame: pd.DataFrame,
    scores: np.ndarray,
    labels: np.ndarray,
    threshold: float,
) -> dict[str, Any]:

    binary = calculate_binary_metrics(
        scores,
        labels,
        threshold,
    )

    return {
        "metrics": metrics_to_dict(binary),
        "hard_negative_at_085": (
            hard_negative_metrics_at_085(
                frame,
                scores,
                labels,
            )
        ),
    }
def release_model(
    model: SentenceTransformer | None,
) -> None:

    if model is not None:
        del model

    gc.collect()

    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()

def main() -> int:

    experiment_started = time.perf_counter()

    print_header(
        "MIRA EPOCH-2 FULL PRECISION vs INT8 EVALUATION"
    )

    validate_environment()
    validate_paths()

    dataframe = load_dataset()

    dev = dataframe[
        dataframe["split"] == "dev"
    ].copy()

    heldout = dataframe[
        dataframe["split"] == "heldout"
    ].copy()

    fp_model = None

    try:
        fp_model = load_model(
            FP_MODEL,
            quantized=False,
        )

        validate_model_runtime(
            fp_model,
            quantized=False,
        )

        fp_dev_scores, dev_labels, fp_dev_time = encode_split(
            fp_model,
            dev,
            "dev",
        )

        fp_heldout_scores, heldout_labels, fp_heldout_time = encode_split(
            fp_model,
            heldout,
            "heldout",
        )

        fp_threshold_result = find_best_threshold(
            fp_dev_scores,
            dev_labels,
            objective="f1",
        )

        frozen_threshold = float(
            fp_threshold_result.threshold
        )

        print()
        print(
            f"Frozen threshold from FP DEV: "
            f"{frozen_threshold:.3f}"
        )

        fp_dev = evaluate_at_threshold(
            dev,
            fp_dev_scores,
            dev_labels,
            frozen_threshold,
        )

        fp_heldout = evaluate_at_threshold(
            heldout,
            fp_heldout_scores,
            heldout_labels,
            frozen_threshold,
        )

    finally:
        release_model(fp_model)

    int8_model = None

    try:
        int8_model = load_model(
            INT8_MODEL,
            quantized=True,
        )

        validate_model_runtime(
            int8_model,
            quantized=True,
        )

        int8_dev_scores, int8_dev_labels, int8_dev_time = encode_split(
            int8_model,
            dev,
            "dev",
        )

        int8_heldout_scores, int8_heldout_labels, int8_heldout_time = encode_split(
            int8_model,
            heldout,
            "heldout",
        )

        # IMPORTANT:
        # SAME frozen FP-derived threshold.
        int8_dev = evaluate_at_threshold(
            dev,
            int8_dev_scores,
            int8_dev_labels,
            frozen_threshold,
        )

        int8_heldout = evaluate_at_threshold(
            heldout,
            int8_heldout_scores,
            heldout_labels,
            frozen_threshold,
        )

    finally:
        release_model(int8_model)

    fp_heldout_metrics = fp_heldout["metrics"]
    int8_heldout_metrics = int8_heldout["metrics"]

    fp_f1 = float(
        fp_heldout_metrics["f1"]
    )

    int8_f1 = float(
        int8_heldout_metrics["f1"]
    )

    f1_retention = (
        int8_f1 / fp_f1
        if fp_f1 > 0.0
        else None
    )

    f1_drop = (
        fp_f1 - int8_f1
    )

    fp_hn = fp_heldout[
        "hard_negative_at_085"
    ].get(
        "false_high_confidence_rate"
    )

    int8_hn = int8_heldout[
        "hard_negative_at_085"
    ].get(
        "false_high_confidence_rate"
    )

    hn_change = (
        int8_hn - fp_hn
        if fp_hn is not None
        and int8_hn is not None
        else None
    )

    result = {
        "experiment": {
            "name": "MIRA Epoch-2 Full Precision vs INT8",
            "model": MODEL_NAME,
            "source_training_step": SOURCE_STEP,
            "embedding_dimension": EXPECTED_EMBEDDING_DIM,
            "threshold_source": "full_precision_dev_f1",
            "frozen_threshold": frozen_threshold,
            "hard_negative_threshold": HN_THRESHOLD,
            "int8_threshold": INT8_THRESHOLD,
            "f1_retention_target": F1_RETENTION_TARGET,
        },
        "dataset": {
            "path": str(DATA_PATH),
            "sha256": sha256_file(DATA_PATH),
            "total_rows": int(len(dataframe)),
            "dev_rows": int(len(dev)),
            "heldout_rows": int(len(heldout)),
        },
        "artifacts": {
            "full_precision_model": str(FP_MODEL),
            "int8_model": str(INT8_MODEL),
            "full_precision_size_bytes": directory_size_bytes(
                FP_MODEL
            ),
            "int8_size_bytes": directory_size_bytes(
                INT8_MODEL
            ),
            "full_precision_size": human_size(
                directory_size_bytes(FP_MODEL)
            ),
            "int8_size": human_size(
                directory_size_bytes(INT8_MODEL)
            ),
        },
        "full_precision": {
            "dev": fp_dev,
            "heldout": fp_heldout,
            "dev_encoding_seconds": fp_dev_time,
            "heldout_encoding_seconds": fp_heldout_time,
        },
        "int8": {
            "dev": int8_dev,
            "heldout": int8_heldout,
            "dev_encoding_seconds": int8_dev_time,
            "heldout_encoding_seconds": int8_heldout_time,
        },
        "retention": {
            "heldout_f1_full_precision": fp_f1,
            "heldout_f1_int8": int8_f1,
            "heldout_f1_retention": f1_retention,
            "heldout_f1_drop": f1_drop,
            "heldout_f1_retention_target": F1_RETENTION_TARGET,
            "passes_95_percent_f1_retention": (
                f1_retention is not None
                and f1_retention >= F1_RETENTION_TARGET
            ),
            "heldout_hn_fhc_full_precision": fp_hn,
            "heldout_hn_fhc_int8": int8_hn,
            "heldout_hn_fhc_change": hn_change,
            "size_reduction_pct": (
                100.0
                * (
                    1.0
                    - (
                        directory_size_bytes(INT8_MODEL)
                        / directory_size_bytes(FP_MODEL)
                    )
                )
            ),
        },
        "runtime": {
            "total_seconds": (
                time.perf_counter()
                - experiment_started
            ),
        },
    }

    RESULT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    RESULT_PATH.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        ),
        encoding="utf-8",
    )

    print_header("EVALUATION COMPLETE")

    print()
    print("FROZEN THRESHOLD")
    print(
        f"Threshold:                 "
        f"{frozen_threshold:.3f}"
    )

    print()
    print("DEV")
    print(
        f"Full precision F1:         "
        f"{fp_dev['metrics']['f1']:.6f}"
    )
    print(
        f"INT8 F1:                   "
        f"{int8_dev['metrics']['f1']:.6f}"
    )
    print(
        f"Full precision HN-FHC:     "
        f"{fp_dev['hard_negative_at_085']['false_high_confidence_rate']:.6f}"
    )
    print(
        f"INT8 HN-FHC:               "
        f"{int8_dev['hard_negative_at_085']['false_high_confidence_rate']:.6f}"
    )

    print()
    print("HELD-OUT")
    print(
        f"Full precision F1:         "
        f"{fp_heldout_metrics['f1']:.6f}"
    )
    print(
        f"INT8 F1:                   "
        f"{int8_heldout_metrics['f1']:.6f}"
    )
    print(
        f"Full precision Precision:  "
        f"{fp_heldout_metrics['precision']:.6f}"
    )
    print(
        f"INT8 Precision:            "
        f"{int8_heldout_metrics['precision']:.6f}"
    )
    print(
        f"Full precision Recall:     "
        f"{fp_heldout_metrics['recall']:.6f}"
    )
    print(
        f"INT8 Recall:               "
        f"{int8_heldout_metrics['recall']:.6f}"
    )
    print(
        f"Full precision ROC-AUC:    "
        f"{fp_heldout_metrics['roc_auc']:.6f}"
    )
    print(
        f"INT8 ROC-AUC:              "
        f"{int8_heldout_metrics['roc_auc']:.6f}"
    )
    print(
        f"Full precision HN-FHC:     "
        f"{fp_hn:.6f}"
    )
    print(
        f"INT8 HN-FHC:               "
        f"{int8_hn:.6f}"
    )

    print()
    print("QUANTIZATION RETENTION")
    print(
        f"F1 retention:              "
        f"{f1_retention:.2%}"
    )
    print(
        f"F1 drop:                   "
        f"{f1_drop:.6f}"
    )
    print(
        f"HN-FHC change:             "
        f"{hn_change:+.6f}"
    )

    print()
    print("MODEL SIZE")
    print(
        f"Full precision:            "
        f"{result['artifacts']['full_precision_size']}"
    )
    print(
        f"INT8:                      "
        f"{result['artifacts']['int8_size']}"
    )
    print(
        f"Reduction:                 "
        f"{result['retention']['size_reduction_pct']:.2f}%"
    )

    print()
    print(
        "95% F1 retention gate:     "
        + (
            "PASS"
            if result["retention"][
                "passes_95_percent_f1_retention"
            ]
            else "FAIL"
        )
    )

    print()
    print("Results saved to:")
    print(RESULT_PATH)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
