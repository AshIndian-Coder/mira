from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset


REQUIRED_COLUMNS = {
    "pair_id",
    "desc_a",
    "desc_b",
    "label",
    "pair_type",
    "split",
}
ALLOWED_SPLITS = {"train", "dev", "heldout"}
ALLOWED_HN_TYPES = {"HN_CORRUPT", "HN_SIBLING"}


def find_project_root(start: Path) -> Path:
    start = start.resolve()
    candidates = [start, *start.parents]
    for candidate in candidates:
        if (candidate / "backend" / "app" / "ml_pipeline").is_dir():
            return candidate
    for candidate in candidates:
        if (candidate / "backend").is_dir():
            return candidate
    return start


THIS_FILE = Path(__file__).resolve()
BASE_DIR = (
    Path(os.environ["MIRA_PROJECT_ROOT"]).resolve()
    if os.environ.get("MIRA_PROJECT_ROOT")
    else find_project_root(THIS_FILE)
)
ML_PIPELINE_DIR = (
    BASE_DIR / "backend" / "app" / "ml_pipeline"
    if (BASE_DIR / "backend" / "app" / "ml_pipeline").is_dir()
    else THIS_FILE.parent.parent
)
DEFAULT_DATA_PATH = (
    Path(os.environ["MIRA_DATA_PATH"]).resolve()
    if os.environ.get("MIRA_DATA_PATH")
    else ML_PIPELINE_DIR / "train_data" / "training" / "Training_Pairs_MIRA_FINAL.csv"
)


@dataclass(frozen=True)
class PairRecord:
    pair_id: str
    text_a: str
    text_b: str
    label: int
    split: str
    pair_type: str
    difficulty: str | None = None
    category: str | None = None
    cpse_a: str | None = None
    cpse_b: str | None = None
    tmk_a: str | None = None
    tmk_b: str | None = None
    material_code_a: str | None = None
    material_code_b: str | None = None
    hard_negative_reason: str | None = None
    hard_negative_field: str | None = None
    source_a: str | None = None
    source_b: str | None = None
    dataset_version: str | None = None


@dataclass(frozen=True)
class TripletRecord:
    triplet_id: str
    source_pair_id: str
    anchor: str
    positive: str
    hard_negative: str
    tmk: str
    hn_type: str
    hard_negative_field: str
    split: str
    epoch1_similarity: float | None = None
    orientation: str = ""


def normalize_description(value: Any) -> str:
    if pd.isna(value):
        return ""
    return " ".join(str(value).strip().split())


def normalize_optional_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.casefold() in {"", "nan", "none", "null", "n/a", "na"}:
        return ""
    return text


def normalize_split(value: Any) -> str:
    return normalize_optional_text(value).casefold()


def normalize_pair_type(value: Any) -> str:
    return normalize_optional_text(value).upper()


def is_corrupt_tmk(value: Any) -> bool:
    text = normalize_optional_text(value)
    return bool(re.search(r"#CORRUPT", text, flags=re.IGNORECASE))


def normalize_tmk(value: Any) -> str:
    text = normalize_optional_text(value)
    if not text:
        return ""
    text = re.sub(r"#CORRUPT", "", text, flags=re.IGNORECASE)
    return text.strip()


def optional_string(row: pd.Series, column: str) -> str | None:
    if column not in row.index:
        return None
    value = normalize_optional_text(row[column])
    return value or None


def _validate_pair_ids(df: pd.DataFrame, require_unique: bool) -> None:
    values = df["pair_id"].map(normalize_optional_text)
    if values.eq("").any():
        raise ValueError("pair_id contains empty values.")
    if require_unique and values.duplicated().any():
        sample = values[values.duplicated(keep=False)].drop_duplicates().head(10).tolist()
        raise ValueError(f"pair_id must be unique; duplicates include {sample}.")


def validate_dataframe(df: pd.DataFrame, *, require_unique_pair_ids: bool = False) -> None:
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError("Training dataset is missing required columns: " + ", ".join(sorted(missing)))
    if df.empty:
        raise ValueError("Training dataset is empty.")
    _validate_pair_ids(df, require_unique_pair_ids)

    labels = pd.to_numeric(df["label"], errors="coerce")
    if labels.isna().any() or (~np.isfinite(labels.to_numpy(dtype=np.float64))).any():
        raise ValueError("label contains non-finite or non-numeric values.")
    if (~(labels % 1 == 0)).any():
        raise ValueError("label contains non-integer values.")
    labels = labels.astype(int)
    if (~labels.isin([0, 1])).any():
        raise ValueError("label must contain only 0 and 1.")

    splits = df["split"].map(normalize_split)
    if (~splits.isin(ALLOWED_SPLITS)).any():
        bad = sorted(splits[~splits.isin(ALLOWED_SPLITS)].unique().tolist())
        raise ValueError("split contains invalid values: " + ", ".join(bad))

    desc_a = df["desc_a"].map(normalize_description)
    desc_b = df["desc_b"].map(normalize_description)
    if desc_a.eq("").any() or desc_b.eq("").any():
        raise ValueError("desc_a and desc_b must contain non-empty descriptions.")

    pair_types = df["pair_type"].map(normalize_pair_type)
    if pair_types.eq("").any():
        raise ValueError("pair_type contains empty values.")

    if {"tmk_a", "tmk_b"}.issubset(df.columns):
        raw_a = df["tmk_a"].map(normalize_optional_text)
        raw_b = df["tmk_b"].map(normalize_optional_text)
        clean_a = raw_a.map(normalize_tmk)
        clean_b = raw_b.map(normalize_tmk)

        positive_bad = (labels == 1) & clean_a.ne("") & clean_b.ne("") & clean_a.ne(clean_b)
        if positive_bad.any():
            raise ValueError(f"Found {int(positive_bad.sum())} positive rows with conflicting TMKs.")

        corrupt_a = raw_a.map(is_corrupt_tmk)
        corrupt_b = raw_b.map(is_corrupt_tmk)
        corrupt_bad = (pair_types == "HN_CORRUPT") & (corrupt_a == corrupt_b)
        if corrupt_bad.any():
            raise ValueError(f"Found {int(corrupt_bad.sum())} HN_CORRUPT rows without exactly one corrupt TMK marker.")

        sibling_bad = (pair_types == "HN_SIBLING") & (
            clean_a.eq("") | clean_b.eq("") | clean_a.eq(clean_b)
        )
        if sibling_bad.any():
            raise ValueError(f"Found {int(sibling_bad.sum())} invalid HN_SIBLING TMK rows.")


def load_pairs_dataframe(
    path: str | Path = DEFAULT_DATA_PATH,
    *,
    require_unique_pair_ids: bool = False,
) -> pd.DataFrame:
    dataset_path = Path(path).resolve()
    if not dataset_path.is_file():
        raise FileNotFoundError(f"Training dataset not found:\n{dataset_path}")
    df = pd.read_csv(dataset_path, low_memory=False)
    validate_dataframe(df, require_unique_pair_ids=require_unique_pair_ids)
    result = df.copy()
    result["pair_id"] = result["pair_id"].map(normalize_optional_text)
    result["desc_a"] = result["desc_a"].map(normalize_description)
    result["desc_b"] = result["desc_b"].map(normalize_description)
    result["label"] = pd.to_numeric(result["label"], errors="raise").astype(np.int8)
    result["split"] = result["split"].map(normalize_split)
    result["pair_type"] = result["pair_type"].map(normalize_pair_type)
    if "tmk_a" in result.columns:
        result["tmk_a"] = result["tmk_a"].map(normalize_optional_text)
    if "tmk_b" in result.columns:
        result["tmk_b"] = result["tmk_b"].map(normalize_optional_text)
    return result.reset_index(drop=True)


def row_to_record(row: pd.Series) -> PairRecord:
    return PairRecord(
        pair_id=normalize_optional_text(row["pair_id"]),
        text_a=normalize_description(row["desc_a"]),
        text_b=normalize_description(row["desc_b"]),
        label=int(row["label"]),
        split=normalize_split(row["split"]),
        pair_type=normalize_pair_type(row["pair_type"]),
        difficulty=optional_string(row, "difficulty"),
        category=optional_string(row, "category"),
        cpse_a=optional_string(row, "cpse_a"),
        cpse_b=optional_string(row, "cpse_b"),
        tmk_a=optional_string(row, "tmk_a"),
        tmk_b=optional_string(row, "tmk_b"),
        material_code_a=optional_string(row, "material_code_a"),
        material_code_b=optional_string(row, "material_code_b"),
        hard_negative_reason=optional_string(row, "hard_negative_reason"),
        hard_negative_field=optional_string(row, "hard_negative_field"),
        source_a=optional_string(row, "source_a"),
        source_b=optional_string(row, "source_b"),
        dataset_version=optional_string(row, "dataset_version"),
    )


def dataframe_to_records(df: pd.DataFrame) -> list[PairRecord]:
    return [row_to_record(row) for _, row in df.iterrows()]


def collate_pairs(batch: list[dict[str, Any]]) -> dict[str, Any]:
    if not batch:
        raise ValueError("Pair batch cannot be empty.")
    return {
        "text_a": [item["text_a"] for item in batch],
        "text_b": [item["text_b"] for item in batch],
        "label": torch.tensor([int(item["label"]) for item in batch], dtype=torch.float32),
        "pair_type": [item["pair_type"] for item in batch],
    }


class MiraPairDataset(Dataset[dict[str, Any]]):
    def __init__(self, records: list[PairRecord]) -> None:
        if not records:
            raise ValueError("MiraPairDataset cannot be empty.")
        self.records = records

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> dict[str, Any]:
        record = self.records[index]
        return {
            "text_a": record.text_a,
            "text_b": record.text_b,
            "label": record.label,
            "pair_type": record.pair_type,
        }


def create_split_dataset(df: pd.DataFrame, split: str) -> MiraPairDataset:
    normalized = normalize_split(split)
    if normalized not in ALLOWED_SPLITS:
        raise ValueError("split must be one of: " + ", ".join(sorted(ALLOWED_SPLITS)))
    split_df = df[df["split"].map(normalize_split) == normalized].copy()
    if split_df.empty:
        raise ValueError(f"Split '{normalized}' contains no rows.")
    return MiraPairDataset(dataframe_to_records(split_df))


def summarize_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    validate_dataframe(df)
    return {
        "rows": int(len(df)),
        "labels": {str(k): int(v) for k, v in df["label"].value_counts().sort_index().items()},
        "splits": {str(k): int(v) for k, v in df["split"].value_counts().sort_index().items()},
        "pair_types": {str(k): int(v) for k, v in df["pair_type"].value_counts().sort_index().items()},
    }


def check_tmk_leakage(df: pd.DataFrame) -> dict[str, Any]:
    if not {"tmk_a", "tmk_b", "split"}.issubset(df.columns):
        return {"available": False, "status": "SKIPPED_MISSING_COLUMNS"}
    groups: dict[str, set[str]] = {}
    normalized_split = df["split"].map(normalize_split)
    for split in sorted(ALLOWED_SPLITS):
        values: set[str] = set()
        part = df[normalized_split == split]
        for column in ("tmk_a", "tmk_b"):
            for value in part[column].tolist():
                normalized = normalize_tmk(value)
                if normalized:
                    values.add(normalized)
        groups[split] = values
    overlaps: dict[str, Any] = {}
    names = sorted(ALLOWED_SPLITS)
    for i, first in enumerate(names):
        for second in names[i + 1 :]:
            overlap = groups[first] & groups[second]
            overlaps[f"{first}_vs_{second}"] = {
                "count": len(overlap),
                "sample": sorted(overlap)[:10],
            }
    total = sum(item["count"] for item in overlaps.values())
    return {
        "available": True,
        "total_overlap_count": int(total),
        "overlaps": overlaps,
        "status": "PASS" if total == 0 else "FAIL",
    }


def _choose_positives(
    pool: list[str],
    anchor: str,
    negative: str,
    limit: int,
    rng: np.random.RandomState,
) -> list[str]:
    candidates = sorted({text for text in pool if text and text != anchor and text != negative})
    if not candidates:
        return []
    if len(candidates) <= limit:
        return candidates
    chosen = rng.choice(np.asarray(candidates, dtype=object), size=limit, replace=False)
    return sorted(str(value) for value in chosen.tolist())


def _prepare_positive_pools(train_df: pd.DataFrame) -> dict[str, list[str]]:
    positive = train_df[train_df["label"] == 1]
    pools: dict[str, set[str]] = {}
    for _, row in positive.iterrows():
        tmk_a = normalize_tmk(row.get("tmk_a"))
        tmk_b = normalize_tmk(row.get("tmk_b"))
        if tmk_a and tmk_b and tmk_a != tmk_b:
            continue
        tmk = tmk_a or tmk_b
        if not tmk:
            continue
        bucket = pools.setdefault(tmk, set())
        bucket.add(normalize_description(row["desc_a"]))
        bucket.add(normalize_description(row["desc_b"]))
        bucket.discard("")
    return {tmk: sorted(values) for tmk, values in pools.items()}


def _prepare_hn_rows(train_df: pd.DataFrame, hn_df: pd.DataFrame | None) -> pd.DataFrame:
    if hn_df is None:
        result = train_df[
            (train_df["label"] == 0) & train_df["pair_type"].isin(ALLOWED_HN_TYPES)
        ].copy()
    else:
        required = {
            "pair_id",
            "desc_a",
            "desc_b",
            "label",
            "pair_type",
            "split",
            "tmk_a",
            "tmk_b",
            "hard_negative_field",
        }
        missing = required - set(hn_df.columns)
        if missing:
            raise ValueError("HN dataframe is missing required columns: " + ", ".join(sorted(missing)))
        result = hn_df.copy()
        result["pair_id"] = result["pair_id"].map(normalize_optional_text)
        result["desc_a"] = result["desc_a"].map(normalize_description)
        result["desc_b"] = result["desc_b"].map(normalize_description)
        result["label"] = pd.to_numeric(result["label"], errors="raise").astype(int)
        result["split"] = result["split"].map(normalize_split)
        result["pair_type"] = result["pair_type"].map(normalize_pair_type)
        result["tmk_a"] = result["tmk_a"].map(normalize_optional_text)
        result["tmk_b"] = result["tmk_b"].map(normalize_optional_text)
        result["hard_negative_field"] = result["hard_negative_field"].map(normalize_optional_text).str.casefold()
        result = result[(result["split"] == "train") & (result["label"] == 0)].copy()
        result = result[result["pair_type"].isin(ALLOWED_HN_TYPES)].copy()
        if result["pair_id"].eq("").any() or result["pair_id"].duplicated().any():
            raise ValueError("HN dataframe must contain unique non-empty pair_id values.")

    for column in ("tmk_a", "tmk_b"):
        if column not in result.columns:
            raise ValueError(f"HN dataframe is missing {column}.")
        result[column] = result[column].map(normalize_optional_text)
    if "hard_negative_field" not in result.columns:
        raise ValueError("HN dataframe is missing hard_negative_field.")
    result["hard_negative_field"] = result["hard_negative_field"].map(normalize_optional_text).str.casefold()
    result["desc_a"] = result["desc_a"].map(normalize_description)
    result["desc_b"] = result["desc_b"].map(normalize_description)
    if result["hard_negative_field"].eq("").any():
        raise ValueError("HN dataframe contains empty hard_negative_field values.")
    if result["desc_a"].eq("").any() or result["desc_b"].eq("").any():
        raise ValueError("HN dataframe contains empty descriptions.")
    result = result.drop_duplicates(subset=["pair_id"], keep="first").reset_index(drop=True)

    types = result["pair_type"]
    corrupt_a = result["tmk_a"].map(is_corrupt_tmk)
    corrupt_b = result["tmk_b"].map(is_corrupt_tmk)
    corrupt_bad = (types == "HN_CORRUPT") & (corrupt_a == corrupt_b)
    if corrupt_bad.any():
        raise ValueError(f"HN dataframe contains {int(corrupt_bad.sum())} malformed HN_CORRUPT rows.")

    clean_a = result["tmk_a"].map(normalize_tmk)
    clean_b = result["tmk_b"].map(normalize_tmk)
    sibling_bad = (types == "HN_SIBLING") & (
        clean_a.eq("") | clean_b.eq("") | clean_a.eq(clean_b)
    )
    if sibling_bad.any():
        raise ValueError(f"HN dataframe contains {int(sibling_bad.sum())} malformed HN_SIBLING rows.")
    return result.reset_index(drop=True)


def build_triplets_from_pairs_df(
    df: pd.DataFrame,
    *,
    max_positives_per_hn: int = 4,
    seed: int = 42,
    hn_df: pd.DataFrame | None = None,
    return_diagnostics: bool = False,
) -> pd.DataFrame | tuple[pd.DataFrame, dict[str, Any]]:
    if max_positives_per_hn < 1:
        raise ValueError("max_positives_per_hn must be >= 1.")
    if seed < 0:
        raise ValueError("seed must be >= 0.")
    validate_dataframe(df)

    train_df = df[df["split"].map(normalize_split) == "train"].copy()
    positive_pools = _prepare_positive_pools(train_df)
    hn_rows = _prepare_hn_rows(train_df, hn_df)
    rng = np.random.RandomState(seed)

    diagnostics: dict[str, Any] = {
        "source_hn_rows": int(len(hn_rows)),
        "positive_pool_tmk_count": int(len(positive_pools)),
        "positive_pool_description_count": int(sum(len(v) for v in positive_pools.values())),
        "input_hn_by_type": {str(k): int(v) for k, v in hn_rows["pair_type"].value_counts().sort_index().items()},
        "missing_positive_pool_orientations": 0,
        "no_distinct_positive_orientations": 0,
        "generated_by_orientation": {"corrupt": 0, "sibling_a": 0, "sibling_b": 0},
    }

    rows: list[dict[str, Any]] = []
    for index, row in hn_rows.iterrows():
        pair_id = normalize_optional_text(row["pair_id"]) or f"hn_row_{index}"
        hn_type = normalize_pair_type(row["pair_type"])
        desc_a = normalize_description(row["desc_a"])
        desc_b = normalize_description(row["desc_b"])
        field = normalize_optional_text(row["hard_negative_field"]).casefold()
        similarity = None
        if "epoch1_similarity" in row.index and not pd.isna(row["epoch1_similarity"]):
            similarity = float(row["epoch1_similarity"])
            if not np.isfinite(similarity) or not -1.0 <= similarity <= 1.0:
                raise ValueError(f"Invalid epoch1_similarity for {pair_id}: {similarity}")

        if hn_type == "HN_CORRUPT":
            corrupt_a = is_corrupt_tmk(row["tmk_a"])
            corrupt_b = is_corrupt_tmk(row["tmk_b"])
            if corrupt_a == corrupt_b:
                raise RuntimeError(f"Malformed HN_CORRUPT row after validation: {pair_id}")
            anchor = desc_b if corrupt_a else desc_a
            hard_negative = desc_a if corrupt_a else desc_b
            clean_tmk = normalize_tmk(row["tmk_b"] if corrupt_a else row["tmk_a"])
            positives = _choose_positives(
                positive_pools.get(clean_tmk, []), anchor, hard_negative, max_positives_per_hn, rng
            )
            if not positives:
                diagnostics[
                    "missing_positive_pool_orientations"
                    if clean_tmk not in positive_pools
                    else "no_distinct_positive_orientations"
                ] += 1
                continue
            for position, positive in enumerate(positives):
                rows.append(
                    {
                        "triplet_id": f"trip_corrupt_{pair_id}_{position}",
                        "source_pair_id": pair_id,
                        "anchor": anchor,
                        "positive": positive,
                        "hard_negative": hard_negative,
                        "tmk": clean_tmk,
                        "hn_type": hn_type,
                        "hard_negative_field": field,
                        "epoch1_similarity": similarity,
                        "split": "train",
                        "orientation": "corrupt",
                    }
                )
                diagnostics["generated_by_orientation"]["corrupt"] += 1
            continue

        tmk_a = normalize_tmk(row["tmk_a"])
        tmk_b = normalize_tmk(row["tmk_b"])
        for anchor, hard_negative, clean_tmk, orientation in (
            (desc_a, desc_b, tmk_a, "sibling_a"),
            (desc_b, desc_a, tmk_b, "sibling_b"),
        ):
            positives = _choose_positives(
                positive_pools.get(clean_tmk, []), anchor, hard_negative, max_positives_per_hn, rng
            )
            if not positives:
                diagnostics[
                    "missing_positive_pool_orientations"
                    if clean_tmk not in positive_pools
                    else "no_distinct_positive_orientations"
                ] += 1
                continue
            for position, positive in enumerate(positives):
                rows.append(
                    {
                        "triplet_id": f"trip_sibling_{pair_id}_{orientation}_{position}",
                        "source_pair_id": pair_id,
                        "anchor": anchor,
                        "positive": positive,
                        "hard_negative": hard_negative,
                        "tmk": clean_tmk,
                        "hn_type": hn_type,
                        "hard_negative_field": field,
                        "epoch1_similarity": similarity,
                        "split": "train",
                        "orientation": orientation,
                    }
                )
                diagnostics["generated_by_orientation"][orientation] += 1

    columns = [
        "triplet_id",
        "source_pair_id",
        "anchor",
        "positive",
        "hard_negative",
        "tmk",
        "hn_type",
        "hard_negative_field",
        "epoch1_similarity",
        "split",
        "orientation",
    ]
    result = pd.DataFrame(rows, columns=columns)
    diagnostics["pre_dedup_triplets"] = int(len(result))
    diagnostics["pre_dedup_unique_source_hns"] = int(result["source_pair_id"].nunique()) if not result.empty else 0

    if not result.empty:
        result = result[
            result["anchor"].ne(result["positive"])
            & result["anchor"].ne(result["hard_negative"])
            & result["positive"].ne(result["hard_negative"])
        ].copy()
        result = result.drop_duplicates(
            subset=["anchor", "positive", "hard_negative", "tmk", "hn_type"],
            keep="first",
        ).reset_index(drop=True)

    diagnostics["generated_triplets"] = int(len(result))
    diagnostics["unique_source_hns_used"] = int(result["source_pair_id"].nunique()) if not result.empty else 0
    diagnostics["hns_without_any_triplet_candidates"] = int(
        len(hn_rows) - diagnostics["pre_dedup_unique_source_hns"]
    )
    diagnostics["hns_lost_to_semantic_dedup"] = int(
        diagnostics["pre_dedup_unique_source_hns"] - diagnostics["unique_source_hns_used"]
    )
    diagnostics["hn_type_counts"] = (
        {str(k): int(v) for k, v in result["hn_type"].value_counts().sort_index().items()}
        if not result.empty else {}
    )
    diagnostics["post_dedup_orientation_counts"] = (
        {str(k): int(v) for k, v in result["orientation"].value_counts().sort_index().items()}
        if not result.empty else {}
    )
    diagnostics["field_counts"] = (
        {str(k): int(v) for k, v in result["hard_negative_field"].value_counts().sort_index().items()}
        if not result.empty else {}
    )

    if return_diagnostics:
        return result, diagnostics
    return result


class MiraTripletDataset(Dataset[dict[str, Any]]):
    def __init__(self, records: list[TripletRecord]) -> None:
        if not records:
            raise ValueError("MiraTripletDataset cannot be empty.")
        self.records = records

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> dict[str, Any]:
        record = self.records[index]
        return {
            "triplet_id": record.triplet_id,
            "source_pair_id": record.source_pair_id,
            "anchor": record.anchor,
            "positive": record.positive,
            "hard_negative": record.hard_negative,
            "tmk": record.tmk,
            "hn_type": record.hn_type,
            "hard_negative_field": record.hard_negative_field,
            "epoch1_similarity": record.epoch1_similarity,
            "orientation": record.orientation,
        }


def dataframe_to_triplet_records(df: pd.DataFrame) -> list[TripletRecord]:
    required = {
        "triplet_id",
        "source_pair_id",
        "anchor",
        "positive",
        "hard_negative",
        "tmk",
        "hn_type",
        "hard_negative_field",
        "split",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError("Triplet dataframe is missing: " + ", ".join(sorted(missing)))
    records: list[TripletRecord] = []
    for _, row in df.iterrows():
        similarity = None
        if "epoch1_similarity" in row.index and not pd.isna(row["epoch1_similarity"]):
            similarity = float(row["epoch1_similarity"])
            if not np.isfinite(similarity) or not -1.0 <= similarity <= 1.0:
                raise ValueError(f"Invalid epoch1_similarity in triplet {row['triplet_id']}")
        records.append(
            TripletRecord(
                triplet_id=normalize_optional_text(row["triplet_id"]),
                source_pair_id=normalize_optional_text(row["source_pair_id"]),
                anchor=normalize_description(row["anchor"]),
                positive=normalize_description(row["positive"]),
                hard_negative=normalize_description(row["hard_negative"]),
                tmk=normalize_tmk(row["tmk"]),
                hn_type=normalize_pair_type(row["hn_type"]),
                hard_negative_field=normalize_optional_text(row["hard_negative_field"]).casefold(),
                split=normalize_split(row["split"]),
                epoch1_similarity=similarity,
                orientation=normalize_optional_text(row.get("orientation")),
            )
        )
    return records


def collate_triplets(batch: list[dict[str, Any]]) -> dict[str, Any]:
    if not batch:
        raise ValueError("Triplet batch cannot be empty.")
    return {
        "triplet_id": [item["triplet_id"] for item in batch],
        "source_pair_id": [item["source_pair_id"] for item in batch],
        "anchor": [item["anchor"] for item in batch],
        "positive": [item["positive"] for item in batch],
        "hard_negative": [item["hard_negative"] for item in batch],
        "tmk": [item["tmk"] for item in batch],
        "hn_type": [item["hn_type"] for item in batch],
        "hard_negative_field": [item["hard_negative_field"] for item in batch],
        "epoch1_similarity": [item["epoch1_similarity"] for item in batch],
        "orientation": [item["orientation"] for item in batch],
    }


__all__ = [
    "ALLOWED_HN_TYPES",
    "ALLOWED_SPLITS",
    "DEFAULT_DATA_PATH",
    "MiraPairDataset",
    "MiraTripletDataset",
    "PairRecord",
    "TripletRecord",
    "build_triplets_from_pairs_df",
    "check_tmk_leakage",
    "collate_pairs",
    "collate_triplets",
    "create_split_dataset",
    "dataframe_to_records",
    "dataframe_to_triplet_records",
    "find_project_root",
    "is_corrupt_tmk",
    "load_pairs_dataframe",
    "normalize_description",
    "normalize_optional_text",
    "normalize_pair_type",
    "normalize_split",
    "normalize_tmk",
    "optional_string",
    "summarize_dataframe",
    "validate_dataframe",
]
