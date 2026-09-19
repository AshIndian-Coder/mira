from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


TECHNICAL_FIELDS = [
    "groes",
    "wrkst",
    "normt",
    "laeng",
    "breit",
    "hoehe",
    "meabm",
    "mfrpn",
    "mfrnr",
]


OUTPUT_COLUMNS = [
    "synthetic_id",
    "mandt",
    "source_matnr",
    "description",
    "material_type",
    "material_group",
    "uom",
    "size",
    "material",
    "standard",
    "length",
    "width",
    "height",
    "dimension_uom",
    "manufacturer_part_number",
    "manufacturer",
]


def non_empty(series: pd.Series) -> pd.Series:
    return series.notna() & (series.astype(str).str.strip() != "")


def load_base_materials(
    mara_path: Path,
    makt_path: Path,
) -> pd.DataFrame:
    mara = pd.read_csv(mara_path, low_memory=False)
    makt = pd.read_csv(makt_path, low_memory=False)

    for df in (mara, makt):
        df["mandt"] = df["mandt"].astype(str).str.strip()
        df["matnr"] = df["matnr"].astype(str).str.strip()

    # Remove deleted MARA records.
    mara = mara[
        ~mara["is_deleted"].fillna(False).astype(bool)
    ].copy()

    # Keep active English descriptions.
    makt = makt[
        (makt["spras"].astype(str).str.strip().str.upper() == "E")
        & (~makt["is_deleted"].fillna(False).astype(bool))
    ].copy()

    makt["maktx"] = makt["maktx"].fillna("").astype(str).str.strip()
    makt = makt[non_empty(makt["maktx"])]

    # One English description per SAP client + material.
    makt = makt.drop_duplicates(
        subset=["mandt", "matnr"],
        keep="first",
    )

    df = mara.merge(
        makt[["mandt", "matnr", "maktx"]],
        on=["mandt", "matnr"],
        how="inner",
    )

    df = df.rename(columns={"maktx": "description"})

    # Remove duplicate SAP material keys after joining.
    df = df.drop_duplicates(
        subset=["mandt", "matnr"],
        keep="first",
    )

    # Remove empty descriptions.
    df = df[non_empty(df["description"])].copy()

    # Synthetic ID is deliberately independent of SAP MATNR.
    df = df.reset_index(drop=True)
    df.insert(
        0,
        "synthetic_id",
        [f"SYN_{i:06d}" for i in range(1, len(df) + 1)],
    )

    return df


def build_output(df: pd.DataFrame) -> pd.DataFrame:
    output = pd.DataFrame()

    output["synthetic_id"] = df["synthetic_id"]
    output["mandt"] = df["mandt"]
    output["source_matnr"] = df["matnr"]
    output["description"] = df["description"]
    output["material_type"] = df["mtart"]
    output["material_group"] = df["matkl"]
    output["uom"] = df["meins"]
    output["size"] = df["groes"]
    output["material"] = df["wrkst"]
    output["standard"] = df["normt"]
    output["length"] = df["laeng"]
    output["width"] = df["breit"]
    output["height"] = df["hoehe"]
    output["dimension_uom"] = df["meabm"]
    output["manufacturer_part_number"] = df["mfrpn"]
    output["manufacturer"] = df["mfrnr"]

    return output[OUTPUT_COLUMNS]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the clean synthetic-material seed dataset.",
    )

    parser.add_argument(
        "--mara",
        type=Path,
        default=Path("mara.csv"),
    )
    parser.add_argument(
        "--makt",
        type=Path,
        default=Path("makt.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/evaluation/synthetic/base_materials.csv"
        ),
    )

    args = parser.parse_args()

    df = load_base_materials(args.mara, args.makt)
    output = build_output(df)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output, index=False)

    print(f"MARA records loaded       : {len(pd.read_csv(args.mara, low_memory=False))}")
    print(f"Base materials generated  : {len(output)}")
    print(f"Output                    : {args.output}")


if __name__ == "__main__":
    main()
