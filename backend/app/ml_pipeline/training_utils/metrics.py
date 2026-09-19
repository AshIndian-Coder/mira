from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, roc_auc_score


@dataclass(frozen=True)
class BinaryMetrics:
    threshold: float
    rows: int
    positive_rows: int
    negative_rows: int
    accuracy: float
    precision: float
    recall: float
    f1: float
    roc_auc: float | None
    false_positive_rate: float | None
    false_negative_rate: float | None
    true_positive: int
    true_negative: int
    false_positive: int
    false_negative: int
    mean_positive_similarity: float | None
    mean_negative_similarity: float | None


def _validate_inputs(scores: np.ndarray, labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    scores = np.asarray(scores, dtype=np.float64).reshape(-1)
    labels = np.asarray(labels, dtype=np.int64).reshape(-1)
    if scores.size == 0:
        raise ValueError("scores and labels cannot be empty")
    if scores.size != labels.size:
        raise ValueError(f"scores and labels length mismatch: {scores.size} != {labels.size}")
    if not np.isfinite(scores).all():
        raise ValueError("scores contain NaN or infinite values")
    if not np.isin(labels, [0, 1]).all():
        raise ValueError("labels must contain only 0 and 1")
    return scores, labels


def _validate_threshold(threshold: float) -> float:
    threshold = float(threshold)
    if not np.isfinite(threshold) or not -1.0 <= threshold <= 1.0:
        raise ValueError("threshold must be finite and in [-1, 1]")
    return threshold


def calculate_binary_metrics(scores: np.ndarray, labels: np.ndarray, threshold: float) -> BinaryMetrics:
    threshold = _validate_threshold(threshold)
    scores, labels = _validate_inputs(scores, labels)
    predictions = (scores >= threshold).astype(np.int64)
    tn, fp, fn, tp = confusion_matrix(labels, predictions, labels=[0, 1]).ravel().tolist()
    positive_rows = int((labels == 1).sum())
    negative_rows = int((labels == 0).sum())
    accuracy = float((tp + tn) / labels.size)
    precision = float(tp / (tp + fp)) if tp + fp else 0.0
    recall = float(tp / (tp + fn)) if tp + fn else 0.0
    f1 = float((2.0 * precision * recall) / (precision + recall)) if precision + recall else 0.0
    roc_auc = float(roc_auc_score(labels, scores)) if np.unique(labels).size == 2 else None
    fpr = float(fp / (fp + tn)) if fp + tn else None
    fnr = float(fn / (fn + tp)) if fn + tp else None
    positive_scores = scores[labels == 1]
    negative_scores = scores[labels == 0]
    return BinaryMetrics(
        threshold=threshold,
        rows=int(labels.size),
        positive_rows=positive_rows,
        negative_rows=negative_rows,
        accuracy=accuracy,
        precision=precision,
        recall=recall,
        f1=f1,
        roc_auc=roc_auc,
        false_positive_rate=fpr,
        false_negative_rate=fnr,
        true_positive=int(tp),
        true_negative=int(tn),
        false_positive=int(fp),
        false_negative=int(fn),
        mean_positive_similarity=float(positive_scores.mean()) if positive_scores.size else None,
        mean_negative_similarity=float(negative_scores.mean()) if negative_scores.size else None,
    )


def find_best_threshold(
    scores: np.ndarray,
    labels: np.ndarray,
    *,
    objective: str = "f1",
    min_threshold: float = 0.0,
    max_threshold: float = 1.0,
    step: float = 0.001,
) -> BinaryMetrics:
    objective = objective.strip().lower()
    if objective not in {"f1", "precision", "recall", "accuracy"}:
        raise ValueError("objective must be one of f1, precision, recall, accuracy")
    if not np.isfinite(step) or step <= 0.0:
        raise ValueError("step must be finite and > 0")
    if not -1.0 <= float(min_threshold) < float(max_threshold) <= 1.0:
        raise ValueError("threshold bounds must satisfy -1 <= min < max <= 1")
    scores, labels = _validate_inputs(scores, labels)

    grid = np.arange(float(min_threshold), float(max_threshold) + float(step) * 0.5, float(step), dtype=np.float64)
    grid = np.unique(np.clip(grid, -1.0, 1.0))
    if grid.size == 0 or grid[-1] < float(max_threshold) - 1e-12:
        grid = np.append(grid, float(max_threshold))

    best: BinaryMetrics | None = None
    best_key: tuple[float, float, float, float, float] | None = None
    for threshold in grid:
        candidate = calculate_binary_metrics(scores, labels, float(threshold))
        objective_value = float(getattr(candidate, objective))
        candidate_key = (
            objective_value,
            float(candidate.precision),
            float(candidate.recall),
            -float(candidate.false_positive_rate if candidate.false_positive_rate is not None else 1.0),
            -float(candidate.threshold),
        )
        if best is None or candidate_key > best_key:
            best = candidate
            best_key = candidate_key
    if best is None:
        raise RuntimeError("Threshold search produced no candidate")
    return best


def hard_negative_metrics(scores: np.ndarray, labels: np.ndarray, threshold: float) -> dict[str, Any]:
    threshold = _validate_threshold(threshold)
    scores, labels = _validate_inputs(scores, labels)
    negative_scores = scores[labels == 0]
    if negative_scores.size == 0:
        return {
            "rows": int(scores.size),
            "negative_rows": 0,
            "false_high_confidence_count": 0,
            "false_high_confidence_rate": None,
            "status": "NO_NEGATIVE_EXAMPLES",
        }
    count = int((negative_scores >= threshold).sum())
    return {
        "rows": int(scores.size),
        "negative_rows": int(negative_scores.size),
        "false_high_confidence_count": count,
        "false_high_confidence_rate": float(count / negative_scores.size),
        "mean_similarity": float(negative_scores.mean()),
        "median_similarity": float(np.median(negative_scores)),
        "p90_similarity": float(np.percentile(negative_scores, 90)),
        "max_similarity": float(negative_scores.max()),
        "status": "OK",
    }


def evaluate_subgroup(scores: np.ndarray, labels: np.ndarray, threshold: float, *, min_rows: int = 20) -> dict[str, Any]:
    scores, labels = _validate_inputs(scores, labels)
    if min_rows < 1:
        raise ValueError("min_rows must be >= 1")
    if len(labels) < min_rows:
        return {"rows": int(len(labels)), "status": "INSUFFICIENT_SAMPLE"}
    return {"status": "OK", **asdict(calculate_binary_metrics(scores, labels, threshold))}


def evaluate_grouped(
    dataframe: pd.DataFrame,
    scores: np.ndarray,
    threshold: float,
    group_column: str,
    *,
    min_rows: int = 20,
) -> dict[str, Any]:
    if group_column not in dataframe.columns:
        return {}
    if "label" not in dataframe.columns:
        raise ValueError("dataframe must contain label")
    scores = np.asarray(scores).reshape(-1)
    if len(dataframe) != len(scores):
        raise ValueError("dataframe and scores length mismatch")
    groups = dataframe[group_column].fillna("UNKNOWN").astype(str).str.strip()
    groups = groups.mask(groups.eq(""), "UNKNOWN")
    return {
        group: evaluate_subgroup(
            scores[groups.to_numpy() == group],
            dataframe.loc[groups.to_numpy() == group, "label"].to_numpy(dtype=np.int64),
            threshold,
            min_rows=min_rows,
        )
        for group in sorted(groups.unique())
    }


def to_serializable(value: BinaryMetrics | dict[str, Any]) -> dict[str, Any]:
    payload = asdict(value) if isinstance(value, BinaryMetrics) else value
    return _sanitize(payload)


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        number = float(value)
        return number if np.isfinite(number) else None
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    return value


__all__ = [
    "BinaryMetrics",
    "calculate_binary_metrics",
    "evaluate_grouped",
    "evaluate_subgroup",
    "find_best_threshold",
    "hard_negative_metrics",
    "to_serializable",
]
