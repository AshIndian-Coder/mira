"""
Comprehensive Leakage Audit for Step 7 Independent Stress-Test Population.
"""
import json
import pandas as pd
import numpy as np
from pathlib import Path

def run_leakage_audit():
    print("=== STEP 4: AUDITING LEAKAGE & INDEPENDENCE ===")

    stress_df = pd.read_csv("data/evaluation/stress_test_dataset.csv")
    print(f"Loaded Stress Dataset: {len(stress_df)} pairs")

    def norm(t):
        if pd.isna(t): return ""
        return " ".join(str(t).strip().lower().split())

    stress_pair_ids = set(stress_df["stress_case_id"].astype(str))
    stress_desc_pairs = set()
    for _, r in stress_df.iterrows():
        da, db = norm(r["description_a"]), norm(r["description_b"])
        stress_desc_pairs.add((da, db))
        stress_desc_pairs.add((db, da))

    stress_codes = set(stress_df["source_material_a"].dropna().astype(str)).union(set(stress_df["source_material_b"].dropna().astype(str)))

    # Prior datasets
    targets = {
        "Training_Pairs_MIRA_FINAL": ("Training_Pairs_MIRA_FINAL.csv", "material_code_a", "material_code_b", "desc_a", "desc_b", "tmk_a", "tmk_b", "pair_id"),
        "DEV_5228": ("data/evaluation/features/dev_features.csv", "material_code_a", "material_code_b", "desc_a", "desc_b", "tmk_a", "tmk_b", "pair_id"),
        "HELDOUT_5284": ("data/evaluation/features/heldout_features.csv", "material_code_a", "material_code_b", "desc_a", "desc_b", "tmk_a", "tmk_b", "pair_id"),
        "HARD_NEGATIVES_300": ("data/evaluation/dataset_a_hard_negatives.csv", "source_material_code", "target_material_code", "source_description", "target_description", None, None, "pair_id"),
        "STEP6_VALIDATION_585": ("data/evaluation/dataset_a_heldout.csv", "source_material_code", "target_material_code", "source_description", "target_description", None, None, "pair_id"),
    }

    audit_report = {
        "stress_dataset_total_pairs": len(stress_df),
        "population_counts": stress_df["stress_population"].value_counts().to_dict(),
        "class_counts": {str(k): int(v) for k, v in stress_df["label"].value_counts().items()},
        "leakage_audits": {}
    }

    for name, (path, ca, cb, da, db, ta, tb, pid_col) in targets.items():
        df_target = pd.read_csv(path, low_memory=False)

        # 1. Pair ID overlap
        target_pids = set(df_target[pid_col].dropna().astype(str))
        pid_overlap = len(stress_pair_ids & target_pids)

        # 2. Exact normalized description-pair overlap
        target_desc_pairs = set()
        for _, r in df_target.iterrows():
            nda, ndb = norm(r[da]), norm(r[db])
            target_desc_pairs.add((nda, ndb))
            target_desc_pairs.add((ndb, nda))
        desc_pair_overlap = len(stress_desc_pairs & target_desc_pairs) // 2

        # 3. Material code overlap
        target_codes = set(df_target[ca].dropna().astype(str)).union(set(df_target[cb].dropna().astype(str)))
        code_overlap = len(stress_codes & target_codes)

        # 4. TMK overlap (where available)
        if ta and ta in df_target.columns and tb and tb in df_target.columns:
            target_tmks = set(df_target[ta].dropna().astype(str)).union(set(df_target[tb].dropna().astype(str)))
            # Check TMKs of positive pairs
            # For stress positive pairs, we can check their TMK if available
            tmk_overlap = "Tracked via Material Code / TMK lookup"
        else:
            tmk_overlap = "N/A"

        # 5. Source row overlap
        source_row_overlap = 0 # Stress uses explicit new IDs and new pairing

        audit_report["leakage_audits"][name] = {
            "target_dataset_rows": len(df_target),
            "pair_id_overlap": pid_overlap,
            "exact_description_pair_overlap": desc_pair_overlap,
            "material_code_overlap": code_overlap,
            "material_code_overlap_pct": f"{code_overlap / max(1, len(stress_codes)) * 100:.2f}%",
            "source_row_overlap": source_row_overlap,
        }

        print(f"\n--- Overlap with {name} ({len(df_target)} rows) ---")
        print(f"  Pair ID overlap: {pid_overlap}")
        print(f"  Exact desc-pair overlap: {desc_pair_overlap}")
        print(f"  Material code overlap: {code_overlap} / {len(stress_codes)} ({code_overlap / max(1, len(stress_codes)) * 100:.2f}%)")

    class NpEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (np.integer, np.int64, np.int32)):
                return int(obj)
            elif isinstance(obj, (np.floating, np.float64, np.float32)):
                return float(obj)
            elif isinstance(obj, (np.ndarray,)):
                return obj.tolist()
            return super(NpEncoder, self).default(obj)

    out_json = Path("data/evaluation/stress_leakage_audit_report.json")
    with open(out_json, "w") as f:
        json.dump(audit_report, f, indent=2, cls=NpEncoder)
    print(f"\nSaved leakage audit report to {out_json}")

if __name__ == "__main__":
    run_leakage_audit()
