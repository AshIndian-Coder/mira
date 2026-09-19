from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent

BASE_DATASET = (
    BASE_DIR
    / "train_data"
    / "training"
    / "Training_Pairs_MIRA_FINAL.csv"
)

HN_POOL = (
    BASE_DIR
    / "results"
    / "epoch2"
    / "hn_true_keep_all.csv"
)

OUTPUT_DIR = (
    BASE_DIR
    / "results"
    / "epoch2"
)

OUTPUT_DATASET = (
    OUTPUT_DIR
    / "Training_Pairs_MIRA_EPOCH2.csv"
)

MANIFEST_PATH = (
    OUTPUT_DIR
    / "epoch2_dataset_manifest.json"
)

ALLOWED_HN_FIELDS = {
    "dimensions",
    "size_or_model",
}

ALLOWED_HN_TYPES = {
    "HN_CORRUPT",
    "HN_SIBLING",
}

DEFAULT_HN_REPEAT = 4

REQUIRED_BASE_COLUMNS = {
    "pair_id",
    "desc_a",
    "desc_b",
    "label",
    "split",
    "pair_type",
}

REQUIRED_HN_COLUMNS = {
    "pair_id",
    "desc_a",
    "desc_b",
    "label",
    "pair_type",
    "hard_negative_field",
    "epoch1_similarity",
}


def normalize_text(
    value: object,
) -> str:
    if pd.isna(value):
        return ""

    return " ".join(
        str(value)
        .strip()
        .split()
    )


def normalize_split(
    value: object,
) -> str:
    if pd.isna(value):
        return ""

    return (
        str(value)
        .strip()
        .lower()
    )


def canonical_pair_text(
    value: object,
) -> str:
    text = normalize_text(
        value
    ).upper()

    if not text:
        return ""

    text = re.sub(
        r"\bDN\s*(\d+(?:\.\d+)?)\b",
        r"NB\1",
        text,
    )

    text = re.sub(
        r"\b(\d+(?:\.\d+)?)\s*NB\b",
        r"NB\1",
        text,
    )

    text = re.sub(
        r"[\s\-_/,:;()]+",
        "",
        text,
    )

    return text


def make_pair_key(
    desc_a: object,
    desc_b: object,
) -> str:
    a = canonical_pair_text(
        desc_a
    )

    b = canonical_pair_text(
        desc_b
    )

    low, high = (
        (a, b)
        if a <= b
        else (b, a)
    )

    return (
        f"{low}||{high}"
    )


def validate_base_dataframe(
    df: pd.DataFrame,
) -> None:
    missing = (
        REQUIRED_BASE_COLUMNS
        - set(df.columns)
    )

    if missing:
        raise ValueError(
            "Base dataset is missing required columns:\n"
            + "\n".join(
                f"  - {column}"
                for column
                in sorted(missing)
            )
        )


def validate_hn_dataframe(
    df: pd.DataFrame,
) -> None:
    missing = (
        REQUIRED_HN_COLUMNS
        - set(df.columns)
    )

    if missing:
        raise ValueError(
            "HN pool is missing required columns:\n"
            + "\n".join(
                f"  - {column}"
                for column
                in sorted(missing)
            )
        )


def validate_labels(
    df: pd.DataFrame,
    name: str,
) -> None:
    labels = pd.to_numeric(
        df["label"],
        errors="coerce",
    )

    if labels.isna().any():
        raise ValueError(
            f"{name} contains non-numeric labels."
        )

    labels = labels.astype(int)

    invalid = ~labels.isin(
        [0, 1]
    )

    if invalid.any():
        raise ValueError(
            f"{name} contains "
            f"{int(invalid.sum())} invalid labels."
        )


def validate_similarity(
    df: pd.DataFrame,
) -> None:
    values = pd.to_numeric(
        df["epoch1_similarity"],
        errors="coerce",
    )

    if values.isna().any():
        raise ValueError(
            "HN pool contains non-numeric "
            "epoch1_similarity values."
        )

    if not values.between(
        -1.0,
        1.0,
    ).all():
        raise ValueError(
            "HN pool contains similarity "
            "values outside [-1, 1]."
        )


def deduplicate_hard_negatives(
    hn_df: pd.DataFrame,
) -> pd.DataFrame:
    if hn_df.empty:
        return hn_df.copy()

    work = hn_df.copy()

    work["_pair_key"] = [
        make_pair_key(
            row["desc_a"],
            row["desc_b"],
        )
        for _, row
        in work.iterrows()
    ]

    work["_similarity"] = pd.to_numeric(
        work["epoch1_similarity"],
        errors="raise",
    )

    work = (
        work
        .sort_values(
            "_similarity",
            ascending=False,
            kind="stable",
        )
        .drop_duplicates(
            subset=["_pair_key"],
            keep="first",
        )
        .drop(
            columns=[
                "_pair_key",
                "_similarity",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    return work


def validate_hn_pair_ids(
    hn_df: pd.DataFrame,
) -> None:
    duplicate_ids = (
        hn_df["pair_id"]
        .astype(str)
        .duplicated(
            keep=False
        )
    )

    if duplicate_ids.any():
        values = (
            hn_df.loc[
                duplicate_ids,
                "pair_id",
            ]
            .astype(str)
            .drop_duplicates()
            .head(20)
            .tolist()
        )

        raise ValueError(
            "HN pool contains duplicate pair_id values:\n"
            + "\n".join(
                f"  - {value}"
                for value in values
            )
        )


def find_train_pair_collisions(
    base_train_non_hn: pd.DataFrame,
    hn_df: pd.DataFrame,
) -> pd.DataFrame:
    existing_keys = {
        make_pair_key(
            row["desc_a"],
            row["desc_b"],
        )
        for _, row
        in base_train_non_hn.iterrows()
    }

    collision_mask = []

    for _, row in hn_df.iterrows():
        collision_mask.append(
            make_pair_key(
                row["desc_a"],
                row["desc_b"],
            )
            in existing_keys
        )

    return hn_df.loc[
        collision_mask
    ].copy()


def prepare_hn_rows(
    hn_df: pd.DataFrame,
    base_columns: list[str],
) -> pd.DataFrame:
    work = hn_df.copy()

    work["label"] = 0
    work["split"] = "train"

    work["desc_a"] = (
        work["desc_a"]
        .map(normalize_text)
    )

    work["desc_b"] = (
        work["desc_b"]
        .map(normalize_text)
    )

    work["pair_type"] = (
        work["pair_type"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    work["hard_negative_field"] = (
        work["hard_negative_field"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
    )

    return work[
        base_columns
    ].copy()


def validate_final_dataframe(
    final_df: pd.DataFrame,
    base_df: pd.DataFrame,
    expected_train_rows: int,
) -> None:

    if list(final_df.columns) != list(
        base_df.columns
    ):
        raise RuntimeError(
            "Final dataset schema does not "
            "match the base dataset."
        )

    if len(final_df) == 0:
        raise RuntimeError(
            "Final dataset is empty."
        )

    train_mask = (
        final_df["split"]
        == "train"
    )

    dev_mask = (
        final_df["split"]
        == "dev"
    )

    heldout_mask = (
        final_df["split"]
        == "heldout"
    )

    if int(train_mask.sum()) != (
        expected_train_rows
    ):
        raise RuntimeError(
            "Final TRAIN row count is incorrect."
        )

    if not dev_mask.any():
        raise RuntimeError(
            "Final DEV split is missing."
        )

    if not heldout_mask.any():
        raise RuntimeError(
            "Final HELD-OUT split is missing."
        )

    surviving_hn = final_df.loc[
        train_mask,
        "pair_type",
    ].fillna("").astype(str).str.upper().str.startswith("HN_")

    original_hn_count = int(
        surviving_hn.sum()
    )

    if original_hn_count != (
        final_df.loc[
            train_mask,
            "pair_type",
        ].isin(
            ALLOWED_HN_TYPES
        ).sum()
    ):
        raise RuntimeError(
            "Unexpected HN pair types "
            "remain in final TRAIN."
        )


def compare_preserved_split(
    before: pd.DataFrame,
    after: pd.DataFrame,
    split: str,
) -> None:
    before_part = (
        before[
            before["split"] == split
        ]
        .reset_index(
            drop=True
        )
    )

    after_part = (
        after[
            after["split"] == split
        ]
        .reset_index(
            drop=True
        )
    )

    if not before_part.equals(
        after_part
    ):
        raise RuntimeError(
            f"{split.upper()} changed."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build the MIRA Epoch-2 "
            "training dataset."
        )
    )

    parser.add_argument(
        "--hn-repeat",
        type=int,
        default=DEFAULT_HN_REPEAT,
        help="HN repeat factor. Default: 4",
    )

    args = parser.parse_args()

    if args.hn_repeat < 1:
        parser.error(
            "--hn-repeat must be >= 1."
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not BASE_DATASET.is_file():
        raise FileNotFoundError(
            "Base dataset not found:\n"
            f"{BASE_DATASET.resolve()}"
        )

    if not HN_POOL.is_file():
        raise FileNotFoundError(
            "HN pool not found:\n"
            f"{HN_POOL.resolve()}"
        )

    print("=" * 78)
    print(
        "MIRA — EPOCH 2 DATASET BUILDER"
    )
    print("=" * 78)

    base_df = pd.read_csv(
        BASE_DATASET,
        low_memory=False,
    )

    hn_df = pd.read_csv(
        HN_POOL,
        low_memory=False,
    )

    if base_df.empty:
        raise RuntimeError(
            "Base dataset is empty."
        )

    if hn_df.empty:
        raise RuntimeError(
            "HN pool is empty."
        )

    validate_base_dataframe(
        base_df
    )

    validate_hn_dataframe(
        hn_df
    )

    validate_labels(
        base_df,
        "Base dataset",
    )

    validate_labels(
        hn_df,
        "HN pool",
    )

    validate_similarity(
        hn_df
    )

    base_df["split"] = (
        base_df["split"]
        .map(normalize_split)
    )

    base_df["desc_a"] = (
        base_df["desc_a"]
        .map(normalize_text)
    )

    base_df["desc_b"] = (
        base_df["desc_b"]
        .map(normalize_text)
    )

    hn_df["desc_a"] = (
        hn_df["desc_a"]
        .map(normalize_text)
    )

    hn_df["desc_b"] = (
        hn_df["desc_b"]
        .map(normalize_text)
    )

    hn_df["label"] = (
        pd.to_numeric(
            hn_df["label"],
            errors="raise",
        )
        .astype(int)
    )

    hn_df["pair_type"] = (
        hn_df["pair_type"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    hn_df["hard_negative_field"] = (
        hn_df["hard_negative_field"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
    )

    hn_df["epoch1_similarity"] = (
        pd.to_numeric(
            hn_df["epoch1_similarity"],
            errors="raise",
        )
        .astype(float)
    )

    if not hn_df["label"].eq(0).all():
        raise ValueError(
            "HN pool contains non-zero labels."
        )

    if (
        hn_df["pair_type"]
        .isin(ALLOWED_HN_TYPES)
        .eq(False)
        .any()
    ):
        bad_types = sorted(
            hn_df.loc[
                ~hn_df["pair_type"].isin(
                    ALLOWED_HN_TYPES
                ),
                "pair_type",
            ].unique()
        )

        raise ValueError(
            "HN pool contains unsupported pair types:\n"
            + "\n".join(
                f"  - {value}"
                for value in bad_types
            )
        )

    filtered_fields = hn_df[
        ~hn_df[
            "hard_negative_field"
        ].isin(ALLOWED_HN_FIELDS)
    ]

    filtered_field_counts = (
        filtered_fields[
            "hard_negative_field"
        ]
        .value_counts()
        .to_dict()
    )

    hn_df = hn_df[
        hn_df[
            "hard_negative_field"
        ].isin(ALLOWED_HN_FIELDS)
    ].copy()

    if hn_df.empty:
        raise RuntimeError(
            "No dimensions/size_or_model "
            "HNs remain."
        )

    validate_hn_pair_ids(
        hn_df
    )

    hn_before_dedup = len(
        hn_df
    )

    hn_df = deduplicate_hard_negatives(
        hn_df
    )

    hn_after_dedup = len(
        hn_df
    )

    if hn_after_dedup == 0:
        raise RuntimeError(
            "No HNs remain after deduplication."
        )

    base_train = base_df[
        base_df["split"] == "train"
    ].copy()

    base_dev = base_df[
        base_df["split"] == "dev"
    ].copy()

    base_heldout = base_df[
        base_df["split"] == "heldout"
    ].copy()

    if base_train.empty:
        raise RuntimeError(
            "Base TRAIN split is empty."
        )

    if base_dev.empty:
        raise RuntimeError(
            "Base DEV split is empty."
        )

    if base_heldout.empty:
        raise RuntimeError(
            "Base HELD-OUT split is empty."
        )

    original_hn_mask = (
        base_train["pair_type"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .str.startswith("HN_")
    )

    original_hn_count = int(
        original_hn_mask.sum()
    )

    base_train_non_hn = (
        base_train[
            ~original_hn_mask
        ]
        .copy()
    )

    if base_train_non_hn.empty:
        raise RuntimeError(
            "No TRAIN rows remain after "
            "removing original HNs."
        )

    collisions = find_train_pair_collisions(
        base_train_non_hn,
        hn_df,
    )

    if not collisions.empty:
        sample = collisions[
            [
                "pair_id",
                "desc_a",
                "desc_b",
            ]
        ].head(10)

        formatted = "\n".join(
            (
                f"{row.pair_id}: "
                f"{row.desc_a} <-> "
                f"{row.desc_b}"
            )
            for row in sample.itertuples()
        )

        raise RuntimeError(
            "Audited HNs collide with existing "
            "non-HN TRAIN pairs.\n"
            f"Sample:\n{formatted}"
        )

    base_columns = list(
        base_df.columns
    )

    clean_hn = prepare_hn_rows(
        hn_df,
        base_columns,
    )

    epoch2_hn = pd.concat(
        [
            clean_hn
            for _ in range(
                args.hn_repeat
            )
        ],
        ignore_index=True,
    )

    train_output = pd.concat(
        [
            base_train_non_hn,
            epoch2_hn,
        ],
        ignore_index=True,
    )

    output_df = pd.concat(
        [
            train_output,
            base_dev[
                base_columns
            ],
            base_heldout[
                base_columns
            ],
        ],
        ignore_index=True,
    )

    expected_train_rows = (
        len(base_train_non_hn)
        + len(epoch2_hn)
    )

    validate_final_dataframe(
        output_df,
        base_df,
        expected_train_rows,
    )

    compare_preserved_split(
        base_df,
        output_df,
        "dev",
    )

    compare_preserved_split(
        base_df,
        output_df,
        "heldout",
    )

    final_train = output_df[
        output_df["split"] == "train"
    ].copy()

    final_hn_mask = (
        final_train["pair_type"]
        .fillna("")
        .astype(str)
        .str.upper()
        .str.startswith("HN_")
    )

    final_hn = final_train[
        final_hn_mask
    ].copy()

    if final_hn.empty:
        raise RuntimeError(
            "Final TRAIN contains no Epoch-2 HNs."
        )

    final_hn_fields = set(
        final_hn[
            "hard_negative_field"
        ]
        .fillna("")
        .astype(str)
        .str.lower()
        .unique()
    )

    if not final_hn_fields.issubset(
        ALLOWED_HN_FIELDS
    ):
        raise RuntimeError(
            "Final TRAIN contains an "
            "unauthorized HN field."
        )

    final_hn_types = set(
        final_hn[
            "pair_type"
        ]
        .fillna("")
        .astype(str)
        .str.upper()
        .unique()
    )

    if not final_hn_types.issubset(
        ALLOWED_HN_TYPES
    ):
        raise RuntimeError(
            "Final TRAIN contains an "
            "unauthorized HN type."
        )

    output_df.to_csv(
        OUTPUT_DATASET,
        index=False,
    )

    reloaded = pd.read_csv(
        OUTPUT_DATASET,
        low_memory=False,
    )

    validate_final_dataframe(
        reloaded,
        base_df,
        expected_train_rows,
    )

    compare_preserved_split(
        base_df,
        reloaded,
        "dev",
    )

    compare_preserved_split(
        base_df,
        reloaded,
        "heldout",
    )

    reloaded_hn_mask = (
        reloaded["split"].eq("train")
        & reloaded["pair_type"]
        .fillna("")
        .astype(str)
        .str.upper()
        .str.startswith("HN_")
    )

    reloaded_hn = reloaded[
        reloaded_hn_mask
    ]

    expected_hn_rows = (
        hn_after_dedup
        * args.hn_repeat
    )

    if len(reloaded_hn) != (
        expected_hn_rows
    ):
        raise RuntimeError(
            "Reloaded HN row count is incorrect."
        )

    if not reloaded_hn["label"].eq(
        0
    ).all():
        raise RuntimeError(
            "Reloaded Epoch-2 HNs contain "
            "non-zero labels."
        )

    remaining_original_hn = (
        reloaded.loc[
            reloaded["split"] == "train",
            "pair_type",
        ]
        .fillna("")
        .astype(str)
        .str.upper()
        .str.startswith("HN_")
    )

    if int(
        remaining_original_hn.sum()
    ) != expected_hn_rows:
        raise RuntimeError(
            "Unexpected HN rows remain in "
            "Epoch-2 TRAIN."
        )

    if list(
        reloaded.columns
    ) != base_columns:
        raise RuntimeError(
            "Reloaded dataset schema changed."
        )

    manifest = {
        "base_dataset": str(
            BASE_DATASET.resolve()
        ),
        "hn_pool": str(
            HN_POOL.resolve()
        ),
        "output_dataset": str(
            OUTPUT_DATASET.resolve()
        ),
        "configuration": {
            "hn_repeat": int(
                args.hn_repeat
            ),
            "allowed_hn_fields": sorted(
                ALLOWED_HN_FIELDS
            ),
            "allowed_hn_types": sorted(
                ALLOWED_HN_TYPES
            ),
            "original_train_hns_removed": True,
        },
        "counts": {
            "base_total_rows": int(
                len(base_df)
            ),
            "base_train_rows": int(
                len(base_train)
            ),
            "original_train_hn_rows_removed": int(
                original_hn_count
            ),
            "base_non_hn_train_rows": int(
                len(base_train_non_hn)
            ),
            "hn_pool_before_filter": int(
                hn_before_dedup
            ),
            "hn_pool_after_reverse_dedup": int(
                hn_after_dedup
            ),
            "epoch2_hn_rows_added": int(
                expected_hn_rows
            ),
            "final_train_rows": int(
                expected_train_rows
            ),
            "dev_rows": int(
                len(base_dev)
            ),
            "heldout_rows": int(
                len(base_heldout)
            ),
        },
        "filtered_hn_fields": {
            str(key): int(value)
            for key, value
            in filtered_field_counts.items()
        },
        "validation": {
            "schema_preserved": True,
            "dev_preserved": True,
            "heldout_preserved": True,
            "train_count_validated": True,
            "no_original_hn_rows_remaining": True,
            "no_train_pair_collisions": True,
            "output_reloaded_successfully": True,
            "hn_fields_validated": True,
            "hn_types_validated": True,
            "hn_labels_validated": True,
        },
    }

    MANIFEST_PATH.write_text(
        json.dumps(
            manifest,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        "\n" + "=" * 78
    )
    print(
        "EPOCH 2 DATASET BUILD COMPLETE"
    )
    print(
        "=" * 78
    )
    print(
        f"Original TRAIN rows:       "
        f"{len(base_train):,}"
    )
    print(
        f"Original TRAIN HNs removed:"
        f" {original_hn_count:,}"
    )
    print(
        f"Non-HN TRAIN retained:     "
        f"{len(base_train_non_hn):,}"
    )
    print(
        f"HN pool before dedup:      "
        f"{hn_before_dedup:,}"
    )
    print(
        f"HN pool after dedup:       "
        f"{hn_after_dedup:,}"
    )
    print(
        f"HN repeat factor:          "
        f"{args.hn_repeat}x"
    )
    print(
        f"Epoch-2 HN rows added:     "
        f"{expected_hn_rows:,}"
    )
    print(
        f"Final TRAIN rows:          "
        f"{expected_train_rows:,}"
    )
    print(
        f"DEV rows preserved:        "
        f"{len(base_dev):,}"
    )
    print(
        f"HELD-OUT rows preserved:   "
        f"{len(base_heldout):,}"
    )
    print(
        f"\nEpoch-2 dataset:\n"
        f"{OUTPUT_DATASET.resolve()}"
    )
    print(
        f"\nManifest:\n"
        f"{MANIFEST_PATH.resolve()}"
    )
    print(
        "=" * 78
    )


if __name__ == "__main__":
    main()