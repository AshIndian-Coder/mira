"""
Profiling and Performance Benchmark for MIRA Production Matching Path.

Profiles the exact production path used by POST /api/matching/run-batch:
- Material loading & indexing
- Blocker object creation & inverted index construction
- Candidate pair generation (blocking)
- Embedding cache precomputation (cold vs warm, single vs batch)
- Candidate pair scoring (text similarity, semantic dot product, spec similarity, grade similarity)
- Critical gates evaluation
- Decision classification
- Database persistence (PersistentList / Postgres)

Tests across 50, 100, and 206 real cross-CPSE material records.
"""

import cProfile
import csv
import io
import os
import pstats
import time
from typing import Any

from app import store
from app.services.blocking.service import (
    MaterialForBlocking,
    generate_block_keys,
    generate_candidates as blocking_generate_candidates,
)
from app.services.matching.classifier import classify_match
from app.services.matching.critical_gates import evaluate_critical_gates
from app.services.matching.embeddings import (
    EmbeddingCache,
    get_embedding_model,
    precompute_embeddings,
)
from app.services.matching.scoring import calculate_match_score
from app.services.matching.similarity import (
    semantic_similarity,
    specification_similarity,
    text_similarity,
    value_similarity,
)
from app.services.normalization.service import normalize_material_description
from app.services.parsing.service import parse_specifications


def load_cross_cpse_real_materials(limit: int) -> list[dict[str, Any]]:
    """
    Load real material records round-robin across multiple CPSEs
    from Original_company_records_no_synthetic.csv to ensure cross-CPSE candidate generation.
    """
    csv_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Original_company_records_no_synthetic.csv",
    )
    records_by_org: dict[str, list[dict[str, Any]]] = {}
    with open(csv_path, "r", encoding="utf-8-sig", errors="ignore") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            raw_desc = (row.get("clean_description") or row.get("description") or "").strip()
            if not raw_desc:
                continue
            cpse = row.get("organization") or "CPSE_GENERIC"
            code = row.get("material_code") or f"MAT-{idx+1:06d}"
            cat = row.get("product_category") or "General"
            norm_desc = normalize_material_description(raw_desc)
            parsed = parse_specifications(raw_desc)
            rec = {
                "id": idx + 1,
                "cpse": cpse,
                "material_code": code,
                "description": raw_desc,
                "normalized_description": norm_desc,
                "category": cat,
                "unit": row.get("unit"),
                "manufacturer": row.get("manufacturer"),
                "manufacturer_part_number": row.get("manufacturer_part_number"),
                "material_grade": row.get("material_grade") or parsed.get("material_grade"),
                "parsed_specifications": {k: v for k, v in parsed.items() if v is not None},
                "other_attributes": {},
            }
            records_by_org.setdefault(cpse, []).append(rec)

    # Interleave records from top organizations
    interleaved: list[dict[str, Any]] = []
    org_keys = list(records_by_org.keys())
    max_len = max(len(v) for v in records_by_org.values())

    for i in range(max_len):
        for org in org_keys:
            if i < len(records_by_org[org]):
                rec = dict(records_by_org[org][i])
                rec["id"] = len(interleaved) + 1
                interleaved.append(rec)
                if len(interleaved) >= limit:
                    return interleaved
    return interleaved


def profile_stage_breakdown(materials: list[dict[str, Any]], max_candidates_per_material: int = 50):
    """
    Instrument each distinct stage of matching on the given material list.
    """
    total_t0 = time.perf_counter()

    # --- Stage A & B: Material loading & Preprocessing ---
    t0 = time.perf_counter()
    material_index = {m["id"]: m for m in materials}
    t_load = time.perf_counter() - t0

    # --- Stage C: Blocker Creation & Indexing ---
    t0 = time.perf_counter()
    blocker_objects = [
        MaterialForBlocking(
            id=m["id"],
            category=m.get("category"),
            normalized_description=m.get("normalized_description") or m.get("description", ""),
            material_grade=m.get("material_grade"),
            manufacturer_part_number=m.get("manufacturer_part_number"),
        )
        for m in materials
    ]
    block_index: dict[str, list[int]] = {}
    material_block_keys: dict[int, set[str]] = {}
    blocker_by_id: dict[int, MaterialForBlocking] = {}
    target_order: dict[int, int] = {}

    for idx, bo in enumerate(blocker_objects):
        blocker_by_id[bo.id] = bo
        target_order[bo.id] = idx
        keys = generate_block_keys(bo)
        material_block_keys[bo.id] = keys
        for key in keys:
            block_index.setdefault(key, []).append(bo.id)
    t_block_indexing = time.perf_counter() - t0

    # --- Candidate Generation (Blocking) ---
    t0 = time.perf_counter()
    seen_pairs: set[tuple[int, int]] = set()
    candidate_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []

    for source_bo in blocker_objects:
        source_keys = material_block_keys[source_bo.id]
        raw_candidates = blocking_generate_candidates(
            source_bo,
            block_index=block_index,
            target_map=blocker_by_id,
            target_order=target_order,
            source_keys=source_keys,
        )
        raw_candidates = raw_candidates[:max_candidates_per_material]

        for target_bo in raw_candidates:
            source_mat = material_index[source_bo.id]
            target_mat = material_index[target_bo.id]

            if source_mat["cpse"].upper() == target_mat["cpse"].upper():
                continue

            pk = (min(source_bo.id, target_bo.id), max(source_bo.id, target_bo.id))
            if pk in seen_pairs:
                continue
            seen_pairs.add(pk)
            candidate_pairs.append((source_mat, target_mat))
    t_candidate_gen = time.perf_counter() - t0

    # --- Stage D: Embedding Precomputation (Cold & Warm) ---
    unique_descriptions = list({
        m.get("normalized_description") or m.get("description", "")
        for m in materials
        if m.get("normalized_description") or m.get("description")
    })

    # Test Cold Embedding (Precomputed Batch)
    cold_cache = EmbeddingCache()
    t0 = time.perf_counter()
    cold_cache.precompute(unique_descriptions, batch_size=64)
    t_embed_cold = time.perf_counter() - t0

    # Test Warm Embedding (already cached)
    t0 = time.perf_counter()
    warm_cache = EmbeddingCache(cold_cache._cache)
    warm_cache.precompute(unique_descriptions, batch_size=64)
    t_embed_warm = time.perf_counter() - t0

    # Test Per-description single call (simulate non-precomputed / lazy)
    model = get_embedding_model()
    t0 = time.perf_counter()
    sample_texts = unique_descriptions[: min(10, len(unique_descriptions))]
    for text in sample_texts:
        _ = model.encode(text, normalize_embeddings=True)
    t_single_10 = time.perf_counter() - t0
    avg_single_encode_ms = (t_single_10 / len(sample_texts)) * 1000 if sample_texts else 0

    # --- Stage E-I: Candidate Pair Scoring Sub-Breakdown ---
    t_text_sim_total = 0.0
    t_semantic_sim_total = 0.0
    t_spec_sim_total = 0.0
    t_grade_sim_total = 0.0
    t_scoring_total = 0.0
    t_gates_total = 0.0
    t_classify_total = 0.0

    scored_results = []
    t_eval_start = time.perf_counter()
    for s_mat, t_mat in candidate_pairs:
        # Micro-measure scoring components
        ts0 = time.perf_counter()
        
        # 1. Text similarity (SequenceMatcher)
        ts_text0 = time.perf_counter()
        _ = text_similarity(s_mat.get("normalized_description", ""), t_mat.get("normalized_description", ""))
        t_text_sim_total += (time.perf_counter() - ts_text0)

        # 2. Semantic similarity (dot product on cached vector)
        ts_sem0 = time.perf_counter()
        _ = cold_cache.similarity(s_mat.get("normalized_description", ""), t_mat.get("normalized_description", ""))
        t_semantic_sim_total += (time.perf_counter() - ts_sem0)

        # 3. Spec similarity
        ts_spec0 = time.perf_counter()
        _ = specification_similarity(s_mat.get("parsed_specifications"), t_mat.get("parsed_specifications"), s_mat.get("category"))
        t_spec_sim_total += (time.perf_counter() - ts_spec0)

        # 4. Grade similarity
        ts_grade0 = time.perf_counter()
        _ = value_similarity(s_mat.get("material_grade"), t_mat.get("material_grade"))
        t_grade_sim_total += (time.perf_counter() - ts_grade0)

        t_scoring_total += (time.perf_counter() - ts0)

        # 5. Critical gates
        tg0 = time.perf_counter()
        checks = evaluate_critical_gates(s_mat, t_mat)
        t_gates_total += (time.perf_counter() - tg0)

        # 6. Full classify_match
        tc0 = time.perf_counter()
        res = classify_match(s_mat, t_mat, embedding_cache=cold_cache)
        t_classify_total += (time.perf_counter() - tc0)
        scored_results.append(res)

    t_eval_total = time.perf_counter() - t_eval_start

    # --- Stage J: Database Persistence Simulation ---
    store.reset_stores()
    t0 = time.perf_counter()
    store.MATERIALS.extend(materials)
    t_db_materials = time.perf_counter() - t0

    candidate_records = []
    for idx, (res, (s_mat, t_mat)) in enumerate(zip(scored_results, candidate_pairs)):
        candidate_records.append({
            "id": idx + 1,
            "source_material_id": s_mat["id"],
            "target_material_id": t_mat["id"],
            "source_cpse": s_mat["cpse"],
            "target_cpse": t_mat["cpse"],
            "source_code": s_mat["material_code"],
            "target_code": t_mat["material_code"],
            "source_description": s_mat["description"],
            "target_description": t_mat["description"],
            "scores": res["scores"],
            "critical_checks": res["critical_checks"],
            "engine_decision": res["decision"],
            "review_status": "PENDING" if res["decision"] in {"HIGH_CONFIDENCE", "REVIEW"} else res["decision"],
            "reviewer_id": None,
            "reviewer_comments": None,
            "reviewed_at": None,
            "created_at": "2026-09-20T21:00:00Z",
        })

    t0 = time.perf_counter()
    store.CANDIDATES.extend(candidate_records)
    t_db_candidates = time.perf_counter() - t0

    total_wall_clock = time.perf_counter() - total_t0

    # Also simulate what un-cached / lazy encode per pair would take
    # (i.e. if model.encode was called per candidate pair without cache)
    estimated_uncached_pair_time_s = len(candidate_pairs) * (2 * avg_single_encode_ms / 1000.0)

    return {
        "materials_count": len(materials),
        "unique_descriptions": len(unique_descriptions),
        "candidate_pairs": len(candidate_pairs),
        "t_load_ms": t_load * 1000,
        "t_block_indexing_ms": t_block_indexing * 1000,
        "t_candidate_gen_ms": t_candidate_gen * 1000,
        "t_embed_cold_ms": t_embed_cold * 1000,
        "t_embed_warm_ms": t_embed_warm * 1000,
        "avg_single_encode_ms": avg_single_encode_ms,
        "t_scoring_total_ms": t_scoring_total * 1000,
        "t_text_sim_ms": t_text_sim_total * 1000,
        "t_semantic_sim_ms": t_semantic_sim_total * 1000,
        "t_spec_sim_ms": t_spec_sim_total * 1000,
        "t_grade_sim_ms": t_grade_sim_total * 1000,
        "t_gates_total_ms": t_gates_total * 1000,
        "t_classify_total_ms": t_classify_total * 1000,
        "t_eval_total_ms": t_eval_total * 1000,
        "t_db_materials_ms": t_db_materials * 1000,
        "t_db_candidates_ms": t_db_candidates * 1000,
        "t_db_total_ms": (t_db_materials + t_db_candidates) * 1000,
        "total_wall_clock_s": total_wall_clock,
        "estimated_uncached_pair_time_s": estimated_uncached_pair_time_s,
    }


def run_cprofile_on_batch(materials: list[dict[str, Any]]):
    """Run cProfile on the full matching path to capture top CPU consumers."""
    profiler = cProfile.Profile()
    unique_descriptions = list({
        m.get("normalized_description") or m.get("description", "")
        for m in materials
        if m.get("normalized_description") or m.get("description")
    })
    cache = precompute_embeddings(unique_descriptions, batch_size=64)
    
    material_index = {m["id"]: m for m in materials}
    blocker_objects = [
        MaterialForBlocking(
            id=m["id"],
            category=m.get("category"),
            normalized_description=m.get("normalized_description") or m.get("description", ""),
            material_grade=m.get("material_grade"),
            manufacturer_part_number=m.get("manufacturer_part_number"),
        )
        for m in materials
    ]
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
        raw_candidates = blocking_generate_candidates(
            source_bo,
            block_index=block_index,
            target_map=blocker_by_id,
            target_order=target_order,
            source_keys=source_keys,
        )[:50]
        for target_bo in raw_candidates:
            source_mat = material_index[source_bo.id]
            target_mat = material_index[target_bo.id]
            if source_mat["cpse"].upper() == target_mat["cpse"].upper():
                continue
            pk = (min(source_bo.id, target_bo.id), max(source_bo.id, target_bo.id))
            if pk in seen_pairs:
                continue
            seen_pairs.add(pk)
            candidate_pairs.append((source_mat, target_mat))

    profiler.enable()
    for s_mat, t_mat in candidate_pairs:
        classify_match(s_mat, t_mat, embedding_cache=cache)
    profiler.disable()

    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s).sort_stats("cumulative")
    ps.print_stats(30)
    return s.getvalue()


if __name__ == "__main__":
    print("=" * 70)
    print("MIRA PRODUCTION MATCHING PATH PERFORMANCE PROFILE")
    print("=" * 70)

    # Warm up model once so cold import overhead is separated
    get_embedding_model()

    sizes = [50, 100, 206]
    all_metrics = []

    for size in sizes:
        print(f"\n--- Loading {size} real cross-CPSE materials ---")
        mats = load_cross_cpse_real_materials(size)
        metrics = profile_stage_breakdown(mats)
        all_metrics.append(metrics)
        print(f"Materials: {metrics['materials_count']} | Unique Descs: {metrics['unique_descriptions']} | Candidate Pairs: {metrics['candidate_pairs']}")
        print(f"  - Blocking Indexing: {metrics['t_block_indexing_ms']:.2f} ms")
        print(f"  - Candidate Gen:     {metrics['t_candidate_gen_ms']:.2f} ms")
        print(f"  - Cold Embedding:    {metrics['t_embed_cold_ms']:.2f} ms ({metrics['t_embed_cold_ms']/metrics['unique_descriptions']:.2f} ms/desc in batch)")
        print(f"  - Warm Embedding:    {metrics['t_embed_warm_ms']:.2f} ms")
        print(f"  - Single Encode:     {metrics['avg_single_encode_ms']:.2f} ms/desc")
        print(f"  - Scoring Total:     {metrics['t_scoring_total_ms']:.2f} ms ({metrics['t_scoring_total_ms']/metrics['candidate_pairs']:.4f} ms/pair)" if metrics['candidate_pairs'] else f"  - Scoring Total:     {metrics['t_scoring_total_ms']:.2f} ms")
        print(f"      * Text Sim:      {metrics['t_text_sim_ms']:.2f} ms")
        print(f"      * Semantic Sim:  {metrics['t_semantic_sim_ms']:.2f} ms")
        print(f"      * Spec Sim:      {metrics['t_spec_sim_ms']:.2f} ms")
        print(f"      * Grade Sim:     {metrics['t_grade_sim_ms']:.2f} ms")
        print(f"  - Critical Gates:    {metrics['t_gates_total_ms']:.2f} ms")
        print(f"  - Full Classification: {metrics['t_classify_total_ms']:.2f} ms")
        print(f"  - DB Persistence:    {metrics['t_db_total_ms']:.2f} ms (mats: {metrics['t_db_materials_ms']:.2f} ms, cands: {metrics['t_db_candidates_ms']:.2f} ms)")
        print(f"  - Total Wall Clock:  {metrics['total_wall_clock_s']:.3f} s")
        if metrics['candidate_pairs'] > 0:
            print(f"  - [Hypothetical Uncached] Repeated Encode per Pair: {metrics['estimated_uncached_pair_time_s']:.2f} s")

    print("\n" + "=" * 70)
    print("cProfile Output for 206 Materials (Matching Loop):")
    print("=" * 70)
    mats_206 = load_cross_cpse_real_materials(206)
    cprofile_summary = run_cprofile_on_batch(mats_206)
    print(cprofile_summary)
