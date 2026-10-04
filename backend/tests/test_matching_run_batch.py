from fastapi.testclient import TestClient
import pytest

from app.main import app
from app import store
from app.api.v1.mappings import MAPPINGS
from app.api.v1.audit import AUDIT_EVENTS
from app.core.seed import seed_default_users_and_cpses


client = TestClient(app)


@pytest.fixture
def auth_headers():
    seed_default_users_and_cpses()
    resp = client.post(
        "/api/auth/login",
        json={"email": "admin@mira.gov.in", "password": "Admin@123"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_run_batch_generates_and_persists_candidate(auth_headers):
    store.reset_stores()
    MAPPINGS.clear()
    AUDIT_EVENTS.clear()

    try:
        csv_content = """cpse,material_code,description,category,material_grade
NTPC,NTPC-VALVE-001,SS 304 GATE VALVE 2 IN 150 LB,Valve,SS304
BHEL,BHEL-VALVE-001,SS 304 GATE VALVE 2 IN 150 LB,Valve,SS304
"""

        upload_response = client.post(
            "/api/materials/upload",
            headers=auth_headers,
            files={
                "file": (
                    "integration_test.csv",
                    csv_content,
                    "text/csv",
                )
            },
        )

        assert upload_response.status_code == 200

        upload_data = upload_response.json()
        assert upload_data["records_ingested"] == 2

        batch_response = client.post(
            "/api/matching/run-batch",
            headers=auth_headers,
            json={
                "max_candidates_per_material": 50,
                "overwrite": False,
            },
        )

        assert batch_response.status_code == 200

        batch_data = batch_response.json()

        assert batch_data["status"] == "complete"
        assert batch_data["materials_processed"] == 2
        assert batch_data["candidate_pairs_evaluated"] == 1
        assert batch_data["new_candidates_stored"] == 1
        assert batch_data["total_candidates"] == 1

        candidates_response = client.get(
            "/api/matching/candidates",
            headers=auth_headers,
        )

        assert candidates_response.status_code == 200

        candidates_data = candidates_response.json()

        assert candidates_data["total"] == 1
        assert len(candidates_data["candidates"]) == 1

        candidate = candidates_data["candidates"][0]

        assert candidate["source_cpse"] == "NTPC"
        assert candidate["target_cpse"] == "BHEL"
        assert candidate["source_code"] == "NTPC-VALVE-001"
        assert candidate["target_code"] == "BHEL-VALVE-001"
        assert candidate["engine_decision"] in {
            "HIGH_CONFIDENCE",
            "REVIEW",
            "DIFFERENT",
        }
        if candidate["engine_decision"] in ("HIGH_CONFIDENCE", "REVIEW"):
            # Both still require human approval.
            assert candidate["review_status"] == "PENDING"
        else:
            assert candidate["review_status"] == "DIFFERENT"

    finally:
        store.reset_stores()
        MAPPINGS.clear()
        AUDIT_EVENTS.clear()


def test_review_approval_generates_mapping_and_audit_event(auth_headers):
    store.reset_stores()
    MAPPINGS.clear()
    AUDIT_EVENTS.clear()

    try:
        csv_content = """cpse,material_code,description,category,material_grade
NTPC,NTPC-VALVE-001,SS 304 GATE VALVE 2 IN,Valve,SS304
BHEL,BHEL-VALVE-001,GATE VALVE SS304 2 INCH,Valve,SS304
"""

        upload_response = client.post(
            "/api/materials/upload",
            headers=auth_headers,
            files={
                "file": (
                    "integration_test.csv",
                    csv_content,
                    "text/csv",
                )
            },
        )

        assert upload_response.status_code == 200
        assert upload_response.json()["records_ingested"] == 2

        batch_response = client.post(
            "/api/matching/run-batch",
            headers=auth_headers,
            json={"overwrite": False},
        )

        assert batch_response.status_code == 200
        assert batch_response.json()["new_candidates_stored"] == 1

        queue_response = client.get(
            "/api/review/queue",
            headers=auth_headers,
        )

        assert queue_response.status_code == 200

        queue_data = queue_response.json()
        assert queue_data["total_pending"] == 1
        assert len(queue_data["queue"]) == 1

        candidate = queue_data["queue"][0]
        candidate_id = candidate["id"]

        assert candidate["engine_decision"] == "REVIEW"
        assert candidate["review_status"] == "PENDING"

        review_response = client.post(
            f"/api/review/queue/{candidate_id}/action",
            headers=auth_headers,
            json={
                "action": "APPROVE",
                "reviewer_comments": "Approved for integration test.",
                "user_id": "integration-test-user",
            },
        )

        assert review_response.status_code == 200

        review_data = review_response.json()
        assert review_data["action_applied"] == "APPROVE"
        assert review_data["candidate"]["review_status"] == "APPROVED"
        assert review_data["candidate"]["reviewer_id"] in ("admin@mira.gov.in", "integration-test-user")

        mapping_response = client.post(
            "/api/mappings/generate",
            headers=auth_headers,
        )

        assert mapping_response.status_code == 200

        mapping_data = mapping_response.json()

        assert mapping_data["status"] == "success"
        assert mapping_data["mappings_created"] == 1
        assert mapping_data["total_mappings"] == 1

        mapping = mapping_data["mappings"][0]

        assert mapping["status"] == "PROVISIONAL"
        assert mapping["cluster_size"] == 2
        assert len(mapping["cpse_mappings"]) == 2

        audit_response = client.get(
            "/api/audit",
            headers=auth_headers,
        )

        assert audit_response.status_code == 200

        audit_data = audit_response.json()

        assert audit_data["total"] == 1

        event = audit_data["events"][0]

        assert event["event_type"] == "MATCH_APPROVED"
        assert event["candidate_id"] == candidate_id
        assert event["actor"] in ("admin@mira.gov.in", "integration-test-user")
        assert event["comments"] == "Approved for integration test."

    finally:
        store.reset_stores()
        MAPPINGS.clear()
        AUDIT_EVENTS.clear()


def test_run_batch_does_not_duplicate_existing_pairs(auth_headers):
    store.reset_stores()
    MAPPINGS.clear()
    AUDIT_EVENTS.clear()

    try:
        csv_content = """cpse,material_code,description,category,material_grade
NTPC,NTPC-VALVE-001,SS 304 GATE VALVE 2 IN 150 LB,Valve,SS304
BHEL,BHEL-VALVE-001,SS 304 GATE VALVE 2 IN 150 LB,Valve,SS304
"""

        upload_response = client.post(
            "/api/materials/upload",
            headers=auth_headers,
            files={
                "file": (
                    "integration_test.csv",
                    csv_content,
                    "text/csv",
                )
            },
        )

        assert upload_response.status_code == 200

        first_run = client.post(
            "/api/matching/run-batch",
            headers=auth_headers,
            json={"overwrite": False},
        )

        assert first_run.status_code == 200
        assert first_run.json()["new_candidates_stored"] == 1
        assert first_run.json()["total_candidates"] == 1

        second_run = client.post(
            "/api/matching/run-batch",
            headers=auth_headers,
            json={"overwrite": False},
        )

        assert second_run.status_code == 200
        assert second_run.json()["new_candidates_stored"] == 0
        assert second_run.json()["total_candidates"] == 1

    finally:
        store.reset_stores()
        MAPPINGS.clear()
        AUDIT_EVENTS.clear()


def test_run_batch_excludes_same_cpse_pairs(auth_headers):
    store.reset_stores()
    MAPPINGS.clear()
    AUDIT_EVENTS.clear()

    try:
        csv_content = """cpse,material_code,description,category,material_grade
NTPC,NTPC-E2E-003,SS 304 GATE VALVE 2 IN 150 LB,Valve,SS304
NTPC,NTPC-E2E-004,SS 304 GATE VALVE 2 IN 150 LB,Valve,SS304
BHEL,BHEL-E2E-003,SS 304 GATE VALVE 2 IN 150 LB,Valve,SS304
"""

        upload_response = client.post(
            "/api/materials/upload",
            headers=auth_headers,
            files={
                "file": (
                    "cross_cpse_test.csv",
                    csv_content,
                    "text/csv",
                )
            },
        )

        assert upload_response.status_code == 200
        assert upload_response.json()["records_ingested"] == 3

        batch_response = client.post(
            "/api/matching/run-batch",
            headers=auth_headers,
            json={"overwrite": False},
        )

        assert batch_response.status_code == 200

        batch_data = batch_response.json()

        assert batch_data["materials_processed"] == 3
        assert batch_data["candidate_pairs_evaluated"] == 2
        assert batch_data["new_candidates_stored"] == 2
        assert batch_data["total_candidates"] == 2

        candidates_response = client.get(
            "/api/matching/candidates",
            headers=auth_headers,
        )

        assert candidates_response.status_code == 200

        candidates = candidates_response.json()["candidates"]

        assert len(candidates) == 2

        for candidate in candidates:
            assert candidate["source_cpse"] != candidate["target_cpse"]

    finally:
        store.reset_stores()
        MAPPINGS.clear()
        AUDIT_EVENTS.clear()


def test_late_appended_bhel_material_participates_in_batch_matching(auth_headers):
    """
    Verify that a BHEL material appended after many NTPC materials is not starved
    by same-CPSE materials or high material IDs, and successfully generates candidates.
    """
    store.reset_stores()
    MAPPINGS.clear()
    AUDIT_EVENTS.clear()

    try:
        # Generate 60 generic NTPC materials + 1 matching NTPC dished end
        lines = ["cpse,material_code,description,category,material_grade"]
        for i in range(1, 61):
            lines.append(f"NTPC,NTPC-GEN-{i:03d},GENERIC UNRELATED ITEM TYPE {i},General,")
        lines.append("NTPC,NTPC-DISHED-01,DISHED END 2:1 ELLIP ID1700X25THK,General,")

        # 1 BHEL real material appended later
        lines.append("BHEL,HE9711823020,DISHED END 2:1 ELLIP ID1700X25THK(MIN),General,")

        upload_response = client.post(
            "/api/materials/upload",
            headers=auth_headers,
            files={"file": ("dataset.csv", "\n".join(lines), "text/csv")},
        )
        assert upload_response.status_code == 200
        assert upload_response.json()["records_ingested"] == 62

        batch_response = client.post(
            "/api/matching/run-batch",
            headers=auth_headers,
            json={"max_candidates_per_material": 50, "overwrite": True},
        )
        assert batch_response.status_code == 200
        data = batch_response.json()
        assert data["status"] == "complete"

        # Query candidates for HE9711823020
        cands_resp = client.get(
            "/api/matching/candidates?limit=100",
            headers=auth_headers,
        )
        assert cands_resp.status_code == 200
        all_cands = cands_resp.json()["candidates"]

        he_candidates = [
            c for c in all_cands
            if c["source_code"] == "HE9711823020" or c["target_code"] == "HE9711823020"
        ]
        assert len(he_candidates) >= 1, "HE9711823020 must participate in candidate generation"

        # The candidate with NTPC-DISHED-01 must be present
        dished_pair = [
            c for c in he_candidates
            if "NTPC-DISHED-01" in (c["source_code"], c["target_code"])
        ]
        assert len(dished_pair) == 1
        assert dished_pair[0]["engine_decision"] in {"HIGH_CONFIDENCE", "REVIEW"}

    finally:
        store.reset_stores()
        MAPPINGS.clear()
        AUDIT_EVENTS.clear()


def test_existing_test_pair_bolt_behavior(auth_headers):
    """
    Verify that the existing test pair:
      NTPC:TEST-001 (BOLT HEX M24 X 40 MM SS 304)
      BHEL:TEST-002 (HEX BOLT M24X40 SS304)
    generates a candidate evaluated as REVIEW with the expected score and safe gating.
    """
    store.reset_stores()
    MAPPINGS.clear()
    AUDIT_EVENTS.clear()

    try:
        csv_content = """cpse,material_code,description,category,material_grade
NTPC,TEST-001,BOLT HEX M24 X 40 MM SS 304,Fastener,SS304
BHEL,TEST-002,HEX BOLT M24X40 SS304,Fastener,SS304
"""
        upload_resp = client.post(
            "/api/materials/upload",
            headers=auth_headers,
            files={"file": ("bolt_test.csv", csv_content, "text/csv")},
        )
        assert upload_resp.status_code == 200

        batch_resp = client.post(
            "/api/matching/run-batch",
            headers=auth_headers,
            json={"overwrite": True},
        )
        assert batch_resp.status_code == 200

        cands_resp = client.get("/api/matching/candidates", headers=auth_headers)
        assert cands_resp.status_code == 200
        candidates = cands_resp.json()["candidates"]

        bolt_pair = [
            c for c in candidates
            if ("TEST-001" in (c["source_code"], c["target_code"])
                and "TEST-002" in (c["source_code"], c["target_code"]))
        ]
        assert len(bolt_pair) == 1
        cand = bolt_pair[0]
        assert cand["engine_decision"] in {"HIGH_CONFIDENCE", "REVIEW"}
        if cand["engine_decision"] in ("HIGH_CONFIDENCE", "REVIEW"):
            assert cand["review_status"] == "PENDING"
        assert cand["scores"]["final_score"] > 0.60
        assert isinstance(cand["critical_checks"], list)
        assert not any(c.get("status") == "CONFLICT" for c in cand["critical_checks"])

    finally:
        store.reset_stores()
        MAPPINGS.clear()
        AUDIT_EVENTS.clear()


def test_batch_matching_respects_max_candidates_per_material(auth_headers):
    """Verify that max_candidates_per_material cap is strictly respected per source."""
    store.reset_stores()
    MAPPINGS.clear()
    AUDIT_EVENTS.clear()

    try:
        lines = ["cpse,material_code,description,category,material_grade"]
        lines.append("BHEL,BHEL-SRC-1,GATE VALVE SS304 2 IN 150 LB,Valve,SS304")
        for i in range(1, 20):
            lines.append(f"NTPC,NTPC-TGT-{i},GATE VALVE SS304 2 IN 150 LB VARIANT {i},Valve,SS304")

        upload_resp = client.post(
            "/api/materials/upload",
            headers=auth_headers,
            files={"file": ("cap_test.csv", "\n".join(lines), "text/csv")},
        )
        assert upload_resp.status_code == 200

        # Cap at 5 with source_cpse BHEL
        batch_resp = client.post(
            "/api/matching/run-batch",
            headers=auth_headers,
            json={"max_candidates_per_material": 5, "source_cpse": "BHEL", "overwrite": True},
        )
        assert batch_resp.status_code == 200

        cands_resp = client.get("/api/matching/candidates?limit=100", headers=auth_headers)
        candidates = cands_resp.json()["candidates"]

        src_candidates = [
            c for c in candidates
            if c["source_code"] == "BHEL-SRC-1" or c["target_code"] == "BHEL-SRC-1"
        ]
        # BHEL-SRC-1 had 19 potential targets, but capped at 5
        assert len(src_candidates) <= 5
        assert len(src_candidates) == 5

    finally:
        store.reset_stores()
        MAPPINGS.clear()
        AUDIT_EVENTS.clear()