import pytest
from fastapi.testclient import TestClient

from app import store
from app.api.v1.audit import AUDIT_EVENTS
from app.api.v1.mappings import MAPPINGS
from app.core.seed import seed_default_users_and_cpses
from app.main import app

client = TestClient(app)


@pytest.fixture
def test_setup():
    seed_default_users_and_cpses()
    store.reset_stores()
    MAPPINGS.clear()
    AUDIT_EVENTS.clear()

    # Logins
    def login(email, password):
        resp = client.post("/api/auth/login", json={"email": email, "password": password})
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}

    headers = {
        "admin": login("admin@mira.gov.in", "Admin@123"),
        "steward": login("steward@mira.gov.in", "Steward@123"),
        "reviewer": login("reviewer@mira.gov.in", "Reviewer@123"),
        "auditor": login("auditor@mira.gov.in", "Auditor@123"),
    }

    yield headers

    store.reset_stores()
    MAPPINGS.clear()
    AUDIT_EVENTS.clear()


def test_mapping_approval_lifecycle_full(test_setup):
    headers = test_setup

    # 1. Create a provisional mapping
    mapping_record = {
        "id": 101,
        "nmc": "MIRA-VLV-17-101",
        "cpse_mappings": [
            {
                "material_id": 1,
                "cpse": "IOCL",
                "material_code": "IOCL-VALVE-01",
                "description": "GATE VALVE CS 150 LB",
                "category": "Valve",
                "material_grade": "CS",
            },
            {
                "material_id": 2,
                "cpse": "BHEL",
                "material_code": "BHEL-VALVE-01",
                "description": "GATE VALVE CS 150 LB",
                "category": "Valve",
                "material_grade": "CS",
            },
        ],
        "cluster_size": 2,
        "status": "PROVISIONAL",
        "common_material_record": {
            "canonical_description": "GATE VALVE CS 150 LB",
            "category": "Valve",
            "canonical_technical_attributes": {
                "material_grade": "CS",
                "pressure_rating": {"value": 150.0, "unit": "LB"},
            },
            "source_materials": [
                {"material_id": 1, "cpse": "IOCL", "material_code": "IOCL-VALVE-01"},
                {"material_id": 2, "cpse": "BHEL", "material_code": "BHEL-VALVE-01"},
            ],
            "provenance": {"source_count": 2, "material_ids": [1, 2]},
            "approval_status": "PROVISIONAL",
            "critical_unknown_fields": [],
        },
        "created_at": "2026-09-27T00:00:00Z",
    }
    MAPPINGS.append(mapping_record)

    # 2. Non-existent mapping returns 404
    missing_resp = client.post("/api/mappings/99999/approve", headers=headers["steward"])
    assert missing_resp.status_code == 404
    assert "not found" in missing_resp.json()["detail"]

    # 3. Reviewer cannot approve mapping (403 Forbidden)
    rev_resp = client.post("/api/mappings/101/approve", headers=headers["reviewer"])
    assert rev_resp.status_code == 403
    assert "not authorized" in rev_resp.json()["detail"]

    # 4. Auditor cannot approve mapping (403 Forbidden)
    aud_resp = client.post("/api/mappings/101/approve", headers=headers["auditor"])
    assert aud_resp.status_code == 403
    assert "not authorized" in aud_resp.json()["detail"]

    # 5. Data Steward approves mapping (200 OK)
    approve_resp = client.post("/api/mappings/101/approve", headers=headers["steward"])
    assert approve_resp.status_code == 200
    data = approve_resp.json()
    assert data["status"] == "success"
    assert data["mapping"]["status"] == "APPROVED"
    assert data["mapping"]["common_material_record"]["approval_status"] == "APPROVED"

    # 6. Verify MAPPINGS store updated
    persisted = next(m for m in MAPPINGS if m["id"] == 101)
    assert persisted["status"] == "APPROVED"
    assert persisted["common_material_record"]["approval_status"] == "APPROVED"

    # 7. Verify audit log event
    audit_events = [e for e in AUDIT_EVENTS if e["event_type"] == "MAPPING_APPROVED"]
    assert len(audit_events) == 1
    event = audit_events[0]
    assert event["event_type"] == "MAPPING_APPROVED"
    assert event["source_code"] == "MIRA-VLV-17-101"
    assert event["target_code"] == "MIRA-VLV-17-101"
    assert event["actor"] == "steward@mira.gov.in"
    assert "101" in event["comments"]

    # 8. Repeated approval is idempotent and safe
    repeat_resp = client.post("/api/mappings/101/approve", headers=headers["steward"])
    assert repeat_resp.status_code == 200
    repeat_data = repeat_resp.json()
    assert repeat_data["status"] == "already_approved"
    assert repeat_data["mapping"]["status"] == "APPROVED"
    # No duplicate audit log
    assert len([e for e in AUDIT_EVENTS if e["event_type"] == "MAPPING_APPROVED"]) == 1

    # 9. Admin can also approve a newly created provisional mapping
    mapping_record_2 = {
        "id": 102,
        "nmc": "MIRA-PMP-01-102",
        "cpse_mappings": [],
        "cluster_size": 1,
        "status": "PROVISIONAL",
        "common_material_record": {"approval_status": "PROVISIONAL"},
        "created_at": "2026-09-27T00:00:00Z",
    }
    MAPPINGS.append(mapping_record_2)

    admin_resp = client.post("/api/mappings/102/approve", headers=headers["admin"])
    assert admin_resp.status_code == 200
    assert admin_resp.json()["mapping"]["status"] == "APPROVED"
    assert admin_resp.json()["mapping"]["common_material_record"]["approval_status"] == "APPROVED"
    admin_audit = [e for e in AUDIT_EVENTS if e["source_code"] == "MIRA-PMP-01-102"]
    assert len(admin_audit) == 1
    assert admin_audit[0]["actor"] == "admin@mira.gov.in"
