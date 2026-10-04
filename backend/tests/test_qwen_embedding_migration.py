import os
from pathlib import Path
import numpy as np
import pytest

from app.services.matching.embeddings import (
    EmbeddingCache,
    find_qwen_model_path,
    get_embedding_dimension,
    get_embedding_model,
    get_embedding_model_name,
    generate_embedding,
    precompute_embeddings,
    resolve_model_name,
    semantic_similarity as embeddings_semantic_similarity,
)
from app.services.matching.similarity import semantic_similarity
from app.services.matching.scoring import calculate_match_score
from app.services.matching.classifier import classify_match
from app.services.matching.cnmc_matcher import find_cnmc_candidates_for_material


def _get_milvus_configured_dim() -> int:
    milvus_file = Path(__file__).resolve().parents[1] / "create_milvus_collection.py"
    for line in milvus_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("EMBEDDING_DIM"):
            return int(line.split("=")[1].strip())
    raise ValueError("EMBEDDING_DIM not found in create_milvus_collection.py")


def test_qwen_model_resolution_and_default():
    """Verify that the Qwen INT8 model is resolved as default when available."""
    qwen_path = find_qwen_model_path()
    assert qwen_path is not None
    assert qwen_path.exists()
    assert (qwen_path / "config.json").exists()

    # Unset alias -> resolves to local Qwen model
    resolved_default = resolve_model_name()
    assert resolved_default == str(qwen_path)

    # Explicit 'qwen' alias -> resolves to local Qwen model
    resolved_qwen = resolve_model_name("qwen")
    assert resolved_qwen == str(qwen_path)

    # Explicit 'production' alias -> resolves to local Qwen model
    resolved_prod = resolve_model_name("production")
    assert resolved_prod == str(qwen_path)

    # Explicit 'mira' / 'mira.ai' / 'default' aliases -> resolves to local Qwen model
    assert resolve_model_name("default") == str(qwen_path)
    assert resolve_model_name("mira") == str(qwen_path)
    assert resolve_model_name("mira.ai") == str(qwen_path)

    # get_embedding_model_name() uses resolve_model_name()
    assert get_embedding_model_name() == str(qwen_path)


def test_qwen_missing_fails_explicitly_without_silent_minilm_fallback(monkeypatch):
    """When the model is missing AND auto-download is disabled, resolution must
    fail with FileNotFoundError rather than silently falling back to 384D MiniLM."""
    import app.services.matching.embeddings as emb_module

    monkeypatch.setattr(emb_module, "find_qwen_model_path", lambda: None)
    monkeypatch.setattr(emb_module.settings, "model_auto_download", False)
    monkeypatch.setattr(emb_module, "_download_attempted", True)

    # Default / production / qwen / mira must raise FileNotFoundError
    with pytest.raises(FileNotFoundError, match="MIRA production Qwen embedding model"):
        resolve_model_name()

    with pytest.raises(FileNotFoundError, match="MIRA production Qwen embedding model"):
        resolve_model_name("production")

    with pytest.raises(FileNotFoundError, match="MIRA production Qwen embedding model"):
        resolve_model_name("qwen")

    with pytest.raises(FileNotFoundError, match="MIRA production Qwen embedding model"):
        resolve_model_name("mira")


def test_cross_platform_candidate_discovery_and_env_overrides(monkeypatch):
    """Verify that model resolution works portably across operating systems and respects env vars."""
    from app.services.matching.embeddings import get_qwen_candidate_paths

    candidates = get_qwen_candidate_paths()
    assert len(candidates) >= 5
    # Ensure no machine-specific absolute username paths are baked in without Path.home()
    assert all(isinstance(p, Path) for p in candidates)

    # Test MIRA_QWEN_MODEL_PATH override
    monkeypatch.setenv("MIRA_QWEN_MODEL_PATH", "/custom/os/independent/path/Mira.ai")
    new_candidates = get_qwen_candidate_paths()
    assert Path("/custom/os/independent/path/Mira.ai") in new_candidates

    # Test direct path in MIRA_EMBEDDING_MODEL
    monkeypatch.setenv("MIRA_EMBEDDING_MODEL", "/custom/model/checkpoint")
    assert resolve_model_name() == "/custom/model/checkpoint"


def test_qwen_embedding_dimension_and_generation():
    """Verify Qwen model generates 1024-dimensional normalized vectors."""
    text = "HEX HEAD BOLT M8 X 25 MM SS304"
    emb = generate_embedding(text)
    assert isinstance(emb, list)
    assert len(emb) == 1024
    vec = np.array(emb, dtype=np.float32)
    norm = float(np.linalg.norm(vec))
    assert abs(norm - 1.0) < 1e-2


def test_qwen_semantic_similarity_discrimination():
    """Verify Qwen similarity on equivalent vs unrelated material descriptions."""
    equiv_left = "HEX HEAD BOLT M8 X 25 MM SS304"
    equiv_right = "BOLT HEX SS304 M8 X 25"
    unrelated = "ROLLER BEARING 50 MM"

    sim_equiv = semantic_similarity(equiv_left, equiv_right)
    sim_unrelated = semantic_similarity(equiv_left, unrelated)

    assert sim_equiv > 0.75, f"Expected high similarity for equivalent bolts, got {sim_equiv}"
    assert sim_unrelated < 0.35, f"Expected low similarity for bolt vs bearing, got {sim_unrelated}"
    assert sim_equiv > sim_unrelated + 0.40


def test_milvus_dimension_matches_qwen():
    """Verify Milvus collection configuration and dynamic dimension derive 1024-dimensional embeddings."""
    assert get_embedding_dimension() == 1024
    from create_milvus_collection import EMBEDDING_DIM
    assert EMBEDDING_DIM == 1024


def test_embedding_cache_with_qwen_defaults():
    """Verify EmbeddingCache precomputes and caches 1024-dimensional Qwen embeddings."""
    items = [
        "SEAMLESS PIPE ASTM A106 GRADE B 2 INCH SCH 40",
        "PIPE SEAMLESS A106-B 2 IN SCH 40",
        "BALL VALVE FLANGED CLASS 150 2 IN",
    ]
    cache = precompute_embeddings(items)
    assert len(cache) == 3
    for item in items:
        assert item in cache
        vec = cache.get(item)
        assert isinstance(vec, np.ndarray)
        assert vec.shape == (1024,)
        assert abs(np.linalg.norm(vec) - 1.0) < 1e-2

    # Verify cached similarity matches uncached similarity within quantization tolerance
    sim_c = cache.similarity(items[0], items[1])
    sim_u = embeddings_semantic_similarity(items[0], items[1])
    assert abs(sim_c - sim_u) < 0.10


def test_qwen_scoring_and_critical_gate_routing():
    """Verify full scoring and classification lifecycle using Qwen default embeddings."""
    # 1. High-confidence equivalent pair (high semantic + high text + all gates pass)
    mat_bolt_a = {
        "id": 1,
        "category": "Fastener",
        "normalized_description": "HEX HEAD BOLT M8 X 25 MM SS304",
        "material_grade": "SS304",
        "parsed_specifications": {
            "dimensions": {"size": "M8", "length": {"value": 25, "unit": "MM"}},
        },
        "other_attributes": {},
    }
    mat_bolt_b = {
        "id": 2,
        "category": "Fastener",
        "normalized_description": "HEX HEAD BOLT M8 X 25 MM SS 304",
        "material_grade": "SS304",
        "parsed_specifications": {
            "dimensions": {"size": "M8", "length": {"value": 25, "unit": "MM"}},
        },
        "other_attributes": {},
    }

    result_equiv = classify_match(mat_bolt_a, mat_bolt_b)
    assert result_equiv["decision"] == "HIGH_CONFIDENCE"
    assert result_equiv["scores"]["final_score"] >= 0.85
    assert all(c["status"] == "PASS" for c in result_equiv["critical_checks"])

    # 2. Review case: different word order with score ~0.836 (review threshold)
    mat_bolt_reordered = {
        "id": 20,
        "category": "Fastener",
        "normalized_description": "BOLT HEX SS304 M8 X 25",
        "material_grade": "SS304",
        "parsed_specifications": {
            "dimensions": {"size": "M8", "length": {"value": 25, "unit": "MM"}},
        },
        "other_attributes": {},
    }
    result_reordered = classify_match(mat_bolt_a, mat_bolt_reordered)
    assert result_reordered["decision"] in ("HIGH_CONFIDENCE", "REVIEW")
    assert result_reordered["scores"]["final_score"] >= 0.80

    # 3. Hard technical conflict (M8x25 vs M8x50) -> DIFFERENT
    mat_bolt_conflict = {
        "id": 3,
        "category": "Fastener",
        "normalized_description": "HEX HEAD BOLT M8 X 50 MM SS304",
        "material_grade": "SS304",
        "parsed_specifications": {
            "dimensions": {"size": "M8", "length": {"value": 50, "unit": "MM"}},
        },
        "other_attributes": {},
    }
    result_conflict = classify_match(mat_bolt_a, mat_bolt_conflict)
    assert result_conflict["decision"] == "DIFFERENT"
    assert any(c["status"] == "CONFLICT" for c in result_conflict["critical_checks"])


def test_batch_embeddings_utility():
    """Verify standalone batch_embeddings helper generates deduplicated 1024D vectors."""
    from app.services.matching.batch_embeddings import generate_embeddings

    texts = [
        "HEX HEAD BOLT M8 X 25 MM SS304",
        "HEX HEAD BOLT M8 X 25 MM SS304",  # Duplicate
        "SEAMLESS PIPE ASTM A106 GRADE B 2 INCH SCH 40",
        "",  # Empty string
    ]
    emb_map = generate_embeddings(texts, batch_size=4)
    assert len(emb_map) == 2
    assert "HEX HEAD BOLT M8 X 25 MM SS304" in emb_map
    assert "SEAMLESS PIPE ASTM A106 GRADE B 2 INCH SCH 40" in emb_map
    vec = emb_map["HEX HEAD BOLT M8 X 25 MM SS304"]
    assert isinstance(vec, list)
    assert len(vec) == 1024
    assert abs(np.linalg.norm(np.array(vec, dtype=np.float32)) - 1.0) < 1e-2


def test_auto_download_used_when_model_absent_locally(monkeypatch):
    """With auto-download on, a missing local model triggers a Hub fetch."""
    import app.services.matching.embeddings as emb_module

    monkeypatch.setattr(emb_module, "find_qwen_model_path", lambda: None)
    monkeypatch.setattr(emb_module.settings, "model_auto_download", True)
    monkeypatch.setattr(emb_module, "_download_attempted", False)

    expected = emb_module._download_target_dir()
    monkeypatch.setattr(emb_module, "_download_qwen_model", lambda dest: dest)

    assert resolve_model_name() == str(expected)


def test_auto_download_failure_still_raises_actionable_error(monkeypatch):
    """A failed download must not silently degrade -- it must raise."""
    import app.services.matching.embeddings as emb_module

    monkeypatch.setattr(emb_module, "find_qwen_model_path", lambda: None)
    monkeypatch.setattr(emb_module.settings, "model_auto_download", True)
    monkeypatch.setattr(emb_module, "_download_attempted", False)
    monkeypatch.setattr(emb_module, "_download_qwen_model", lambda dest: None)
    monkeypatch.setattr(
        emb_module, "_download_failed_reason", "simulated network failure"
    )

    with pytest.raises(FileNotFoundError, match="MIRA production Qwen embedding model"):
        resolve_model_name()


def test_auto_download_does_not_override_local_model(monkeypatch):
    """A local model is always preferred; the Hub is never consulted."""
    import app.services.matching.embeddings as emb_module

    local = Path("/pretend/local/Mira.ai")
    monkeypatch.setattr(emb_module, "find_qwen_model_path", lambda: local)

    def _explode(dest):
        raise AssertionError("auto-download must not run when a local model exists")

    monkeypatch.setattr(emb_module, "_download_qwen_model", _explode)
    assert resolve_model_name() == str(local)


def test_download_target_is_a_searched_path(monkeypatch):
    """The download destination must be discoverable on the next run."""
    import app.services.matching.embeddings as emb_module

    monkeypatch.delenv("MIRA_MODELS_DIR", raising=False)
    monkeypatch.setattr(emb_module.settings, "model_auto_download_dir", "")

    dest = emb_module._download_target_dir()
    candidates = emb_module.get_qwen_candidate_paths()
    assert dest in candidates, f"{dest} is not in the searched candidate paths"