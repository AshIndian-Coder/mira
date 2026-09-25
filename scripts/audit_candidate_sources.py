"""
Audit candidate data sources for Step 7 Independent Stress-Test Construction.
"""
import os
import glob
import json
import pandas as pd
import numpy as np

def run_audit():
    print("=== STEP 1: AUDITING AVAILABLE REAL CPSE DATA SOURCES ===")

    # 1. Load Training and Existing Evaluation Datasets for overlap reference
    print("Loading baseline/training datasets for leakage & overlap tracking...")
    train_final = pd.read_csv('Training_Pairs_MIRA_FINAL.csv', low_memory=False)
    dev_feat = pd.read_csv('data/evaluation/features/dev_features.csv')
    heldout_feat = pd.read_csv('data/evaluation/features/heldout_features.csv')
    hn_df = pd.read_csv('data/evaluation/dataset_a_hard_negatives.csv')
    step6_df = pd.read_csv('data/evaluation/dataset_a_heldout.csv')

    train_pairs_set = set(train_final['pair_id'].astype(str))
    dev_pairs_set = set(dev_feat['pair_id'].astype(str))
    heldout_pairs_set = set(heldout_feat['pair_id'].astype(str))
    hn_pairs_set = set(hn_df['pair_id'].astype(str))
    step6_pairs_set = set(step6_df['pair_id'].astype(str))

    # Normalized descriptions in training / evaluation
    def norm_text(t):
        if pd.isna(t): return ""
        return " ".join(str(t).strip().lower().split())

    train_desc_pairs = set()
    for _, r in train_final.iterrows():
        da, db = norm_text(r['desc_a']), norm_text(r['desc_b'])
        train_desc_pairs.add((da, db))
        train_desc_pairs.add((db, da))

    dev_desc_pairs = set()
    for _, r in dev_feat.iterrows():
        da, db = norm_text(r['desc_a']), norm_text(r['desc_b'])
        dev_desc_pairs.add((da, db))
        dev_desc_pairs.add((db, da))

    heldout_desc_pairs = set()
    for _, r in heldout_feat.iterrows():
        da, db = norm_text(r['desc_a']), norm_text(r['desc_b'])
        heldout_desc_pairs.add((da, db))
        heldout_desc_pairs.add((db, da))

    hn_desc_pairs = set()
    for _, r in hn_df.iterrows():
        da, db = norm_text(r['source_description']), norm_text(r['target_description'])
        hn_desc_pairs.add((da, db))
        hn_desc_pairs.add((db, da))

    train_mat_codes = set(train_final['material_code_a'].dropna().astype(str)).union(set(train_final['material_code_b'].dropna().astype(str)))
    dev_mat_codes = set(dev_feat['material_code_a'].dropna().astype(str)).union(set(dev_feat['material_code_b'].dropna().astype(str)))
    heldout_mat_codes = set(heldout_feat['material_code_a'].dropna().astype(str)).union(set(heldout_feat['material_code_b'].dropna().astype(str)))
    hn_mat_codes = set(hn_df['source_material_code'].dropna().astype(str)).union(set(hn_df['target_material_code'].dropna().astype(str)))

    train_tmks = set(train_final['tmk_a'].dropna().astype(str)).union(set(train_final['tmk_b'].dropna().astype(str)))
    dev_tmks = set(dev_feat['tmk_a'].dropna().astype(str)).union(set(dev_feat['tmk_b'].dropna().astype(str)))
    heldout_tmks = set(heldout_feat['tmk_a'].dropna().astype(str)).union(set(heldout_feat['tmk_b'].dropna().astype(str)))

    all_prior_mat_codes = train_mat_codes | dev_mat_codes | heldout_mat_codes | hn_mat_codes

    print(f"Loaded {len(train_pairs_set)} train pairs, {len(dev_pairs_set)} dev pairs, {len(heldout_pairs_set)} heldout pairs.")

    # List candidate sources to audit
    candidates = [
        {
            "name": "Original_company_records_no_synthetic.csv",
            "path": "Original_company_records_no_synthetic.csv",
            "type_guess": "real raw/processed company records"
        },
        {
            "name": "Final_Master_Material_Records.csv",
            "path": "Final_Master_Material_Records.csv",
            "type_guess": "real/derived CPSE master records"
        },
        {
            "name": "makt.csv",
            "path": "makt.csv",
            "type_guess": "real SAP ERP material descriptions table"
        },
        {
            "name": "mara.csv",
            "path": "mara.csv",
            "type_guess": "real SAP ERP general material attributes table"
        },
        {
            "name": "mard.csv",
            "path": "mard.csv",
            "type_guess": "real SAP ERP storage / plant material data table"
        },
        {
            "name": "data/processed/materials_all_enriched.csv",
            "path": "data/processed/materials_all_enriched.csv",
            "type_guess": "processed enriched CPSE material records"
        },
        {
            "name": "data/processed/ntpc_materials.csv",
            "path": "data/processed/ntpc_materials.csv",
            "type_guess": "processed NTPC material records"
        },
        {
            "name": "data/processed/bhel_materials.csv",
            "path": "data/processed/bhel_materials.csv",
            "type_guess": "processed BHEL material records"
        },
        {
            "name": "data/processed/nalco_materials.csv",
            "path": "data/processed/nalco_materials.csv",
            "type_guess": "processed NALCO material records"
        },
        {
            "name": "data/evaluation/dataset_a_dev.csv",
            "path": "data/evaluation/dataset_a_dev.csv",
            "type_guess": "existing evaluation dev dataset"
        },
        {
            "name": "data/evaluation/dataset_a_heldout.csv",
            "path": "data/evaluation/dataset_a_heldout.csv",
            "type_guess": "existing evaluation heldout dataset"
        },
        {
            "name": "data/evaluation/dataset_a_hard_negatives.csv",
            "path": "data/evaluation/dataset_a_hard_negatives.csv",
            "type_guess": "existing evaluation hard negatives dataset"
        },
        {
            "name": "data/training/ntpc_weak_labels.csv",
            "path": "data/training/ntpc_weak_labels.csv",
            "type_guess": "weak labeled candidate pairs"
        }
    ]

    audit_results = []

    for cand in candidates:
        path = cand["path"]
        name = cand["name"]
        if not os.path.exists(path):
            print(f"File not found: {path}")
            continue

        print(f"\n--- Auditing: {name} ---")
        try:
            # Read first chunk or full df if reasonable size
            file_size_mb = os.path.getsize(path) / (1024 * 1024)
            if file_size_mb > 150:
                print(f"Large file ({file_size_mb:.1f} MB), reading sample/iteratively...")
                df = pd.read_csv(path, nrows=50000, low_memory=False)
                # Count total lines efficiently
                with open(path, 'rb') as f:
                    total_rows = sum(1 for _ in f) - 1
            else:
                df = pd.read_csv(path, low_memory=False)
                total_rows = len(df)
        except Exception as e:
            print(f"Error reading {path}: {e}")
            continue

        cols = list(df.columns)

        # CPSE coverage
        cpse_col = None
        for col in ['organization', 'cpse_code', 'cpse', 'source_cpse', 'mandt']:
            if col in df.columns:
                cpse_col = col
                break

        if cpse_col:
            cpse_counts = df[cpse_col].value_counts(dropna=False).head(10).to_dict()
            cpse_coverage = list(df[cpse_col].dropna().astype(str).unique())
        else:
            cpse_coverage = ["N/A"]
            cpse_counts = {}

        # Available material identifiers
        mat_id_cols = [c for c in cols if 'code' in c.lower() or 'matnr' in c.lower() or 'material' in c.lower() or 'part' in c.lower()]
        mat_id_counts = {c: df[c].notna().sum() for c in mat_id_cols}

        # Description coverage
        desc_cols = [c for c in cols if 'desc' in c.lower() or 'makt' in c.lower() or 'search_text' in c.lower()]
        desc_cov = {}
        for c in desc_cols:
            non_null = df[c].notna().sum()
            desc_cov[c] = f"{non_null}/{len(df)} ({non_null/len(df)*100:.1f}%)"

        # Specification coverage
        spec_cols = [c for c in cols if any(k in c.lower() for k in ['spec', 'dim', 'attr', 'size', 'rating', 'voltage', 'thread', 'bore'])]
        spec_cov = {}
        for c in spec_cols:
            non_null = df[c].notna().sum()
            spec_cov[c] = f"{non_null}/{len(df)} ({non_null/len(df)*100:.1f}%)"

        # Category coverage
        cat_cols = [c for c in cols if 'cat' in c.lower() or 'group' in c.lower() or 'type' in c.lower()]
        cat_cov = {}
        for c in cat_cols:
            non_null = df[c].notna().sum()
            top_cats = df[c].value_counts(dropna=False).head(5).to_dict()
            cat_cov[c] = {"coverage": f"{non_null}/{len(df)} ({non_null/len(df)*100:.1f}%)", "top_5": top_cats}

        # Material-grade coverage
        grade_cols = [c for c in cols if 'grade' in c.lower() or 'moc' in c.lower()]
        grade_cov = {}
        for c in grade_cols:
            non_null = df[c].notna().sum()
            grade_cov[c] = f"{non_null}/{len(df)} ({non_null/len(df)*100:.1f}%)"

        # Material code overlap check
        cand_mat_codes = set()
        for c in mat_id_cols:
            if c in df.columns:
                cand_mat_codes.update(df[c].dropna().astype(str).unique())

        overlap_codes = cand_mat_codes & all_prior_mat_codes

        # Check real/synthetic/derived
        # Check if contains synthetic flags or indicators
        is_synthetic = False
        if 'synthetic' in name.lower() or 'synthetic_id' in cols:
            is_synthetic = True
        elif 'Original_company_records_no_synthetic' in name:
            is_synthetic = False

        # Overlap with training pairs
        train_overlap_count = 0
        if 'pair_id' in cols:
            train_overlap_count = len(set(df['pair_id'].astype(str)) & train_pairs_set)

        summary = {
            "source_name": str(name),
            "total_records": int(total_rows),
            "sample_audited": int(len(df)),
            "cpse_coverage": [str(x) for x in cpse_coverage[:10]],
            "cpse_distribution": {str(k): int(v) for k, v in cpse_counts.items()},
            "material_id_columns": [str(c) for c in mat_id_cols],
            "material_id_counts": {str(k): int(v) for k, v in mat_id_counts.items()},
            "description_coverage": {str(k): str(v) for k, v in desc_cov.items()},
            "specification_coverage": {str(k): str(v) for k, v in spec_cov.items()},
            "category_coverage": {str(k): {"coverage": str(v["coverage"]), "top_5": {str(ck): int(cv) for ck, cv in v["top_5"].items()}} for k, v in cat_cov.items()},
            "material_grade_coverage": {str(k): str(v) for k, v in grade_cov.items()},
            "data_nature": str("Synthetic" if is_synthetic else "Real / Enriched / Derived"),
            "material_code_overlap_with_prior_train_dev_heldout": int(len(overlap_codes)),
            "material_code_overlap_pct": f"{len(overlap_codes)/max(1, len(cand_mat_codes))*100:.2f}%",
            "direct_pair_id_overlap_with_train": int(train_overlap_count)
        }

        audit_results.append(summary)
        print(f"Record count: {total_rows}")
        print(f"CPSEs: {cpse_coverage[:10]}")
        print(f"Material codes overlap: {len(overlap_codes)} / {len(cand_mat_codes)} ({len(overlap_codes)/max(1, len(cand_mat_codes))*100:.2f}%)")

    class NpEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (np.integer, np.int64, np.int32)):
                return int(obj)
            elif isinstance(obj, (np.floating, np.float64, np.float32)):
                return float(obj)
            elif isinstance(obj, (np.ndarray,)):
                return obj.tolist()
            return super(NpEncoder, self).default(obj)

    with open('data/evaluation/candidate_sources_audit_report.json', 'w') as f:
        json.dump(audit_results, f, indent=2, cls=NpEncoder)
    print("\nSaved detailed audit to data/evaluation/candidate_sources_audit_report.json")

if __name__ == '__main__':
    run_audit()
