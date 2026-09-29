import pytest
import numpy as np

from app.services.matching.embeddings import (
    EmbeddingCache,
    get_embedding_model,
    precompute_embeddings,
    semantic_similarity as embeddings_semantic_similarity,
)
from app.services.matching.similarity import semantic_similarity
from app.services.matching.scoring import calculate_match_score
from app.services.matching.classifier import classify_match


def test_unique_descriptions_precomputation():
    texts = [
        "SS 304 GATE VALVE 2 IN 150 LB",
        "GLOBE VALVE SS316 3 IN 300 LB",
        "BALL VALVE SS304 4 IN 600 LB",
    ]
    cache = precompute_embeddings(texts)
    assert len(cache) == 3
    for t in texts:
        assert t in cache
        vec = cache.get(t)
        assert isinstance(vec, np.ndarray)
        assert vec.shape == (1024,)
        # Check normalized unit vector
        assert abs(np.linalg.norm(vec) - 1.0) < 1e-2


def test_duplicate_descriptions_encoded_only_once():
    texts = [
        "GATE VALVE CS 150 LB 2 IN",
        "GATE VALVE CS 150 LB 2 IN",
        "GATE VALVE CS 150 LB 2 IN",
        "SEAMLESS PIPE ASTM A106 2 IN",
        "SEAMLESS PIPE ASTM A106 2 IN",
    ]
    cache = precompute_embeddings(texts)
    # Only 2 unique descriptions
    assert len(cache) == 2
    assert "GATE VALVE CS 150 LB 2 IN" in cache
    assert "SEAMLESS PIPE ASTM A106 2 IN" in cache


def test_empty_and_none_descriptions():
    cache = EmbeddingCache()
    assert cache.similarity("", "VALVE") == 0.0
    assert cache.similarity("VALVE", "") == 0.0
    assert cache.similarity("", "") == 0.0
    assert embeddings_semantic_similarity("", "VALVE", embedding_cache=cache) == 0.0
    assert embeddings_semantic_similarity("VALVE", "", embedding_cache=cache) == 0.0
    assert embeddings_semantic_similarity("", "", embedding_cache=cache) == 0.0
    assert len(cache) == 0


def test_numerical_parity_between_cached_and_uncached():
    pairs = [
        ("SS 304 GATE VALVE 2 IN 150 LB", "SS304 GATE VALVE 50 MM 150 LB"),
        ("DEEP GROOVE BALL BEARING SKF 6205", "SPHERICAL ROLLER BEARING FAG 22210"),
        ("CENTRIFUGAL WATER PUMP 50 M3/HR", "INDUCTION MOTOR 3 PHASE 15 KW"),
        ("GATE VALVE CS 150 LB 2 IN", "GATE VALVE CS 150 LB 2 IN"),
    ]

    all_texts = [t for pair in pairs for t in pair]
    cache = precompute_embeddings(all_texts)

    for left, right in pairs:
        uncached_sim = embeddings_semantic_similarity(left, right)
        cached_sim = embeddings_semantic_similarity(left, right, embedding_cache=cache)
        wrapper_sim = semantic_similarity(left, right, embedding_cache=cache)

        assert abs(uncached_sim - cached_sim) < 0.10, f"Mismatch: uncached={uncached_sim}, cached={cached_sim}"
        assert abs(cached_sim - wrapper_sim) < 1e-6


def test_multiple_candidate_pairs_sharing_same_material():
    source_desc = "SS 304 GATE VALVE 2 IN 150 LB"
    targets = [
        "SS 304 GATE VALVE 2 IN 150 LB",
        "SS 304 GATE VALVE 2 IN 300 LB",
        "SS 316 GATE VALVE 2 IN 150 LB",
        "BALL BEARING 50 MM",
    ]

    cache = precompute_embeddings([source_desc] + targets)
    source_vec = cache.get(source_desc)
    assert source_vec is not None

    for target_desc in targets:
        sim = cache.similarity(source_desc, target_desc)
        assert 0.0 <= sim <= 1.0
        # Verify vector was not recomputed
        assert cache.get(source_desc) is source_vec


def test_cache_reuse_and_on_demand_encoding():
    cache = EmbeddingCache()
    assert len(cache) == 0

    t1 = "GATE VALVE 2 IN"
    t2 = "GLOBE VALVE 2 IN"

    sim1 = cache.similarity(t1, t2)
    assert len(cache) == 2
    assert t1 in cache
    assert t2 in cache

    vec1_first = cache.get(t1)
    # Second access should return exact same object
    vec1_second = cache.get_or_encode(t1)
    assert vec1_first is vec1_second


def test_no_cross_request_leakage():
    cache_req1 = precompute_embeddings(["REQUEST 1 DESCRIPTION"])
    cache_req2 = precompute_embeddings(["REQUEST 2 DESCRIPTION"])

    assert "REQUEST 1 DESCRIPTION" in cache_req1
    assert "REQUEST 1 DESCRIPTION" not in cache_req2
    assert "REQUEST 2 DESCRIPTION" in cache_req2
    assert "REQUEST 2 DESCRIPTION" not in cache_req1

    cache_req1.clear()
    assert len(cache_req1) == 0
    assert len(cache_req2) == 1


def test_classify_match_and_scoring_with_embedding_cache():
    mat_a = {
        "id": 1,
        "category": "Valve",
        "normalized_description": "SS 304 GATE VALVE 2 IN 150 LB",
        "material_grade": "SS304",
        "parsed_specifications": {
            "pressure_rating": {"value": 150, "unit": "LB"},
            "dimensions": {"value": 2, "unit": "IN"},
        },
        "other_attributes": {},
    }
    mat_b = {
        "id": 2,
        "category": "Valve",
        "normalized_description": "SS 304 GATE VALVE 50 MM 150 LB",
        "material_grade": "SS304",
        "parsed_specifications": {
            "pressure_rating": {"value": 150, "unit": "LB"},
            "dimensions": {"value": 50.8, "unit": "MM"},
        },
        "other_attributes": {},
    }

    cache = precompute_embeddings([
        mat_a["normalized_description"],
        mat_b["normalized_description"],
    ])

    scores_uncached = calculate_match_score(mat_a, mat_b)
    scores_cached = calculate_match_score(mat_a, mat_b, embedding_cache=cache)

    assert scores_uncached == scores_cached

    decision_uncached = classify_match(mat_a, mat_b)
    decision_cached = classify_match(mat_a, mat_b, embedding_cache=cache)

    assert decision_uncached["decision"] == decision_cached["decision"]
    assert decision_uncached["scores"] == decision_cached["scores"]


def test_semantic_equivalence_across_similarity_spectrum_and_negative_cosine():
    """
    Verify pre-optimization vs new cached behavior across all similarity levels:
    1. Identical text
    2. Highly similar text
    3. Moderately similar text
    4. Unrelated text
    5. Synthetic / extreme negative cosine vectors (verifying clamping to [0.0, 1.0])
    """
    test_cases = [
        # 1. Identical
        ("SS 304 GATE VALVE 2 IN 150 LB", "SS 304 GATE VALVE 2 IN 150 LB"),
        # 2. Highly similar
        ("SS 304 GATE VALVE 2 IN 150 LB", "SS304 GATE VALVE 50 MM 150 LB"),
        # 3. Moderately similar
        ("SS 304 GATE VALVE 2 IN 150 LB", "GLOBE VALVE CARBON STEEL 4 IN 300 LB"),
        # 4. Unrelated
        ("SS 304 GATE VALVE 2 IN 150 LB", "COTTON SHIRT BLUE MEDIUM"),
        # Opposing concepts
        ("extremely hot boiling fire inferno summer", "freezing absolute zero ice glacier winter cold blizzard"),
    ]

    model = get_embedding_model()

    for t1, t2 in test_cases:
        # Pre-optimization reference implementation
        raw_embs = model.encode([t1, t2], normalize_embeddings=True)
        raw_cos = float(raw_embs[0] @ raw_embs[1])
        old_expected = max(0.0, min(1.0, raw_cos))

        # New cached implementation
        cache = precompute_embeddings([t1, t2])
        cached_result = embeddings_semantic_similarity(t1, t2, embedding_cache=cache)

        assert abs(old_expected - cached_result) < 0.10, (
            f"Equivalence failure for ('{t1}', '{t2}'): old={old_expected} vs new={cached_result}"
        )

    # 5. Verify negative cosine behavior on synthetic unit vectors
    # Construct synthetic unit vectors with known negative dot product (-1.0 and -0.4)
    neg_vec_a = np.zeros(1024, dtype=np.float32)
    neg_vec_b = np.zeros(1024, dtype=np.float32)
    neg_vec_a[0] = 1.0
    neg_vec_b[0] = -1.0  # dot product = -1.0

    synthetic_cache = EmbeddingCache({
        "SYNTH_POS": neg_vec_a,
        "SYNTH_NEG": neg_vec_b,
    })

    # Both old and new evaluate max(0.0, min(1.0, -1.0)) = 0.0
    raw_dot = float(neg_vec_a @ neg_vec_b)
    assert raw_dot == -1.0

    old_neg_expected = max(0.0, min(1.0, raw_dot))
    assert old_neg_expected == 0.0

    cached_neg_result = synthetic_cache.similarity("SYNTH_POS", "SYNTH_NEG")
    assert cached_neg_result == 0.0
    assert cached_neg_result == old_neg_expected


def test_qwen_embedding_shape_and_normalization():
    """Verify Qwen INT8 model produces 1024-dimensional normalized embeddings and MiniLM remains 384D."""
    qwen_model = get_embedding_model("qwen")
    minilm_model = get_embedding_model("minilm")

    text = "SS 304 GATE VALVE 2 IN 150 LB"

    qwen_emb = qwen_model.encode(text, normalize_embeddings=True)
    minilm_emb = minilm_model.encode(text, normalize_embeddings=True)

    assert qwen_emb.shape == (1024,)
    assert minilm_emb.shape == (384,)

    qwen_norm = float(np.linalg.norm(qwen_emb))
    minilm_norm = float(np.linalg.norm(minilm_emb))

    assert abs(qwen_norm - 1.0) < 1e-2
    assert abs(minilm_norm - 1.0) < 1e-4


def test_cross_model_cache_isolation_and_no_contamination():
    """
    Verify EmbeddingCache model isolation:
    1. Same text + same model -> cache hit
    2. Same text + MiniLM then Qwen -> NOT same cache entry (different shapes, different keys)
    3. Same text + Qwen repeated -> cache hit
    4. Different text + Qwen -> cache miss
    5. No cross-model cache contamination
    """
    cache = EmbeddingCache(model_name="minilm")
    text1 = "GLOBE VALVE CS 150 LB 2 IN"
    text2 = "BALL VALVE SS316 3 IN 300 LB"

    # 1. Encode text1 with MiniLM
    minilm_vec = cache.get_or_encode(text1, model_name="minilm")
    assert minilm_vec.shape == (384,)

    # 2. Encode same text1 with Qwen on the same cache instance
    qwen_vec = cache.get_or_encode(text1, model_name="qwen")
    assert qwen_vec.shape == (1024,)
    assert qwen_vec is not minilm_vec

    # Verify querying MiniLM still returns the MiniLM vector (no contamination)
    minilm_vec_again = cache.get(text1, model_name="minilm")
    assert minilm_vec_again is minilm_vec
    assert minilm_vec_again.shape == (384,)

    # 3. Repeated Qwen query for text1 returns cached Qwen vector
    qwen_vec_again = cache.get(text1, model_name="qwen")
    assert qwen_vec_again is qwen_vec
    assert qwen_vec_again.shape == (1024,)

    # 4. Different text for Qwen -> not yet in cache
    assert cache.get(text2, model_name="qwen") is None
    qwen_vec2 = cache.get_or_encode(text2, model_name="qwen")
    assert qwen_vec2.shape == (1024,)
    assert cache.get(text2, model_name="qwen") is qwen_vec2


def test_qwen_semantic_similarity_range_contract():
    """Verify semantic similarity with Qwen model always adheres to [0.0, 1.0] range."""
    pairs = [
        ("SS 304 GATE VALVE 2 IN 150 LB", "SS 304 GATE VALVE 2 IN 150 LB"),
        ("SS 304 GATE VALVE 2 IN 150 LB", "SS304 GATE VALVE 50 MM 150 LB"),
        ("HEX BOLT M12X50", "HEX HEAD BOLT M12 X 50 MM"),
        ("BALL VALVE 2 IN 150 LB", "BALL VALVE 4 IN 150 LB"),
        ("COTTON SHIRT BLUE MEDIUM", "GATE VALVE CS 150 LB 2 IN"),
        ("extremely hot boiling fire inferno", "freezing absolute zero ice blizzard"),
    ]

    cache = precompute_embeddings([t for p in pairs for t in p], model_name="qwen")

    for t1, t2 in pairs:
        sim_uncached = embeddings_semantic_similarity(t1, t2, model_name="qwen")
        sim_cached = embeddings_semantic_similarity(t1, t2, embedding_cache=cache, model_name="qwen")

        assert 0.0 <= sim_uncached <= 1.0
        assert 0.0 <= sim_cached <= 1.0
        # Check both cached and uncached are in close agreement (INT8 quantization tolerance)
        assert abs(sim_uncached - sim_cached) < 0.05



def test_production_paths_with_qwen():
    """Verify Qwen works seamlessly across scoring, classification, and CNMC matching."""
    mat_a = {
        "id": 101,
        "cpse": "CPSE1",
        "material_code": "MAT-001",
        "category": "Valve",
        "normalized_description": "SS 304 GATE VALVE 2 IN 150 LB",
        "material_grade": "SS304",
        "parsed_specifications": {
            "pressure_rating": {"value": 150, "unit": "LB"},
            "dimensions": {"value": 2, "unit": "IN"},
        },
        "other_attributes": {},
    }
    mat_b = {
        "id": 102,
        "cpse": "CPSE2",
        "material_code": "MAT-002",
        "category": "Valve",
        "normalized_description": "SS 304 GATE VALVE 50 MM 150 LB",
        "material_grade": "SS304",
        "parsed_specifications": {
            "pressure_rating": {"value": 150, "unit": "LB"},
            "dimensions": {"value": 50.8, "unit": "MM"},
        },
        "other_attributes": {},
    }

    cache = precompute_embeddings(
        [mat_a["normalized_description"], mat_b["normalized_description"]],
        model_name="qwen",
    )

    score_result = calculate_match_score(mat_a, mat_b, embedding_cache=cache)
    assert "semantic_similarity" in score_result
    assert 0.0 <= score_result["semantic_similarity"] <= 1.0
    assert 0.0 <= score_result["final_score"] <= 1.0

    class_result = classify_match(mat_a, mat_b, embedding_cache=cache)
    assert class_result["decision"] in {"HIGH_CONFIDENCE", "REVIEW", "DIFFERENT"}
    assert class_result["scores"]["semantic_similarity"] == score_result["semantic_similarity"]
