"""
Synthetic Dataset A Generator for SIH26099 (MIRA)
Generates synthetic material master records, positive matching pairs, and hard negatives
for development, fine-tuning, and evaluation of the matching engine.
"""

import json
import random
import csv
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DEV_DIR = DATA_DIR / "dev"
EVAL_DIR = DATA_DIR / "evaluation"
SAMPLE_DIR = DATA_DIR / "sample"

for d in [DEV_DIR, EVAL_DIR, SAMPLE_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Fastener items
FASTENERS = [
    {
        "category": "Fastener",
        "type": "HEX HEAD BOLT",
        "synonyms": ["BOLT, HEX", "HEXAGONAL HEAD BOLT", "BOLT HEX"],
        "materials": ["SS304", "SS316", "CARBON STEEL", "ALLOY STEEL"],
        "grades": ["A2-70", "A4-80", "8.8", "10.9"],
        "diameters": ["M8", "M10", "M12", "M16", "M20", "M24"],
        "lengths": ["25", "30", "40", "50", "60", "75", "100"],
    }
]

# Valve items
VALVES = [
    {
        "category": "Valve",
        "type": "GATE VALVE",
        "synonyms": ["VALVE, GATE", "SLUICE VALVE", "GATE VALVE FLANGED"],
        "materials": ["SS304", "SS316", "CAST STEEL", "FORGED STEEL"],
        "pressure_ratings": [{"value": 150, "unit": "LB"}, {"value": 300, "unit": "LB"}, {"value": 600, "unit": "LB"}],
        "sizes": ["1 IN", "2 IN", "3 IN", "4 IN", "6 IN"],
    }
]

CPSES = ["CPSE_A", "CPSE_B", "CPSE_C", "CPSE_D"]


def make_material_record(cpse, code, desc, norm_desc, category, grade, specs):
    return {
        "cpse": cpse,
        "material_code": code,
        "description": desc,
        "normalized_description": norm_desc,
        "category": category,
        "material_grade": grade,
        "parsed_specifications": specs,
        "other_attributes": {}
    }


def generate_dataset_a():
    records = []
    pairs = []
    hard_negatives = []
    
    code_counter = 1000

    # 1. Generate Fasteners
    for item in FASTENERS:
        for mat in item["materials"]:
            for grd in item["grades"]:
                for dia in item["diameters"]:
                    for lng in item["lengths"]:
                        code_counter += 1
                        code_a = f"MAT-{code_counter}"
                        desc_a = f"{item['type']} {dia} X {lng} MM {mat} GRADE {grd}"
                        norm_desc_a = f"{item['type']} {dia} X {lng} MM {mat} {grd}".upper()
                        
                        specs_a = {
                            "dimensions": {"diameter": dia, "length": f"{lng} MM"},
                            "grade": grd
                        }
                        
                        rec_a = make_material_record("CPSE_A", code_a, desc_a, norm_desc_a, item["category"], grd, specs_a)
                        records.append(rec_a)
                        
                        # Generate Positive Match Pair
                        code_counter += 1
                        code_b = f"M-{code_counter}"
                        syn = random.choice(item["synonyms"])
                        desc_b = f"{syn}, {mat}, {grd}, SIZE {dia}x{lng}"
                        norm_desc_b = f"{syn} {mat} {grd} {dia} {lng}".upper()
                        
                        rec_b = make_material_record("CPSE_B", code_b, desc_b, norm_desc_b, item["category"], grd, specs_a)
                        records.append(rec_b)
                        
                        pairs.append({
                            "left": rec_a,
                            "right": rec_b,
                            "label": 1,
                            "reason": "Exact functional duplicate across CPSEs"
                        })
                        
                        # Generate Hard Negative Pair (Conflicting Grade: A2-70 vs A4-80)
                        alt_grd = "A4-80" if grd == "A2-70" else "A2-70"
                        desc_hn = f"{syn}, {mat}, {alt_grd}, SIZE {dia}x{lng}"
                        norm_desc_hn = f"{syn} {mat} {alt_grd} {dia} {lng}".upper()
                        specs_hn = {
                            "dimensions": {"diameter": dia, "length": f"{lng} MM"},
                            "grade": alt_grd
                        }
                        
                        rec_hn = make_material_record("CPSE_C", f"HN-{code_counter}", desc_hn, norm_desc_hn, item["category"], alt_grd, specs_hn)
                        hard_negatives.append({
                            "left": rec_a,
                            "right": rec_hn,
                            "label": 0,
                            "conflict_field": "grade",
                            "reason": f"Conflicting material grade: {grd} vs {alt_grd}"
                        })

    # 2. Generate Valves
    for item in VALVES:
        for mat in item["materials"]:
            for press in item["pressure_ratings"]:
                for sz in item["sizes"]:
                    code_counter += 1
                    code_a = f"MAT-{code_counter}"
                    desc_a = f"{mat} {item['type']} {sz} {press['value']} {press['unit']}"
                    norm_desc_a = desc_a.upper()
                    specs_a = {
                        "pressure_rating": press,
                        "dimensions": {"size": sz}
                    }
                    
                    rec_a = make_material_record("CPSE_A", code_a, desc_a, norm_desc_a, item["category"], mat, specs_a)
                    records.append(rec_a)
                    
                    # Positive Pair
                    code_counter += 1
                    code_b = f"M-{code_counter}"
                    syn = random.choice(item["synonyms"])
                    desc_b = f"{syn} {sz} {press['value']} LB {mat}"
                    norm_desc_b = desc_b.upper()
                    
                    rec_b = make_material_record("CPSE_B", code_b, desc_b, norm_desc_b, item["category"], mat, specs_a)
                    records.append(rec_b)
                    
                    pairs.append({
                        "left": rec_a,
                        "right": rec_b,
                        "label": 1,
                        "reason": "Exact valve match across CPSEs"
                    })
                    
                    # Hard Negative Pair (Conflicting Pressure Rating: 150 LB vs 300 LB)
                    alt_press = {"value": 300, "unit": "LB"} if press["value"] == 150 else {"value": 150, "unit": "LB"}
                    desc_hn = f"{syn} {sz} {alt_press['value']} LB {mat}"
                    norm_desc_hn = desc_hn.upper()
                    specs_hn = {
                        "pressure_rating": alt_press,
                        "dimensions": {"size": sz}
                    }
                    
                    rec_hn = make_material_record("CPSE_C", f"HN-{code_counter}", desc_hn, norm_desc_hn, item["category"], mat, specs_hn)
                    hard_negatives.append({
                        "left": rec_a,
                        "right": rec_hn,
                        "label": 0,
                        "conflict_field": "pressure_rating",
                        "reason": f"Conflicting pressure rating: {press['value']} vs {alt_press['value']}"
                    })

    # Save dataset files
    dev_path = DEV_DIR / "dataset_a_dev.json"
    with open(dev_path, "w", encoding="utf-8") as f:
        json.dump({"records": records, "pairs": pairs}, f, indent=2)

    hn_path = EVAL_DIR / "dataset_a_hard_negatives.json"
    with open(hn_path, "w", encoding="utf-8") as f:
        json.dump(hard_negatives, f, indent=2)

    # Save CSV sample
    csv_path = SAMPLE_DIR / "sample_materials.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["cpse", "material_code", "description", "category", "material_grade"])
        writer.writeheader()
        for r in records[:50]:
            writer.writerow({
                "cpse": r["cpse"],
                "material_code": r["material_code"],
                "description": r["description"],
                "category": r["category"],
                "material_grade": r["material_grade"]
            })

    print(f"Generated {len(records)} records, {len(pairs)} positive pairs, and {len(hard_negatives)} hard negatives.")
    print(f"Saved to: {dev_path}, {hn_path}, and {csv_path}")


if __name__ == "__main__":
    generate_dataset_a()
