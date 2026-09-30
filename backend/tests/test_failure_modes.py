"""
Comprehensive Failure-Mode and Resilience Audit Test Suite.

Tests the current MIRA system against bad inputs and operational failure modes:
1. DATA: empty CSV, missing columns, missing description, missing CPSE,
         duplicate material codes, malformed rows, unknown category,
         unknown units, malformed specifications.
2. MATCHING: same-CPSE pair, no candidates, missing specifications,
            conflicting specifications, identical descriptions but conflicting critical attributes.
3. REVIEW: approve nonexistent, reject nonexistent, repeated approval,
           repeated rejection, unauthorized review action.
4. CNMC: identical identity, different identity, missing identity fields,
         concurrent allocation, repeated generation.
5. AUTH: missing token, invalid token, inactive user, wrong role,
         unauthorized endpoint access.
6. EXPORT: no mappings, mappings with missing optional fields, large export.
"""

import io
from concurrent.futures import ThreadPoolExecutor
from typing import Any
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import store
from app.core.database import SessionLocal
from app.core.security import create_access_token, hash_password
from app.core.seed import seed_default_users_and_cpses
from app.models.user import User
from app.services.normalization.service import normalize_material_description
from app.services.parsing.service import parse_specifications
from app.services.blocking.service import (
    MaterialForBlocking,
    generate_candidates as blocking_generate_candidates,
)
from app.services.matching.classifier import classify_match
from app.services.matching.critical_gates import evaluate_critical_gates
from app.services.matching.scoring import calculate_match_score
from app.services.harmonization.service import build_common_material_record
from app.services.cnmc.service import generate_or_get_cnmc
from app.services.cnmc.canonicalization import build_canonical_identity_string

client = TestClient(app)


def auth_header(email: str, role: str = "admin") -> dict[str, str]:
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
    from app.api.v1.mappings import MAPPINGS
    MAPPINGS.clear()
    from app.api.v1.audit import AUDIT_EVENTS
    AUDIT_EVENTS.clear()
    yield
    store.reset_stores()


# =====================================================================
# 1. DATA FAILURE MODES
# =====================================================================

def test_data_empty_csv():
    headers = auth_header("steward@mira.gov.in", "data_steward")
    file_bytes = b""
    resp = client.post(
        "/api/materials/upload",
        files={"file": ("empty.csv", io.BytesIO(file_bytes), "text/csv")},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["records_ingested"] == 0
    assert data["total_materials"] == 0


def test_data_missing_required_columns():
    headers = auth_header("steward@mira.gov.in", "data_steward")
    csv_content = "unknown_header_1,unknown_header_2\nfoo,bar\n"
    resp = client.post(
        "/api/materials/upload",
        files={"file": ("bad_cols.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["records_ingested"] == 0


def test_data_missing_description():
    headers = auth_header("steward@mira.gov.in", "data_steward")
    csv_content = (
        "cpse,material_code,description\n"
        "IOCL,MAT-001,\n"
        "IOCL,MAT-002,   \n"
        "ONGC,MAT-003,GATE VALVE CS 150 LB 2 IN\n"
    )
    resp = client.post(
        "/api/materials/upload",
        files={"file": ("missing_desc.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["records_ingested"] == 1
    assert data["total_materials"] == 1
    assert data["sample"][0]["material_code"] == "MAT-003"


def test_data_missing_cpse():
    headers = auth_header("steward@mira.gov.in", "data_steward")
    csv_content = (
        "material_code,description\n"
        "MAT-001,BALL VALVE SS304 300 LB 3 IN\n"
    )
    resp = client.post(
        "/api/materials/upload",
        files={"file": ("missing_cpse.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["records_ingested"] == 1
    assert data["sample"][0]["cpse"] == "CPSE_GENERIC"


def test_data_duplicate_material_codes():
    headers = auth_header("steward@mira.gov.in", "data_steward")
    csv_content = (
        "cpse,material_code,description\n"
        "IOCL,MAT-DUP,GATE VALVE CS 150 LB 2 IN\n"
        "IOCL,MAT-DUP,GATE VALVE CS 150 LB 2 IN REVISION 2\n"
    )
    resp = client.post(
        "/api/materials/upload",
        files={"file": ("dup_codes.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["records_ingested"] == 2
    assert data["sample"][0]["id"] != data["sample"][1]["id"]


def test_data_malformed_rows_and_utf8_bom():
    headers = auth_header("steward@mira.gov.in", "data_steward")
    bom_content = "\ufeffcpse,material_code,description,category\nIOCL,MAT-101,\"GATE VALVE, CS 150#\",Valve\nONGC,MAT-102\n"
    resp = client.post(
        "/api/materials/upload",
        files={"file": ("bom.csv", io.BytesIO(bom_content.encode("utf-8")), "text/csv")},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["records_ingested"] == 1
    assert data["sample"][0]["material_code"] == "MAT-101"


def test_data_unknown_category_and_units():
    norm = normalize_material_description("UNKNOWN_ITEM 9999 FOOBAR")
    assert isinstance(norm, str)
    
    parsed = parse_specifications("UNKNOWN_ITEM_WITHOUT_UNITS 9999 FOOBAR")
    assert parsed.get("material_grade") is None
    assert parsed.get("pressure_rating") is None
    assert parsed.get("dimensions") is None


def test_data_malformed_specifications():
    desc = "VALVE SIZE -5 INCH PRESSURE 0 LB GR 9999999"
    parsed = parse_specifications(desc)
    assert isinstance(parsed, dict)


# =====================================================================
# 2. MATCHING FAILURE MODES
# =====================================================================

def test_matching_same_cpse_pair():
    headers = auth_header("steward@mira.gov.in", "data_steward")
    csv_content = (
        "cpse,material_code,description,category\n"
        "IOCL,MAT-1,GATE VALVE CS 150 LB 2 IN,Valve\n"
        "IOCL,MAT-2,GATE VALVE CS 150 LB 2 IN,Valve\n"
    )
    client.post(
        "/api/materials/upload",
        files={"file": ("same_cpse.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        headers=headers,
    )
    batch_resp = client.post(
        "/api/matching/run-batch",
        headers=headers,
        json={"overwrite": True},
    )
    assert batch_resp.status_code == 200
    # Both from IOCL -> 0 cross-CPSE candidates found
    assert batch_resp.json()["candidate_pairs_evaluated"] == 0
    assert batch_resp.json()["new_candidates_stored"] == 0


def test_matching_no_candidates():
    headers = auth_header("steward@mira.gov.in", "data_steward")
    # Empty material store
    batch_resp = client.post(
        "/api/matching/run-batch",
        headers=headers,
        json={"overwrite": True},
    )
    assert batch_resp.status_code == 400
    assert "no materials ingested" in batch_resp.json()["detail"].lower()


def test_matching_missing_specifications():
    mat_a = {"id": 1, "cpse": "IOCL", "material_code": "A1", "description": "GENERAL EQUIPMENT", "parsed_specifications": {}}
    mat_b = {"id": 2, "cpse": "ONGC", "material_code": "B1", "description": "GENERIC ITEM", "parsed_specifications": {}}
    
    res = classify_match(mat_a, mat_b)
    assert "decision" in res
    assert "scores" in res
    assert "critical_checks" in res


def test_matching_conflicting_specifications():
    mat_a = {
        "id": 1,
        "cpse": "IOCL",
        "material_code": "A1",
        "description": "GATE VALVE CS 150 LB 2 IN",
        "category": "Valve",
        "material_grade": "CS",
        "parsed_specifications": {
            "pressure_rating": {"value": 150.0, "unit": "LB"},
            "dimensions": {"value": 2.0, "unit": "IN"},
            "material_grade": "CS",
        },
    }
    mat_b = {
        "id": 2,
        "cpse": "ONGC",
        "material_code": "B1",
        "description": "GATE VALVE CS 600 LB 6 IN",
        "category": "Valve",
        "material_grade": "CS",
        "parsed_specifications": {
            "pressure_rating": {"value": 600.0, "unit": "LB"},
            "dimensions": {"value": 6.0, "unit": "IN"},
            "material_grade": "CS",
        },
    }
    res = classify_match(mat_a, mat_b)
    checks = {c["field"]: c["status"] for c in res["critical_checks"]}
    assert checks.get("pressure_rating") == "CONFLICT"
    assert checks.get("dimensions") == "CONFLICT"
    assert res["decision"] == "DIFFERENT"  # flagged as different due to hard technical conflict


def test_matching_identical_description_conflicting_grade():
    mat_a = {
        "id": 1,
        "cpse": "IOCL",
        "material_code": "A1",
        "category": "Fastener",
        "description": "HEX BOLT 2 IN",
        "material_grade": "SS316",
        "parsed_specifications": {"material_grade": "SS316", "dimensions": {"value": 2.0, "unit": "IN"}},
    }
    mat_b = {
        "id": 2,
        "cpse": "ONGC",
        "material_code": "B1",
        "category": "Fastener",
        "description": "HEX BOLT 2 IN",
        "material_grade": "CS",
        "parsed_specifications": {"material_grade": "CS", "dimensions": {"value": 2.0, "unit": "IN"}},
    }
    res = classify_match(mat_a, mat_b)
    checks = {c["field"]: c["status"] for c in res["critical_checks"]}
    assert checks.get("material_grade") == "CONFLICT"
    assert res["decision"] == "DIFFERENT"


# =====================================================================
# 3. REVIEW FAILURE MODES
# =====================================================================

def test_review_nonexistent_candidate():
    headers = auth_header("reviewer@mira.gov.in", "reviewer")
    resp = client.post(
        "/api/review/queue/99999/action",
        json={"action": "APPROVE"},
        headers=headers,
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()

    resp2 = client.post(
        "/api/review/queue/99999/action",
        json={"action": "REJECT"},
        headers=headers,
    )
    assert resp2.status_code == 404


def test_review_repeated_approval_and_rejection():
    headers = auth_header("reviewer@mira.gov.in", "reviewer")
    store.MATERIALS.append({
        "id": 1, "cpse": "IOCL", "material_code": "IOCL-01", "description": "GATE VALVE 1",
    })
    store.MATERIALS.append({
        "id": 2, "cpse": "ONGC", "material_code": "ONGC-01", "description": "GATE VALVE 2",
    })
    store.CANDIDATES.append({
        "id": 101,
        "source_material_id": 1,
        "target_material_id": 2,
        "source_code": "IOCL-01",
        "target_code": "ONGC-01",
        "source_cpse": "IOCL",
        "target_cpse": "ONGC",
        "engine_decision": "REVIEW",
        "review_status": "PENDING",
        "scores": {"final_score": 0.85},
        "critical_checks": [],
    })

    # First approval -> 200 OK
    resp1 = client.post(
        "/api/review/queue/101/action",
        json={"action": "APPROVE", "reviewer_comments": "Verified"},
        headers=headers,
    )
    assert resp1.status_code == 200
    assert resp1.json()["candidate"]["review_status"] == "APPROVED"

    # Repeated approval -> 409 Conflict
    resp2 = client.post(
        "/api/review/queue/101/action",
        json={"action": "APPROVE"},
        headers=headers,
    )
    assert resp2.status_code == 409
    assert "already has status 'APPROVED'" in resp2.json()["detail"]

    # Rejection of already approved -> 409 Conflict
    resp3 = client.post(
        "/api/review/queue/101/action",
        json={"action": "REJECT"},
        headers=headers,
    )
    assert resp3.status_code == 409


def test_review_unauthorized_action():
    headers = auth_header("auditor@mira.gov.in", "auditor")
    store.MATERIALS.append({
        "id": 3, "cpse": "IOCL", "material_code": "IOCL-02", "description": "VALVE 3",
    })
    store.MATERIALS.append({
        "id": 4, "cpse": "ONGC", "material_code": "ONGC-02", "description": "VALVE 4",
    })
    store.CANDIDATES.append({
        "id": 102,
        "source_material_id": 3,
        "target_material_id": 4,
        "source_code": "IOCL-02",
        "target_code": "ONGC-02",
        "source_cpse": "IOCL",
        "target_cpse": "ONGC",
        "engine_decision": "REVIEW",
        "review_status": "PENDING",
        "scores": {"final_score": 0.85},
        "critical_checks": [],
    })
    resp = client.post(
        "/api/review/queue/102/action",
        json={"action": "APPROVE"},
        headers=headers,
    )
    assert resp.status_code == 403


# =====================================================================
# 4. CNMC FAILURE MODES
# =====================================================================

def test_cnmc_identical_and_different_identities():
    m1 = [{"id": 1, "category": "Valve", "material_grade": "CS", "description": "GATE VALVE 150 LB 2 IN"}]
    cmr1 = build_common_material_record(m1)
    cnmc1 = generate_or_get_cnmc(m1, cmr1)

    m2 = [{"id": 2, "category": "Valve", "material_grade": "CS", "description": "GATE VALVE 150 LB 2 IN"}]
    cmr2 = build_common_material_record(m2)
    cnmc2 = generate_or_get_cnmc(m2, cmr2)
    assert cnmc1["cnmc_code"] == cnmc2["cnmc_code"]
    assert cnmc1["identity_hash"] == cnmc2["identity_hash"]

    m3 = [{"id": 3, "category": "Valve", "material_grade": "SS316", "description": "GATE VALVE 150 LB 2 IN"}]
    cmr3 = build_common_material_record(m3)
    cnmc3 = generate_or_get_cnmc(m3, cmr3)
    assert cnmc3["cnmc_code"] != cnmc1["cnmc_code"]
    assert cnmc3["identity_hash"] != cnmc1["identity_hash"]


def test_cnmc_missing_identity_fields():
    m = [{"id": 1, "description": "MISCELLANEOUS HARDWARE"}]
    cmr = build_common_material_record(m)
    cnmc_info = generate_or_get_cnmc(m, cmr)
    assert cnmc_info["cnmc_code"].startswith("MIRA-GEN-")
    ident_str = build_canonical_identity_string(cmr, "GEN", "00")
    assert "UNKNOWN" in ident_str


def test_cnmc_concurrent_allocation():
    results = []

    def allocate(i: int):
        cat = "Valve" if i % 2 == 0 else "Pipe"
        desc = "GATE VALVE 2 IN" if i % 2 == 0 else "SEAMLESS PIPE 2 IN"
        m = [{"id": i, "category": cat, "material_grade": "CS", "description": desc}]
        cmr = build_common_material_record(m)
        info = generate_or_get_cnmc(m, cmr)
        return info["cnmc_code"]

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(allocate, i) for i in range(20)]
        for f in futures:
            results.append(f.result())

    valve_codes = {results[i] for i in range(20) if i % 2 == 0}
    pipe_codes = {results[i] for i in range(20) if i % 2 != 0}
    assert len(valve_codes) == 1
    assert len(pipe_codes) == 1
    assert list(valve_codes)[0] != list(pipe_codes)[0]


# =====================================================================
# 5. AUTH FAILURE MODES
# =====================================================================

def test_auth_missing_token():
    resp = client.get("/api/materials")
    assert resp.status_code == 401
    assert "not authenticated" in resp.json()["detail"].lower()


def test_auth_invalid_token():
    headers = {"Authorization": "Bearer invalid.token.value"}
    resp = client.get("/api/materials", headers=headers)
    assert resp.status_code == 401
    assert "could not validate credentials" in resp.json()["detail"].lower()


def test_auth_inactive_user():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "deactivated@mira.gov.in").first()
        if not user:
            user = User(
                email="deactivated@mira.gov.in",
                password_hash=hash_password("Pass@123"),
                full_name="Deactivated User",
                role="reviewer",
                is_active=False,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            user.is_active = False
            db.commit()
            db.refresh(user)
        token = create_access_token(user)
    finally:
        db.close()

    resp = client.get("/api/materials", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    assert "deactivated" in resp.json()["detail"].lower()


def test_auth_wrong_role():
    # Reviewer trying to upload materials (requires upload_data permission)
    headers = auth_header("reviewer@mira.gov.in", "reviewer")
    resp = client.post(
        "/api/materials/upload",
        files={"file": ("test.csv", b"cpse,material_code,description\nIOCL,1,VALVE", "text/csv")},
        headers=headers,
    )
    assert resp.status_code == 403
    assert "not authorized" in resp.json()["detail"].lower()


def test_auth_unauthorized_endpoints():
    endpoints = [
        ("GET", "/api/materials"),
        ("POST", "/api/materials/upload"),
        ("GET", "/api/matching/candidates"),
        ("POST", "/api/matching/run-batch"),
        ("GET", "/api/review/queue"),
        ("GET", "/api/mappings"),
        ("POST", "/api/mappings/generate"),
        ("GET", "/api/mappings/export/flat"),
        ("GET", "/api/audit"),
    ]
    for method, path in endpoints:
        if method == "GET":
            r = client.get(path)
        else:
            r = client.post(path)
        assert r.status_code == 401, f"Expected 401 for {method} {path}, got {r.status_code}"


# =====================================================================
# 6. EXPORT FAILURE MODES
# =====================================================================

def test_export_no_mappings():
    headers = auth_header("auditor@mira.gov.in", "auditor")
    resp = client.get("/api/mappings/export/flat", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_rows"] == 0
    assert data["rows"] == []


def test_export_mappings_missing_optional_fields():
    headers = auth_header("auditor@mira.gov.in", "auditor")
    from app.api.v1.mappings import MAPPINGS
    MAPPINGS.append({
        "id": 1,
        "nmc": "MIRA-GEN-00-1",
        "cpse_mappings": [
            {
                "material_id": 1,
                "cpse": "IOCL",
                "material_code": "MAT-001",
                "description": "MISC PART",
            }
        ],
        "cluster_size": 1,
        "status": "PROVISIONAL",
        "created_at": "2026-09-19T00:00:00Z",
    })

    resp = client.get("/api/mappings/export/flat", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_rows"] == 1
    row = data["rows"][0]
    assert row["nmc"] == "MIRA-GEN-00-1"
    assert row["category"] is None
    assert row["material_grade"] is None


def test_export_large_dataset():
    headers = auth_header("auditor@mira.gov.in", "auditor")
    from app.api.v1.mappings import MAPPINGS
    for i in range(1, 1001):
        MAPPINGS.append({
            "id": i,
            "nmc": f"MIRA-VLV-17-{i}",
            "cpse_mappings": [
                {
                    "material_id": i * 2,
                    "cpse": "IOCL",
                    "material_code": f"IOCL-{i}",
                    "description": f"GATE VALVE {i}",
                    "category": "Valve",
                    "material_grade": "CS",
                },
                {
                    "material_id": i * 2 + 1,
                    "cpse": "ONGC",
                    "material_code": f"ONGC-{i}",
                    "description": f"GATE VALVE {i}",
                    "category": "Valve",
                    "material_grade": "CS",
                },
            ],
            "cluster_size": 2,
            "status": "APPROVED",
            "created_at": "2026-09-19T00:00:00Z",
        })

    resp = client.get("/api/mappings/export/flat", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_rows"] == 2000
    assert len(data["rows"]) == 2000


def test_review_queue_server_side_pagination():
    headers = auth_header("reviewer@mira.gov.in", "reviewer")
    store.CANDIDATES.clear()

    # Ensure valid source and target materials exist for foreign keys
    m1_id = 9101
    m2_id = 9102
    existing_ids = {m["id"] for m in store.MATERIALS}
    if m1_id not in existing_ids:
        store.MATERIALS.append({
            "id": m1_id, "cpse": "NTPC", "material_code": "MAT-NTPC-9101", "description": "Valve Component NTPC",
        })
    if m2_id not in existing_ids:
        store.MATERIALS.append({
            "id": m2_id, "cpse": "BHEL", "material_code": "MAT-BHEL-9102", "description": "Valve Component BHEL",
        })

    # Populate 55 review candidates
    for i in range(1, 56):
        store.CANDIDATES.append({
            "id": 1000 + i,
            "source_material_id": m1_id,
            "target_material_id": m2_id,
            "source_code": f"MAT-A-{i}",
            "target_code": f"MAT-B-{i}",
            "source_cpse": "NTPC",
            "target_cpse": "BHEL",
            "source_description": f"Valve Component {i}",
            "target_description": f"Valve Component {i} Equiv",
            "engine_decision": "REVIEW",
            "review_status": "PENDING",
            "scores": {"final_score": 0.82},
            "critical_checks": [],
        })

    # Page 1 (skip=0, limit=50)
    p1 = client.get("/api/review/queue?skip=0&limit=50", headers=headers)
    assert p1.status_code == 200
    d1 = p1.json()
    assert d1["total_pending"] == 55
    assert d1["skip"] == 0
    assert d1["limit"] == 50
    assert len(d1["queue"]) == 50

    # Page 2 (skip=50, limit=50)
    p2 = client.get("/api/review/queue?skip=50&limit=50", headers=headers)
    assert p2.status_code == 200
    d2 = p2.json()
    assert d2["total_pending"] == 55
    assert d2["skip"] == 50
    assert len(d2["queue"]) == 5

    p1_ids = {c["id"] for c in d1["queue"]}
    p2_ids = {c["id"] for c in d2["queue"]}
    assert len(p1_ids) == 50
    assert len(p2_ids) == 5
    assert len(p1_ids & p2_ids) == 0
    assert p1_ids | p2_ids == {1000 + i for i in range(1, 56)}

    # Out of bounds (skip=100, limit=50)
    p3 = client.get("/api/review/queue?skip=100&limit=50", headers=headers)
    assert p3.status_code == 200
    d3 = p3.json()
    assert d3["total_pending"] == 55
    assert len(d3["queue"]) == 0

    # Approve first candidate on page 2
    cand_to_approve = d2["queue"][0]["id"]
    action_resp = client.post(
        f"/api/review/queue/{cand_to_approve}/action",
        json={"action": "APPROVE", "reviewer_comments": "Verified"},
        headers=headers,
    )
    assert action_resp.status_code == 200

    # Total pending is now 54; page 2 now has 4 items
    p2_after = client.get("/api/review/queue?skip=50&limit=50", headers=headers)
    assert p2_after.status_code == 200
    d2_after = p2_after.json()
    assert d2_after["total_pending"] == 54
    assert len(d2_after["queue"]) == 4
    assert all(c["id"] != cand_to_approve for c in d2_after["queue"])
