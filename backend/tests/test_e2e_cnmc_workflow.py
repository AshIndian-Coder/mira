import pytest
from fastapi.testclient import TestClient

from app import store
from app.api.v1.audit import AUDIT_EVENTS
from app.api.v1.mappings import MAPPINGS
from app.core.seed import seed_default_users_and_cpses
from app.main import app

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



def test_e2e_cross_cpse_cnmc_workflow(auth_headers):
    """
    End-to-End workflow validation:
    1. Upload:
       - IOCL: E2E-IOCL-001, GATE VALVE CS 150 NB 80 SCH 40
       - BHEL: E2E-BHEL-001, GATE VALVE CS 150 NB 80 SCH 40
    2. Normalize & parse
    3. Run batch candidate matching
    4. Review queue inspection & human approval
    5. CMR synthesis & CNMC generation
    6. Verify CNMC format: MIRA-VLV-17-<GLOBAL_ID>
    7. Verify both IOCL and BHEL map to the same CNMC
    8. Verify audit trail and flat export
    """
    store.reset_stores()
    MAPPINGS.clear()
    AUDIT_EVENTS.clear()

    try:
        csv_content = """cpse,material_code,description,category,material_grade
IOCL,E2E-IOCL-001,GATE VALVE CS 150 NB 80 SCH 40,Valve,CS
BHEL,E2E-BHEL-001,GATE VALVE CS 150 NB 80 SCH 40,Valve,CS
"""

        # 1. Upload materials
        upload_res = client.post(
            "/api/materials/upload",
            headers=auth_headers,
            files={"file": ("e2e_test.csv", csv_content, "text/csv")},
        )
        assert upload_res.status_code == 200
        assert upload_res.json()["records_ingested"] == 2

        # 2. Run batch matching
        match_res = client.post(
            "/api/matching/run-batch",
            headers=auth_headers,
            json={"overwrite": False},
        )
        assert match_res.status_code == 200
        assert match_res.json()["new_candidates_stored"] >= 1

        # 3. Retrieve review queue item
        queue_res = client.get("/api/review/queue", headers=auth_headers)
        assert queue_res.status_code == 200
        queue_data = queue_res.json()
        assert queue_data["total_pending"] == 1

        candidate = queue_data["queue"][0]
        candidate_id = candidate["id"]

        # 4. Human approval
        action_res = client.post(
            f"/api/review/queue/{candidate_id}/action",
            headers=auth_headers,
            json={
                "action": "APPROVE",
                "reviewer_comments": "Approved identical cross-CPSE valve specification.",
                "user_id": "chief-reviewer",
            },
        )
        assert action_res.status_code == 200
        assert action_res.json()["candidate"]["review_status"] == "APPROVED"

        # 5. Generate mappings and CNMC
        mapping_res = client.post(
            "/api/mappings/generate",
            headers=auth_headers,
        )
        assert mapping_res.status_code == 200
        mapping_data = mapping_res.json()
        assert mapping_data["status"] == "success"
        assert mapping_data["mappings_created"] == 1

        mapping = mapping_data["mappings"][0]
        cnmc_code = mapping["nmc"]

        # 6. Verify CNMC format: MIRA-VLV-17-<GLOBAL_ID>
        assert cnmc_code.startswith("MIRA-VLV-17-")
        global_id_str = cnmc_code.split("-")[-1]
        assert global_id_str.isdigit()
        assert not global_id_str.startswith("0")  # No fixed-width zero padding

        # 7. Verify both CPSE codes map to the same CNMC
        cpse_codes = {entry["material_code"]: entry["cpse"] for entry in mapping["cpse_mappings"]}
        assert "E2E-IOCL-001" in cpse_codes
        assert "E2E-BHEL-001" in cpse_codes
        assert cpse_codes["E2E-IOCL-001"] == "IOCL"
        assert cpse_codes["E2E-BHEL-001"] == "BHEL"

        # 8. Verify audit log
        audit_res = client.get("/api/audit", headers=auth_headers)
        assert audit_res.status_code == 200
        audit_events = audit_res.json()["events"]
        assert any(e["event_type"] == "MATCH_APPROVED" and e["candidate_id"] == candidate_id for e in audit_events)

        # 9. Verify Flat ERP Export
        export_res = client.get("/api/mappings/export/flat", headers=auth_headers)
        assert export_res.status_code == 200
        export_rows = export_res.json()["rows"]
        assert len(export_rows) == 2

        for row in export_rows:
            assert row["nmc"] == cnmc_code
            assert row["cpse_material_code"] in ("E2E-IOCL-001", "E2E-BHEL-001")

    finally:
        store.reset_stores()
        MAPPINGS.clear()
        AUDIT_EVENTS.clear()
