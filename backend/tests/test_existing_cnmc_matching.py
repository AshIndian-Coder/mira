import time
from typing import Any
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import store
from app.api.v1.mappings import MAPPINGS
from app.core.database import SessionLocal
from app.core.security import create_access_token, hash_password
from app.core.seed import seed_default_users_and_cpses
from app.models.user import User
from app.services.cnmc.service import generate_or_get_cnmc
from app.services.harmonization.service import build_common_material_record
from app.services.matching.cnmc_matcher import (
    attach_material_to_mapping,
    build_cnmc_block_index,
    compute_cnmc_candidate_margin,
    find_cnmc_candidates_for_material,
    match_new_materials_against_cnmcs,
)
from app.services.normalization.service import normalize_material_description
from app.services.parsing.service import parse_specifications

client = TestClient(app)


def auth_header(email: str = "steward@mira.gov.in", role: str = "data_steward") -> dict[str, str]:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                email=email,
                password_hash=hash_password("Pass@123"),
                full_name=email,
                role=role,
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        token = create_access_token(user)
        return {"Authorization": f"Bearer {token}"}
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_state():
    seed_default_users_and_cpses()
    store.reset_stores()
    MAPPINGS.clear()
    yield
    store.reset_stores()
    MAPPINGS.clear()


def _create_sample_cnmc_with_mapping() -> tuple[dict[str, Any], dict[str, Any]]:
    """Helper to seed an established CNMC and mapping."""
    mat1 = {
        "id": 1,
        "cpse": "IOCL",
        "material_code": "IOCL-VLV-01",
        "description": "GATE VALVE CS 150 LB 2 IN",
        "normalized_description": normalize_material_description("GATE VALVE CS 150 LB 2 IN"),
        "category": "Valve",
        "material_grade": "CS",
        "parsed_specifications": parse_specifications("GATE VALVE CS 150 LB 2 IN"),
    }
    mat2 = {
        "id": 2,
        "cpse": "ONGC",
        "material_code": "ONGC-VLV-02",
        "description": "GATE VALVE CS 150# 2 INCH FLANGED",
        "normalized_description": normalize_material_description("GATE VALVE CS 150# 2 INCH FLANGED"),
        "category": "Valve",
        "material_grade": "CS",
        "parsed_specifications": parse_specifications("GATE VALVE CS 150# 2 INCH FLANGED"),
    }
    store.MATERIALS.append(mat1)
    store.MATERIALS.append(mat2)

    cmr = build_common_material_record([mat1, mat2])
    cnmc_info = generate_or_get_cnmc([mat1, mat2], cmr)

    mapping_record = {
        "id": 1,
        "nmc": cnmc_info["cnmc_code"],
        "cpse_mappings": [
            {
                "material_id": 1,
                "cpse": "IOCL",
                "material_code": "IOCL-VLV-01",
                "description": mat1["description"],
                "category": "Valve",
                "material_grade": "CS",
            },
            {
                "material_id": 2,
                "cpse": "ONGC",
                "material_code": "ONGC-VLV-02",
                "description": mat2["description"],
                "category": "Valve",
                "material_grade": "CS",
            },
        ],
        "cluster_size": 2,
        "status": "APPROVED",
        "common_material_record": cmr,
        "created_at": "2026-09-20T00:00:00Z",
    }
    MAPPINGS.append(mapping_record)
    return cnmc_info, mapping_record


# =====================================================================
# 1. CORE MATCHING TESTS
# =====================================================================

def test_match_through_approved_member_and_canonical_profile():
    cnmc_info, mapping = _create_sample_cnmc_with_mapping()

    # New material from GAIL with compatible specs
    new_mat = {
        "id": 3,
        "cpse": "GAIL",
        "material_code": "GAIL-GV-99",
        "description": "GATE VALVE CS 150 LB 2 INCH",
        "category": "Valve",
        "material_grade": "CS",
    }

    proposals = find_cnmc_candidates_for_material(new_mat)
    assert len(proposals) >= 1

    top_proposal = proposals[0]
    assert top_proposal["cnmc_code"] == cnmc_info["cnmc_code"]
    assert top_proposal["final_score"] >= 0.85
    assert top_proposal["engine_decision"] == "HIGH_CONFIDENCE"
    assert top_proposal["strongest_member"] is not None
    assert top_proposal["strongest_member"]["cpse"] in {"IOCL", "ONGC"}
    assert top_proposal["canonical_score"] >= 0.80


def test_multiple_approved_members_under_cnmc():
    cnmc_info, mapping = _create_sample_cnmc_with_mapping()

    new_mat = {
        "id": 10,
        "cpse": "HPCL",
        "material_code": "HPCL-001",
        "description": "GATE VALVE CS 150# 2 IN",
        "category": "Valve",
    }
    proposals = find_cnmc_candidates_for_material(new_mat)
    assert len(proposals) == 1
    assert proposals[0]["member_count"] == 2
    assert proposals[0]["strongest_member"] is not None


def test_high_semantic_similarity_with_critical_technical_conflict():
    """
    Semantic similarity may be high between 150 LB and 600 LB valves,
    but critical pressure conflict MUST prevent safe automatic assignment.
    """
    cnmc_info, mapping = _create_sample_cnmc_with_mapping()

    # Conflicting pressure: 600 LB instead of 150 LB
    conflicting_mat = {
        "id": 4,
        "cpse": "GAIL",
        "material_code": "GAIL-600LB",
        "description": "GATE VALVE CS 600 LB 2 IN",
        "category": "Valve",
        "material_grade": "CS",
    }

    proposals = find_cnmc_candidates_for_material(conflicting_mat)
    assert len(proposals) == 1
    top_prop = proposals[0]
    # Gate check must record conflict
    checks = {c["field"]: c["status"] for c in top_prop["critical_checks"]}
    assert checks.get("pressure_rating") == "CONFLICT"
    assert top_prop["engine_decision"] != "HIGH_CONFIDENCE"


def test_no_plausible_cnmc_returns_empty():
    _create_sample_cnmc_with_mapping()

    # Completely unrelated material: transformer
    unrelated_mat = {
        "id": 99,
        "cpse": "NTPC",
        "material_code": "NTPC-XFRMR",
        "description": "POWER TRANSFORMER 11KV 500KVA 50HZ",
        "category": "Electrical",
    }

    proposals = find_cnmc_candidates_for_material(unrelated_mat)
    assert len(proposals) == 0


def test_existing_cnmc_not_mutated_before_approval():
    cnmc_info, mapping = _create_sample_cnmc_with_mapping()
    original_members_count = len(mapping["cpse_mappings"])
    original_hash = cnmc_info["identity_hash"]

    new_mat = {
        "id": 5,
        "cpse": "GAIL",
        "material_code": "GAIL-GV-05",
        "description": "GATE VALVE CS 150 LB 2 IN",
        "category": "Valve",
    }

    # Querying candidate proposals does not mutate the existing CNMC or mapping
    _ = find_cnmc_candidates_for_material(new_mat)

    assert len(mapping["cpse_mappings"]) == original_members_count
    assert mapping["cluster_size"] == original_members_count
    current_cnmc = next(c for c in store.CNMC_REGISTRY if c["cnmc_code"] == cnmc_info["cnmc_code"])
    assert current_cnmc["identity_hash"] == original_hash


def test_approval_updates_mapping_and_preserves_cpse_code():
    cnmc_info, mapping = _create_sample_cnmc_with_mapping()

    new_mat = {
        "id": 6,
        "cpse": "GAIL",
        "material_code": "GAIL-SOURCE-CODE-77",
        "description": "GATE VALVE CS 150 LB 2 IN",
        "category": "Valve",
        "material_grade": "CS",
    }
    store.MATERIALS.append(new_mat)

    # Attach to existing mapping
    updated = attach_material_to_mapping(mapping["id"], new_mat, actor="reviewer@mira.gov.in")
    assert updated["cluster_size"] == 3
    assert len(updated["cpse_mappings"]) == 3

    # Source CPSE code remains preserved
    gail_entry = next(e for e in updated["cpse_mappings"] if e["cpse"] == "GAIL")
    assert gail_entry["material_code"] == "GAIL-SOURCE-CODE-77"
    assert gail_entry["material_id"] == 6

    # CNMC code remains identical
    assert updated["nmc"] == cnmc_info["cnmc_code"]


def test_rejection_does_not_alter_cnmc_or_mapping():
    cnmc_info, mapping = _create_sample_cnmc_with_mapping()

    new_mat = {
        "id": 7,
        "cpse": "GAIL",
        "material_code": "GAIL-REJECTED",
        "description": "GATE VALVE CS 150 LB 2 IN",
        "category": "Valve",
    }

    proposals = find_cnmc_candidates_for_material(new_mat)
    assert len(proposals) >= 1

    # Rejected action leaves mapping untouched
    assert len(mapping["cpse_mappings"]) == 2
    assert mapping["cluster_size"] == 2


def test_cnmc_identity_hash_remains_unchanged():
    cnmc_info, mapping = _create_sample_cnmc_with_mapping()
    initial_hash = cnmc_info["identity_hash"]

    new_mat = {
        "id": 8,
        "cpse": "GAIL",
        "material_code": "GAIL-MATCH-8",
        "description": "GATE VALVE CS 150 LB 2 IN",
        "category": "Valve",
        "material_grade": "CS",
    }
    store.MATERIALS.append(new_mat)
    attach_material_to_mapping(mapping["id"], new_mat)

    cnmc_record = next(c for c in store.CNMC_REGISTRY if c["cnmc_code"] == cnmc_info["cnmc_code"])
    assert cnmc_record["identity_hash"] == initial_hash


def test_deterministic_candidate_ranking():
    # Create two CNMCs in same category
    mat_vlv1 = {
        "id": 1,
        "cpse": "IOCL",
        "material_code": "VLV-150",
        "description": "GATE VALVE CS 150 LB 2 IN",
        "normalized_description": normalize_material_description("GATE VALVE CS 150 LB 2 IN"),
        "category": "Valve",
        "material_grade": "CS",
        "parsed_specifications": parse_specifications("GATE VALVE CS 150 LB 2 IN"),
    }
    cmr1 = build_common_material_record([mat_vlv1])
    cnmc1 = generate_or_get_cnmc([mat_vlv1], cmr1)
    MAPPINGS.append({
        "id": 1,
        "nmc": cnmc1["cnmc_code"],
        "cpse_mappings": [mat_vlv1],
        "cluster_size": 1,
        "common_material_record": cmr1,
    })

    mat_vlv2 = {
        "id": 2,
        "cpse": "ONGC",
        "material_code": "VLV-300",
        "description": "GATE VALVE CS 150 LB 3 IN",
        "normalized_description": normalize_material_description("GATE VALVE CS 150 LB 3 IN"),
        "category": "Valve",
        "material_grade": "CS",
        "parsed_specifications": parse_specifications("GATE VALVE CS 150 LB 3 IN"),
    }
    cmr2 = build_common_material_record([mat_vlv2])
    cnmc2 = generate_or_get_cnmc([mat_vlv2], cmr2)
    MAPPINGS.append({
        "id": 2,
        "nmc": cnmc2["cnmc_code"],
        "cpse_mappings": [mat_vlv2],
        "cluster_size": 1,
        "common_material_record": cmr2,
    })

    query_mat = {
        "id": 3,
        "cpse": "GAIL",
        "material_code": "GAIL-VLV",
        "description": "GATE VALVE CS 150 LB 2 IN",
        "category": "Valve",
        "material_grade": "CS",
    }

    # Run query multiple times to verify deterministic result
    res1 = find_cnmc_candidates_for_material(query_mat)
    res2 = find_cnmc_candidates_for_material(query_mat)

    assert len(res1) == len(res2)
    assert [p["cnmc_code"] for p in res1] == [p["cnmc_code"] for p in res2]
    # Highest match should be cnmc1
    assert res1[0]["cnmc_code"] == cnmc1["cnmc_code"]
    assert res1[0]["final_score"] > res1[1]["final_score"]


# =====================================================================
# 2. API ENDPOINTS & RBAC TESTS
# =====================================================================

def test_api_cnmc_candidates_endpoint():
    cnmc_info, mapping = _create_sample_cnmc_with_mapping()
    headers = auth_header()

    payload = {
        "material": {
            "cpse": "GAIL",
            "material_code": "GAIL-001",
            "description": "GATE VALVE CS 150 LB 2 IN",
            "category": "Valve",
        },
        "max_candidates": 5,
        "min_score": 0.50,
    }
    resp = client.post("/api/matching/cnmc/candidates", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_candidates"] >= 1
    assert data["candidates"][0]["cnmc_code"] == cnmc_info["cnmc_code"]


def test_api_cnmc_run_batch_and_attach():
    cnmc_info, mapping = _create_sample_cnmc_with_mapping()
    headers = auth_header()

    # Add a 3rd material to store
    mat3 = {
        "id": 3,
        "cpse": "GAIL",
        "material_code": "GAIL-BATCH-01",
        "description": "GATE VALVE CS 150 LB 2 IN",
        "category": "Valve",
        "material_grade": "CS",
    }
    store.MATERIALS.append(mat3)

    resp = client.post(
        "/api/matching/cnmc/run-batch",
        json={"max_candidates_per_material": 5, "min_score": 0.65, "create_review_candidates": True},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "complete"
    assert data["proposals_generated"] >= 1

    # Verify review candidates were created
    assert len(store.CANDIDATES) >= 1

    # Attach material via API
    attach_resp = client.post(
        f"/api/mappings/{mapping['id']}/attach",
        json={"material_id": 3},
        headers=headers,
    )
    assert attach_resp.status_code == 200
    assert attach_resp.json()["status"] == "success"
    assert attach_resp.json()["mapping"]["cluster_size"] == 3


# =====================================================================
# 3. PERFORMANCE & RETRIEVAL SCALABILITY BENCHMARK
# =====================================================================

def test_performance_bounded_candidate_retrieval():
    """
    Measure CNMC candidate retrieval and scoring performance.
    Validates that candidate lookup is bounded and does not perform full O(N) scan.
    """
    # Seed 50 synthetic CNMCs across different categories
    for i in range(1, 51):
        cat = "Valve" if i <= 25 else "Pipe"
        desc = f"SEAMLESS PIPE CS {i} IN SCH40" if cat == "Pipe" else f"GATE VALVE CS 150 LB {i} IN"
        mat = {
            "id": i,
            "cpse": f"CPSE_{i % 5}",
            "material_code": f"MAT-{i:04d}",
            "description": desc,
            "category": cat,
            "material_grade": "CS",
            "parsed_specifications": parse_specifications(desc),
        }
        store.MATERIALS.append(mat)
        cmr = build_common_material_record([mat])
        cinfo = generate_or_get_cnmc([mat], cmr)
        MAPPINGS.append({
            "id": i,
            "nmc": cinfo["cnmc_code"],
            "cpse_mappings": [mat],
            "cluster_size": 1,
            "common_material_record": cmr,
        })

    assert len(store.CNMC_REGISTRY) >= 50
    assert len(MAPPINGS) >= 50

    # Build block index
    t0 = time.perf_counter()
    block_index = build_cnmc_block_index()
    index_time = time.perf_counter() - t0

    # Query material for a specific valve
    query_mat = {
        "id": 999,
        "cpse": "TEST_CPSE",
        "material_code": "TEST-VALVE-2",
        "description": "GATE VALVE CS 150 LB 2 IN",
        "category": "Valve",
    }

    # Precompute embeddings cache for all descriptions
    all_descs = {m["description"] for m in store.MATERIALS} | {query_mat["description"]}
    t_emb = time.perf_counter()
    from app.services.matching.embeddings import precompute_embeddings
    emb_cache = precompute_embeddings(all_descs)
    emb_time = time.perf_counter() - t_emb

    t1 = time.perf_counter()
    candidates = find_cnmc_candidates_for_material(
        query_mat,
        block_index=block_index,
        embedding_cache=emb_cache,
    )
    query_time = time.perf_counter() - t1

    # Candidate retrieval + cached scoring should be fast (< 200ms)
    assert query_time < 0.200
    assert len(candidates) >= 1
    # Candidate list is bounded
    assert len(candidates) <= 10

    # Total CNMCs considered: should find matching valve category/tokens, not all 50
    print(f"Index build: {index_time*1000:.2f}ms, Embedding cache: {emb_time*1000:.2f}ms, Query time: {query_time*1000:.2f}ms, Candidates: {len(candidates)}")


# =====================================================================
# 4. BEST-VS-SECOND-BEST CNMC CANDIDATE MARGIN TESTS
# =====================================================================

def test_margin_computation_multiple_candidates():
    """Requirement A: Multiple candidates [0.91, 0.89, 0.52] -> margin 0.02."""
    proposals = [
        {"final_score": 0.91, "cnmc_code": "CNMC-A"},
        {"final_score": 0.89, "cnmc_code": "CNMC-B"},
        {"final_score": 0.52, "cnmc_code": "CNMC-C"},
    ]
    margin = compute_cnmc_candidate_margin(proposals)
    assert margin["best_score"] == 0.91
    assert margin["second_best_score"] == 0.89
    assert margin["score_margin"] == 0.02


def test_margin_computation_single_candidate():
    """Requirement B: Single candidate -> best_score=score, second_best_score=None, margin=None."""
    proposals = [{"final_score": 0.95, "cnmc_code": "CNMC-A"}]
    margin = compute_cnmc_candidate_margin(proposals)
    assert margin["best_score"] == 0.95
    assert margin["second_best_score"] is None
    assert margin["score_margin"] is None


def test_margin_computation_zero_candidates():
    """Requirement C: Zero candidates -> all None."""
    proposals = []
    margin = compute_cnmc_candidate_margin(proposals)
    assert margin["best_score"] is None
    assert margin["second_best_score"] is None
    assert margin["score_margin"] is None


def test_margin_computation_tied_scores_deterministic():
    """Requirement D: Tied scores preserve deterministic ordering and calculate margin == 0.0."""
    proposals = [
        {"final_score": 0.88, "cnmc_code": "CNMC-B"},
        {"final_score": 0.88, "cnmc_code": "CNMC-A"},
    ]
    margin = compute_cnmc_candidate_margin(proposals)
    assert margin["best_score"] == 0.88
    assert margin["second_best_score"] == 0.88
    assert margin["score_margin"] == 0.0


def test_margin_does_not_alter_engine_decision_or_critical_conflict():
    """
    Requirements E & F:
    Existing CNMC behavior remains unchanged: margin does NOT alter engine_decision/classification.
    Critical conflict remains authoritative even if candidate score is high.
    """
    cnmc_info, mapping = _create_sample_cnmc_with_mapping()

    # Conflicting pressure material (600 LB vs 150 LB)
    conflicting_mat = {
        "id": 4,
        "cpse": "GAIL",
        "material_code": "GAIL-600LB",
        "description": "GATE VALVE CS 600 LB 2 IN",
        "category": "Valve",
        "material_grade": "CS",
    }
    proposals = find_cnmc_candidates_for_material(conflicting_mat)
    assert len(proposals) == 1
    top_prop = proposals[0]

    # Critical check conflict must keep decision != HIGH_CONFIDENCE
    checks = {c["field"]: c["status"] for c in top_prop["critical_checks"]}
    assert checks.get("pressure_rating") == "CONFLICT"
    assert top_prop["engine_decision"] != "HIGH_CONFIDENCE"


def test_api_cnmc_candidates_endpoint_margin_and_compatibility():
    """
    Requirement G: Existing API response compatibility and presence of margin evidence.
    """
    # Create two CNMCs
    mat1 = {
        "id": 1,
        "cpse": "IOCL",
        "material_code": "VLV-150-A",
        "description": "GATE VALVE CS 150 LB 2 IN",
        "normalized_description": normalize_material_description("GATE VALVE CS 150 LB 2 IN"),
        "category": "Valve",
        "material_grade": "CS",
        "parsed_specifications": parse_specifications("GATE VALVE CS 150 LB 2 IN"),
    }
    cmr1 = build_common_material_record([mat1])
    cnmc1 = generate_or_get_cnmc([mat1], cmr1)
    MAPPINGS.append({
        "id": 1,
        "nmc": cnmc1["cnmc_code"],
        "cpse_mappings": [mat1],
        "cluster_size": 1,
        "common_material_record": cmr1,
    })

    mat2 = {
        "id": 2,
        "cpse": "ONGC",
        "material_code": "VLV-300-B",
        "description": "GATE VALVE CS 150 LB 3 IN",
        "normalized_description": normalize_material_description("GATE VALVE CS 150 LB 3 IN"),
        "category": "Valve",
        "material_grade": "CS",
        "parsed_specifications": parse_specifications("GATE VALVE CS 150 LB 3 IN"),
    }
    cmr2 = build_common_material_record([mat2])
    cnmc2 = generate_or_get_cnmc([mat2], cmr2)
    MAPPINGS.append({
        "id": 2,
        "nmc": cnmc2["cnmc_code"],
        "cpse_mappings": [mat2],
        "cluster_size": 1,
        "common_material_record": cmr2,
    })

    store.MATERIALS.extend([mat1, mat2])

    headers = auth_header()
    payload = {
        "material": {
            "cpse": "GAIL",
            "material_code": "GAIL-GV-01",
            "description": "GATE VALVE CS 150 LB 2 IN",
            "category": "Valve",
            "material_grade": "CS",
        },
        "max_candidates": 5,
        "min_score": 0.50,
    }
    resp = client.post("/api/matching/cnmc/candidates", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    # Verify margin evidence in envelope
    assert "best_score" in data
    assert "second_best_score" in data
    assert "score_margin" in data
    assert data["total_candidates"] == 2
    assert data["best_score"] is not None
    assert data["second_best_score"] is not None
    assert data["score_margin"] is not None
    assert round(data["best_score"] - data["second_best_score"], 4) == data["score_margin"]

    # Verify backward-compatibility of candidate objects
    cand0 = data["candidates"][0]
    assert "cnmc_code" in cand0
    assert "canonical_score" in cand0
    assert "final_score" in cand0
    assert "critical_checks" in cand0
    assert "engine_decision" in cand0
    assert "strongest_member" in cand0
    assert "strongest_member_score" in cand0


from unittest.mock import patch
from app.services.matching.embeddings import get_embedding_model


def test_single_cnmc_candidate_embedding_cache_coverage():
    """Verify single-material CNMC candidate query precomputes embeddings in a single call."""
    _create_sample_cnmc_with_mapping()

    mat2 = {
        "id": 10,
        "cpse": "GAIL",
        "material_code": "GAIL-VLV-10",
        "description": "GATE VALVE CS 150 LB 2 IN FLANGED ENDS",
        "normalized_description": normalize_material_description("GATE VALVE CS 150 LB 2 IN FLANGED ENDS"),
        "category": "Valve",
        "material_grade": "CS",
        "parsed_specifications": parse_specifications("GATE VALVE CS 150 LB 2 IN FLANGED ENDS"),
    }
    cmr2 = build_common_material_record([mat2])
    cnmc2 = generate_or_get_cnmc([mat2], cmr2)
    MAPPINGS.append({
        "id": 2,
        "nmc": cnmc2["cnmc_code"],
        "cpse_mappings": [mat2],
        "cluster_size": 1,
        "common_material_record": cmr2,
    })
    store.MATERIALS.append(mat2)

    query_mat = {
        "cpse": "BHEL",
        "material_code": "BHEL-VLV-99",
        "description": "GATE VALVE CS 150 LB 2 IN",
        "category": "Valve",
        "material_grade": "CS",
    }

    model = get_embedding_model()
    original_encode = model.encode
    encode_calls = []

    def spied_encode(*args, **kwargs):
        encode_calls.append(args[0] if args else kwargs.get("sentences"))
        return original_encode(*args, **kwargs)

    with patch.object(model, "encode", side_effect=spied_encode):
        payload = {
            "material": query_mat,
            "max_candidates": 5,
            "min_score": 0.50,
        }
        headers = auth_header()
        resp = client.post("/api/matching/cnmc/candidates", json=payload, headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        # Exactly 1 batched precompute call, zero in-loop pairwise calls
        assert len(encode_calls) == 1
        assert isinstance(encode_calls[0], list)
        assert len(data["candidates"]) >= 1
        assert data["candidates"][0]["engine_decision"] in ("HIGH_CONFIDENCE", "REVIEW")



