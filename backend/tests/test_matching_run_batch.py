from fastapi.testclient import TestClient

from app.main import app
from app import store
from app.api.routes.mappings import MAPPINGS
from app.api.routes.audit import AUDIT_EVENTS


client = TestClient(app)


def test_run_batch_generates_and_persists_candidate():
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

        candidates_response = client.get("/api/matching/candidates")

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
        assert candidate["review_status"] in {
            "PENDING",
            "HIGH_CONFIDENCE",
            "DIFFERENT",
        }

    finally:
        store.reset_stores()
        MAPPINGS.clear()
        AUDIT_EVENTS.clear()


def test_review_approval_generates_mapping_and_audit_event():
    store.reset_stores()
    MAPPINGS.clear()
    AUDIT_EVENTS.clear()

    try:
        csv_content = """cpse,material_code,description,category,material_grade
NTPC,NTPC-VALVE-001,SS 304 GATE VALVE 2 IN 150 LB,Valve,SS304
BHEL,BHEL-VALVE-001,SS 304 GATE VALVE 2 IN 300 LB,Valve,SS304
"""

        upload_response = client.post(
            "/api/materials/upload",
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
            json={"overwrite": False},
        )

        assert batch_response.status_code == 200
        assert batch_response.json()["new_candidates_stored"] == 1

        queue_response = client.get("/api/review/queue")

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
        assert review_data["candidate"]["reviewer_id"] == "integration-test-user"

        mapping_response = client.post("/api/mappings/generate")

        assert mapping_response.status_code == 200

        mapping_data = mapping_response.json()

        assert mapping_data["status"] == "success"
        assert mapping_data["mappings_created"] == 1
        assert mapping_data["total_mappings"] == 1

        mapping = mapping_data["mappings"][0]

        assert mapping["status"] == "PROVISIONAL"
        assert mapping["cluster_size"] == 2
        assert len(mapping["cpse_mappings"]) == 2

        audit_response = client.get("/api/audit")

        assert audit_response.status_code == 200

        audit_data = audit_response.json()

        assert audit_data["total"] == 1

        event = audit_data["events"][0]

        assert event["event_type"] == "MATCH_APPROVED"
        assert event["candidate_id"] == candidate_id
        assert event["actor"] == "integration-test-user"
        assert event["comments"] == "Approved for integration test."

    finally:
        store.reset_stores()
        MAPPINGS.clear()
        AUDIT_EVENTS.clear()


def test_run_batch_does_not_duplicate_existing_pairs():
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
            json={"overwrite": False},
        )

        assert first_run.status_code == 200
        assert first_run.json()["new_candidates_stored"] == 1
        assert first_run.json()["total_candidates"] == 1

        second_run = client.post(
            "/api/matching/run-batch",
            json={"overwrite": False},
        )

        assert second_run.status_code == 200
        assert second_run.json()["new_candidates_stored"] == 0
        assert second_run.json()["total_candidates"] == 1

    finally:
        store.reset_stores()
        MAPPINGS.clear()
        AUDIT_EVENTS.clear()


def test_run_batch_excludes_same_cpse_pairs():
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
            json={"overwrite": False},
        )

        assert batch_response.status_code == 200

        batch_data = batch_response.json()

        assert batch_data["materials_processed"] == 3
        assert batch_data["candidate_pairs_evaluated"] == 2
        assert batch_data["new_candidates_stored"] == 2
        assert batch_data["total_candidates"] == 2

        candidates_response = client.get("/api/matching/candidates")

        assert candidates_response.status_code == 200

        candidates = candidates_response.json()["candidates"]

        assert len(candidates) == 2

        for candidate in candidates:
            assert candidate["source_cpse"] != candidate["target_cpse"]

    finally:
        store.reset_stores()
        MAPPINGS.clear()
        AUDIT_EVENTS.clear()
