"""
Production-Parity Feature Extraction Pipeline for MIRA Evaluation.

Extracts the five production matching features for candidate pairs:
1. text_similarity
2. semantic_similarity (via SentenceTransformer / EmbeddingCache)
3. specification_similarity (category-aware)
4. material_grade_similarity (via value_similarity)
5. other_attributes_similarity

Preserves category-specific specification handling, parsed specifications,
material grades, and critical gates for full decision evaluation.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd

from app.services.matching.critical_gates import evaluate_critical_gates
from app.services.matching.embeddings import (
    EmbeddingCache,
    get_embedding_model_name,
    precompute_embeddings,
)
from app.services.matching.similarity import (
    semantic_similarity,
    specification_similarity,
    text_similarity,
    value_similarity,
)
from app.services.normalization.service import normalize_material_description
from app.services.parsing.service import parse_specifications

OUTPUT_DIR = Path("data/evaluation/features")


def prepare_material(
    desc: str,
    category: Optional[str] = None,
    material_grade: Optional[str] = None,
    other_attributes: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Prepare a material record using the exact production pipeline."""
    norm_desc = normalize_material_description(desc)
    specs = parse_specifications(desc)
    grade = material_grade or specs.get("material_grade")
    return {
        "description": desc,
        "category": category,
        "normalized_description": norm_desc,
        "parsed_specifications": specs,
        "material_grade": grade,
        "dimensions": specs.get("dimensions"),
        "other_attributes": other_attributes or {},
    }


def extract_pair_features(
    source_desc: str,
    target_desc: str,
    category: Optional[str] = None,
    embedding_cache: Optional[EmbeddingCache] = None,
    model_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Calculate the 5 production features and evaluate critical gates for a pair."""
    source = prepare_material(source_desc, category=category)
    target = prepare_material(target_desc, category=category)

    t_sim = text_similarity(source["normalized_description"], target["normalized_description"])
    s_sim = semantic_similarity(
        source["normalized_description"],
        target["normalized_description"],
        embedding_cache=embedding_cache,
        model_name=model_name,
    )
    spec_sim = specification_similarity(
        source["parsed_specifications"],
        target["parsed_specifications"],
        category=category,
    )
    grade_sim = value_similarity(source["material_grade"], target["material_grade"])

    left_other = source.get("other_attributes")
    right_other = target.get("other_attributes")
    if not left_other and not right_other:
        other_sim = 1.0
    else:
        other_sim = specification_similarity(left_other, right_other)

    critical_checks = evaluate_critical_gates(source, target)

    return {
        "text_similarity": round(float(t_sim), 6),
        "semantic_similarity": round(float(s_sim), 6),
        "specification_similarity": round(float(spec_sim), 6),
        "material_grade_similarity": round(float(grade_sim), 6),
        "other_attributes_similarity": round(float(other_sim), 6),
        "critical_checks": critical_checks,
    }


def extract_features_for_dataframe(
    df: pd.DataFrame,
    desc_a_col: str = "desc_a",
    desc_b_col: str = "desc_b",
    category_col: str = "category",
    model_name: Optional[str] = None,
    batch_size: int = 256,
) -> pd.DataFrame:
    """Batch extract production-parity features for a dataframe with embedding precomputation."""
    model_identifier = model_name or get_embedding_model_name()
    texts_a = df[desc_a_col].fillna("").astype(str).tolist()
    texts_b = df[desc_b_col].fillna("").astype(str).tolist()
    categories = df[category_col].fillna("").astype(str).tolist() if category_col in df.columns else [None] * len(df)

    # Precompute normalized embeddings
    unique_texts = list(set([
        normalize_material_description(t) for t in (texts_a + texts_b) if t
    ]))
    cache = precompute_embeddings(unique_texts, batch_size=batch_size, model_name=model_identifier)

    records: List[Dict[str, Any]] = []
    for idx, (da, db, cat) in enumerate(zip(texts_a, texts_b, categories)):
        feats = extract_pair_features(
            source_desc=da,
            target_desc=db,
            category=cat if cat else None,
            embedding_cache=cache,
            model_name=model_identifier,
        )
        row_dict = dict(df.iloc[idx])
        row_dict.update({
            "text_similarity": feats["text_similarity"],
            "semantic_similarity": feats["semantic_similarity"],
            "specification_similarity": feats["specification_similarity"],
            "material_grade_similarity": feats["material_grade_similarity"],
            "other_attributes_similarity": feats["other_attributes_similarity"],
            "critical_checks_json": json.dumps(feats["critical_checks"]),
            "semantic_model": model_identifier,
        })
        records.append(row_dict)

    return pd.DataFrame(records)


def extract_and_save_all(
    input_csv: str = "Training_Pairs_MIRA_FINAL.csv",
    hard_negatives_csv: str = "data/evaluation/dataset_a_hard_negatives.csv",
    model_name: Optional[str] = None,
) -> Dict[str, str]:
    """Extract features for DEV, HELDOUT, and 300 Hard Negatives and save to features directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"_{model_name}" if model_name else ""

    print(f"Loading master dataset from {input_csv}...")
    df_all = pd.read_csv(input_csv, low_memory=False)

    df_dev = df_all[df_all["split"] == "dev"].reset_index(drop=True)
    df_heldout = df_all[df_all["split"] == "heldout"].reset_index(drop=True)

    print(f"Extracting features for DEV ({len(df_dev)} pairs)...")
    dev_feats = extract_features_for_dataframe(df_dev, model_name=model_name)
    dev_path = OUTPUT_DIR / f"dev_features{suffix}.csv"
    dev_feats.to_csv(dev_path, index=False)
    print(f"Saved DEV features to {dev_path}")

    print(f"Extracting features for HELDOUT ({len(df_heldout)} pairs)...")
    heldout_feats = extract_features_for_dataframe(df_heldout, model_name=model_name)
    heldout_path = OUTPUT_DIR / f"heldout_features{suffix}.csv"
    heldout_feats.to_csv(heldout_path, index=False)
    print(f"Saved HELDOUT features to {heldout_path}")

    print(f"Loading and extracting features for Hard Negatives ({hard_negatives_csv})...")
    df_hn = pd.read_csv(hard_negatives_csv)
    df_hn_mapped = df_hn.rename(columns={
        "source_description": "desc_a",
        "target_description": "desc_b",
    })
    df_hn_mapped["label"] = 0
    df_hn_mapped["pair_type"] = "HARD_NEGATIVE_BENCHMARK"
    hn_feats = extract_features_for_dataframe(df_hn_mapped, model_name=model_name)
    hn_path = OUTPUT_DIR / f"hard_negatives_features{suffix}.csv"
    hn_feats.to_csv(hn_path, index=False)
    print(f"Saved Hard Negatives features to {hn_path}")

    return {
        "dev": str(dev_path),
        "heldout": str(heldout_path),
        "hard_negatives": str(hn_path),
    }


if __name__ == "__main__":
    extract_and_save_all()
