"""
Performance & Scalability Benchmark for MIRA Pipeline.
Measures actual execution times, throughput (records/sec), candidate counts,
and memory usage across the 9 stages for dataset sizes: 10, 100, 1000, 5000.
"""

import gc
import json
import random
import time
import tracemalloc
from typing import Any

from app import store
from app.services.normalization.service import normalize_material_description
from app.services.parsing.service import parse_specifications
from app.services.blocking.service import (
    MaterialForBlocking,
    generate_block_keys,
    generate_candidates as blocking_generate_candidates,
)
from app.services.matching.classifier import classify_match
from app.services.matching.embeddings import precompute_embeddings
from app.services.harmonization.service import build_common_material_record
from app.services.cnmc.service import generate_or_get_cnmc

SAMPLE_TEMPLATES = [
    ("GATE VALVE CS 150 LB {size} IN", "Valve", "CS", {"value": 150.0, "unit": "LB"}, {"value": 2.0, "unit": "IN"}),
    ("GLOBE VALVE SS316 300 LB {size} IN", "Valve", "SS316", {"value": 300.0, "unit": "LB"}, {"value": 3.0, "unit": "IN"}),
    ("BALL VALVE SS304 600 LB {size} IN", "Valve", "SS304", {"value": 600.0, "unit": "LB"}, {"value": 4.0, "unit": "IN"}),
    ("SEAMLESS PIPE ASTM A106 GR B {size} IN SCH 40", "Pipe", "A106-B", None, {"value": 2.0, "unit": "IN"}),
    ("ERW PIPE CS {size} IN SCH 80", "Pipe", "CS", None, {"value": 6.0, "unit": "IN"}),
    ("DEEP GROOVE BALL BEARING {size} MM SKF 6205", "Bearing", None, None, {"value": 25.0, "unit": "MM"}),
    ("SPHERICAL ROLLER BEARING {size} MM FAG 22210", "Bearing", None, None, {"value": 50.0, "unit": "MM"}),
    ("CENTRIFUGAL WATER PUMP {size} M3/HR 50M HEAD", "Pump", "CI", None, {"value": 50.0, "unit": "M3/HR"}),
    ("SPIRAL WOUND GASKET SS304 {size} IN 150 LB", "Gasket", "SS304", {"value": 150.0, "unit": "LB"}, {"value": 2.0, "unit": "IN"}),
    ("INDUCTION MOTOR 3 PHASE 415V {size} KW 1440 RPM", "Electrical", None, None, {"value": 15.0, "unit": "KW"}),
]

CPSES = ["IOCL", "ONGC", "NTPC", "BHEL", "SAIL", "GAIL", "BPCL", "HPCL"]

def generate_synthetic_materials(count: int) -> list[dict[str, Any]]:
    materials = []
    for i in range(1, count + 1):
        tmpl, cat, grade, pressure, dim = random.choice(SAMPLE_TEMPLATES)
        size_val = round(random.choice([0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 10.0, 12.0]), 1)
        desc = tmpl.format(size=size_val)
        cpse = random.choice(CPSES)
        materials.append({
            "id": i,
            "cpse": cpse,
            "material_code": f"{cpse}-MAT-{i:06d}",
            "description": desc,
            "category": cat,
            "source_file": f"{cpse}_master.csv",
            "source_page": 1,
        })
    return materials

def benchmark_dataset(size: int):
    print(f"\n=======================================================")
    print(f"BENCHMARK RUN: {size} RECORDS")
    print(f"=======================================================")
    
    raw_materials = generate_synthetic_materials(size)
    results = {}
    
    # 1. Ingestion Simulation (dict creation & CSV parsing equivalent)
    gc.collect()
    tracemalloc.start()
    t0 = time.perf_counter()
    ingested_data = []
    for row in raw_materials:
        ingested_data.append({
            "id": row["id"],
            "cpse": row["cpse"],
            "material_code": row["material_code"],
            "description": row["description"],
            "category": row["category"],
        })
    t_ingest = time.perf_counter() - t0
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    results["1_ingestion"] = {
        "time_sec": t_ingest,
        "rate_rec_sec": size / t_ingest if t_ingest > 0 else float("inf"),
        "peak_mem_kb": peak_mem / 1024,
    }
    print(f"1. Ingestion: {t_ingest*1000:.2f} ms | {results['1_ingestion']['rate_rec_sec']:.0f} rec/sec | Peak Mem: {peak_mem/1024:.1f} KB")

    # 2. Normalization
    gc.collect()
    tracemalloc.start()
    t0 = time.perf_counter()
    normalized_list = []
    for row in ingested_data:
        norm = normalize_material_description(row["description"])
        normalized_list.append(norm)
    t_norm = time.perf_counter() - t0
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    results["2_normalization"] = {
        "time_sec": t_norm,
        "rate_rec_sec": size / t_norm if t_norm > 0 else float("inf"),
        "peak_mem_kb": peak_mem / 1024,
    }
    print(f"2. Normalization: {t_norm*1000:.2f} ms | {results['2_normalization']['rate_rec_sec']:.0f} rec/sec | Peak Mem: {peak_mem/1024:.1f} KB")

    # 3. Parsing & Enrichment
    gc.collect()
    tracemalloc.start()
    t0 = time.perf_counter()
    enriched_materials = []
    for i, row in enumerate(ingested_data):
        norm = normalized_list[i]
        parsed = parse_specifications(row["description"])
        enriched_materials.append({
            **row,
            "normalized_description": norm,
            "parsed_specifications": {k: v for k, v in parsed.items() if v is not None},
            "material_grade": parsed.get("material_grade"),
            "dimensions": parsed.get("dimensions"),
        })
    t_parse = time.perf_counter() - t0
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    results["3_parsing_enrichment"] = {
        "time_sec": t_parse,
        "rate_rec_sec": size / t_parse if t_parse > 0 else float("inf"),
        "peak_mem_kb": peak_mem / 1024,
    }
    print(f"3. Parsing/Enrichment: {t_parse*1000:.2f} ms | {results['3_parsing_enrichment']['rate_rec_sec']:.0f} rec/sec | Peak Mem: {peak_mem/1024:.1f} KB")

    # 4. Candidate Generation (Blocking)
    gc.collect()
    tracemalloc.start()
    t0 = time.perf_counter()
    blocker_objects = [
        MaterialForBlocking(
            id=m["id"],
            category=m.get("category"),
            normalized_description=m.get("normalized_description") or m["description"],
            material_grade=m.get("material_grade"),
            manufacturer_part_number=m.get("manufacturer_part_number"),
        )
        for m in enriched_materials
    ]
    material_index = {m["id"]: m for m in enriched_materials}
    
    # Build inverted block index and precompute keys
    block_index = {}
    material_block_keys = {}
    blocker_by_id = {}
    target_order = {}
    for idx, bo in enumerate(blocker_objects):
        blocker_by_id[bo.id] = bo
        target_order[bo.id] = idx
        keys = generate_block_keys(bo)
        material_block_keys[bo.id] = keys
        for key in keys:
            block_index.setdefault(key, []).append(bo.id)

    seen_pairs = set()
    candidate_pairs = []
    for source_bo in blocker_objects:
        source_keys = material_block_keys[source_bo.id]
        raw_cands = blocking_generate_candidates(
            source_bo,
            block_index=block_index,
            target_map=blocker_by_id,
            target_order=target_order,
            source_keys=source_keys,
        )
        raw_cands = raw_cands[:50]  # default max_candidates_per_material
        for target_bo in raw_cands:
            source_mat = material_index[source_bo.id]
            target_mat = material_index[target_bo.id]
            if source_mat["cpse"].upper() == target_mat["cpse"].upper():
                continue
            pk = (min(source_bo.id, target_bo.id), max(source_bo.id, target_bo.id))
            if pk in seen_pairs:
                continue
            seen_pairs.add(pk)
            candidate_pairs.append((source_mat, target_mat))

    t_cand = time.perf_counter() - t0
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    candidate_count = len(candidate_pairs)
    results["4_candidate_generation"] = {
        "time_sec": t_cand,
        "candidate_count": candidate_count,
        "rate_rec_sec": size / t_cand if t_cand > 0 else float("inf"),
        "peak_mem_kb": peak_mem / 1024,
    }
    print(f"4. Candidate Generation: {t_cand*1000:.2f} ms | {candidate_count} candidate pairs | Peak Mem: {peak_mem/1024:.1f} KB")

    # 5. Matching & Scoring (evaluate candidate pairs, cap at realistic subset if huge)
    eval_pairs = candidate_pairs[: min(len(candidate_pairs), 2000)]
    gc.collect()
    tracemalloc.start()
    t0 = time.perf_counter()
    unique_descriptions = {
        m.get("normalized_description") or m.get("description", "")
        for m in enriched_materials
    }
    embedding_cache = precompute_embeddings(unique_descriptions)
    scored_candidates = []
    for pair in eval_pairs:
        res = classify_match(pair[0], pair[1], embedding_cache=embedding_cache)
        scored_candidates.append(res)
    t_score = time.perf_counter() - t0
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    pairs_evaluated = len(eval_pairs)
    results["5_matching_scoring"] = {
        "time_sec": t_score,
        "pairs_evaluated": pairs_evaluated,
        "rate_pairs_sec": pairs_evaluated / t_score if t_score > 0 else float("inf"),
        "peak_mem_kb": peak_mem / 1024,
    }
    print(f"5. Matching & Scoring: {t_score*1000:.2f} ms | {pairs_evaluated} pairs evaluated ({results['5_matching_scoring']['rate_pairs_sec']:.0f} pairs/sec) | Peak Mem: {peak_mem/1024:.1f} KB")

    # 6. Database Persistence (inserting materials & candidates to Postgres adapter)
    # Test batch DB insertion speed
    store.reset_stores()
    gc.collect()
    tracemalloc.start()
    t0 = time.perf_counter()
    store.MATERIALS.extend(enriched_materials[: min(size, 1000)])
    t_db = time.perf_counter() - t0
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    db_items = min(size, 1000)
    results["6_database_persistence"] = {
        "time_sec": t_db,
        "records_persisted": db_items,
        "rate_rec_sec": db_items / t_db if t_db > 0 else float("inf"),
        "peak_mem_kb": peak_mem / 1024,
    }
    print(f"6. DB Persistence ({db_items} recs): {t_db*1000:.2f} ms | {results['6_database_persistence']['rate_rec_sec']:.0f} rec/sec | Peak Mem: {peak_mem/1024:.1f} KB")

    # 7. Review Queue Retrieval & Filtering
    gc.collect()
    tracemalloc.start()
    t0 = time.perf_counter()
    # Simulate retrieving and filtering pending review candidates
    pending_queue = [
        c for c in scored_candidates
        if c.get("engine_decision") in ("REVIEW", "HIGH_CONFIDENCE")
    ][:100]
    t_queue = time.perf_counter() - t0
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    results["7_review_queue_retrieval"] = {
        "time_sec": t_queue,
        "items_retrieved": len(pending_queue),
        "peak_mem_kb": peak_mem / 1024,
    }
    print(f"7. Review Queue Retrieval: {t_queue*1000:.4f} ms | {len(pending_queue)} items | Peak Mem: {peak_mem/1024:.1f} KB")

    # 8. Mapping Generation & CMR Synthesis
    approved_clusters = []
    # Form clusters of 2 from evaluated pairs
    for i in range(0, min(len(eval_pairs), 100), 2):
        approved_clusters.append([eval_pairs[i][0], eval_pairs[i][1]])
    
    gc.collect()
    tracemalloc.start()
    t0 = time.perf_counter()
    cmrs = []
    for cluster in approved_clusters:
        cmr = build_common_material_record(cluster)
        cmrs.append(cmr)
    t_cmr = time.perf_counter() - t0
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    results["8_cmr_generation"] = {
        "time_sec": t_cmr,
        "cmrs_built": len(cmrs),
        "rate_cmr_sec": len(cmrs) / t_cmr if t_cmr > 0 else float("inf"),
        "peak_mem_kb": peak_mem / 1024,
    }
    print(f"8. CMR Generation ({len(cmrs)} clusters): {t_cmr*1000:.2f} ms | {results['8_cmr_generation']['rate_cmr_sec']:.0f} CMR/sec | Peak Mem: {peak_mem/1024:.1f} KB")

    # 9. CNMC Generation
    gc.collect()
    tracemalloc.start()
    t0 = time.perf_counter()
    cnmcs = []
    for i, cluster in enumerate(approved_clusters):
        cmr = cmrs[i]
        cnmc_info = generate_or_get_cnmc(cluster, cmr)
        cnmcs.append(cnmc_info)
    t_cnmc = time.perf_counter() - t0
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    results["9_cnmc_generation"] = {
        "time_sec": t_cnmc,
        "cnmcs_generated": len(cnmcs),
        "rate_cnmc_sec": len(cnmcs) / t_cnmc if t_cnmc > 0 else float("inf"),
        "peak_mem_kb": peak_mem / 1024,
    }
    print(f"9. CNMC Generation ({len(cnmcs)} codes): {t_cnmc*1000:.2f} ms | {results['9_cnmc_generation']['rate_cnmc_sec']:.0f} CNMC/sec | Peak Mem: {peak_mem/1024:.1f} KB")

    store.reset_stores()
    return results

if __name__ == "__main__":
    random.seed(42)
    sizes = [10, 100, 1000, 5000]
    all_results = {}
    for s in sizes:
        all_results[s] = benchmark_dataset(s)
    
    with open("benchmark_results.json", "w") as f:
        json.dump(all_results, f, indent=2)
    print("\nBenchmark completed. Results written to benchmark_results.json")
