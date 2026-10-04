import csv
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app import store
from app.api.v1.audit import AUDIT_EVENTS
from app.api.v1.mappings import MAPPINGS
from app.core.seed import seed_default_users_and_cpses
from app.main import app
from app.services.matching.classifier import classify_match
from app.services.normalization.service import normalize_material_description
from app.services.parsing.service import parse_specifications

client = TestClient(app)


def auth_header(email: str = "admin@mira.gov.in", password: str = "Admin@123") -> dict[str, str]:
    seed_default_users_and_cpses()
    login_resp = client.post("/api/auth/login", json={"email": email, "password": password})
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def load_synthetic_dataset() -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    root = Path(__file__).parent.parent.parent
    csv_path = root / "data" / "sample" / "synthetic_material_master.csv"
    manifest_path = root / "data" / "sample" / "synthetic_material_master_manifest.json"

    materials: dict[str, dict[str, Any]] = {}
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row["material_code"]
            desc = row["description"]
            norm_desc = normalize_material_description(desc)
            parsed = parse_specifications(desc)
            dim = row.get("dimensions") or parsed.get("dimensions")
            materials[code] = {
                "material_code": code,
                "cpse": row["cpse"],
                "description": desc,
                "normalized_description": norm_desc,
                "category": row["category"],
                "material_grade": row.get("material_grade") or parsed.get("material_grade"),
                "parsed_specifications": parsed,
                "dimensions": dim,
                "other_attributes": {},
            }

    manifest = []
    if manifest_path.exists():
        with open(manifest_path, mode="r", encoding="utf-8") as f:
            manifest_data = json.load(f)
            manifest = manifest_data.get("manifest", [])

    return materials, manifest


def test_synthetic_fasteners_obvious_equivalents():
    """Obvious equivalent fasteners with all gates passing and score >= threshold -> HIGH_CONFIDENCE."""
    m_a = {
        "category": "Fastener",
        "description": "HEX HEAD BOLT M8 X 25 MM SS304",
        "normalized_description": "HEX HEAD BOLT M8 X 25 MM SS304",
        "material_grade": "SS304",
        "parsed_specifications": {
            "thread_size": "M8",
            "thread_pitch": None,
            "bolt_length": {"value": 25.0, "unit": "MM"},
            "dimensions": "M8X25MM",
            "material_grade": "SS304",
        },
        "other_attributes": {},
    }
    m_b = {
        "category": "Fastener",
        "description": "HEX HEAD BOLT M8 X 25 MM SS 304",
        "normalized_description": "HEX HEAD BOLT M8 X 25 MM SS 304",
        "material_grade": "SS304",
        "parsed_specifications": {
            "thread_size": "M8",
            "thread_pitch": None,
            "bolt_length": {"value": 25.0, "unit": "MM"},
            "dimensions": "M8X25MM",
            "material_grade": "SS304",
        },
        "other_attributes": {},
    }
    res = classify_match(m_a, m_b)
    assert res["decision"] == "HIGH_CONFIDENCE"
    assert all(c["status"] == "PASS" for c in res["critical_checks"])


def test_synthetic_fasteners_moderate_score_requires_review():
    """Fasteners with all gates passing but with variations in phrasing -> REVIEW."""
    materials, _ = load_synthetic_dataset()
    m1 = materials["NTP-FST-0825"]  # NTPC HEX HEAD BOLT M8 X 25 MM SS304 GRADE A2-70
    m2 = materials["BHL-FST-8025"]  # BHEL HEXAGONAL HEAD BOLT SS 304 M8X25MM

    res1 = classify_match(m1, m2)
    assert all(c["status"] == "PASS" for c in res1["critical_checks"])
    assert res1["decision"] == "REVIEW"


def test_synthetic_bolt_dimension_conflicts():
    """Bolt dimension conflicts (M8x25 vs M8x30 vs M8x40) -> DIFFERENT."""
    materials, _ = load_synthetic_dataset()
    m_25 = materials["NTP-FST-0825"]
    m_30 = materials["NTP-FST-0830"]
    m_40 = materials["BHL-FST-0840"]

    res_25_30 = classify_match(m_25, m_30)
    assert res_25_30["decision"] == "DIFFERENT"
    assert any(c["field"] == "dimensions" and c["status"] == "CONFLICT" for c in res_25_30["critical_checks"])

    res_25_40 = classify_match(m_25, m_40)
    assert res_25_40["decision"] == "DIFFERENT"
    assert any(c["field"] == "dimensions" and c["status"] == "CONFLICT" for c in res_25_40["critical_checks"])


def test_synthetic_valve_pressure_rating_conflicts():
    """Valve pressure rating conflicts (150 LB vs 300 LB vs 600 LB) -> DIFFERENT."""
    materials, _ = load_synthetic_dataset()
    m_150 = materials["IOC-VLV-0215"]   # 150 LB
    m_300 = materials["IOC-VLV-0230"]   # 300 LB
    m_600 = materials["ONG-VLV-0260"]   # 600 LB

    res_150_300 = classify_match(m_150, m_300)
    assert res_150_300["decision"] == "DIFFERENT"
    assert any(c["field"] == "pressure_rating" and c["status"] == "CONFLICT" for c in res_150_300["critical_checks"])

    res_150_600 = classify_match(m_150, m_600)
    assert res_150_600["decision"] == "DIFFERENT"
    assert any(c["field"] == "pressure_rating" and c["status"] == "CONFLICT" for c in res_150_600["critical_checks"])


def test_synthetic_missing_critical_specifications_requires_review():
    """Ambiguous items with missing critical specifications (UNKNOWN) -> REVIEW."""
    materials, _ = load_synthetic_dataset()
    m_amb = materials["IOC-AMB-F01"]    # HEX HEAD BOLT SS304 (no dimensions)
    m_full = materials["NTP-FST-0825"]  # full M8x25 bolt

    res = classify_match(m_amb, m_full)
    assert res["decision"] == "REVIEW"
    assert any(c["status"] == "UNKNOWN" for c in res["critical_checks"])


def test_pipeline_end_to_end_synthetic_dataset_automation_and_governance():
    """
    Complete end-to-end pipeline validation on synthetic material master:
    1. Ingestion of 172 multi-CPSE materials
    2. Batch matching producing PENDING (HIGH_CONFIDENCE + REVIEW) and DIFFERENT states
    3. Review queue containing ALL engine-flagged items -- no auto-approval
    4. Human approval required before mapping generation
    5. Audit trail verifying the human MATCH_APPROVED emission
    """
    store.reset_stores()
    MAPPINGS.clear()
    AUDIT_EVENTS.clear()

    headers = auth_header("admin@mira.gov.in", "Admin@123")
    csv_path = Path(__file__).parent.parent.parent / "data" / "sample" / "synthetic_material_master.csv"

    try:
        # 1. Ingest
        with open(csv_path, "rb") as f:
            up_resp = client.post(
                "/api/materials/upload",
                headers=headers,
                files={"file": ("synthetic_material_master.csv", f, "text/csv")},
            )
        assert up_resp.status_code == 200
        assert up_resp.json()["records_ingested"] == 172

        # 2. Batch Match
        batch_resp = client.post("/api/matching/run-batch", headers=headers, json={"overwrite": True})
        assert batch_resp.status_code == 200
        assert batch_resp.json()["status"] == "complete"

        # The engine must never auto-approve anything.
        auto_approved = [c for c in store.CANDIDATES if c["review_status"] == "AUTO_APPROVED"]
        assert auto_approved == []

        high_conf = [c for c in store.CANDIDATES if c["engine_decision"] == "HIGH_CONFIDENCE"]
        pending = [c for c in store.CANDIDATES if c["review_status"] == "PENDING"]
        different = [c for c in store.CANDIDATES if c["review_status"] == "DIFFERENT"]

        assert len(high_conf) > 0
        assert len(pending) > 0
        assert len(different) > 0

        # Every engine-flagged candidate is PENDING and untouched by any reviewer.
        for c in store.CANDIDATES:
            if c["engine_decision"] in ("HIGH_CONFIDENCE", "REVIEW"):
                assert c["review_status"] == "PENDING"
                assert c["reviewer_id"] is None
                assert c["reviewed_at"] is None

        # High-confidence candidates have no critical conflict.
        for c in high_conf:
            assert not any(chk.get("status") == "CONFLICT" for chk in c["critical_checks"])

        # All DIFFERENT candidates are engine-DIFFERENT and excluded from review.
        for c in different:
            assert c["engine_decision"] == "DIFFERENT"

        # 3. Review queue surfaces BOTH decisions
        queue_resp = client.get("/api/review/queue", headers=headers)
        assert queue_resp.status_code == 200
        queue_data = queue_resp.json()
        assert queue_data["total_pending"] == len(pending)
        for item in queue_data["queue"]:
            assert item["engine_decision"] in ("HIGH_CONFIDENCE", "REVIEW")
            assert item["review_status"] == "PENDING"

        # 3b. High-confidence items are ordered first
        if any(i["engine_decision"] == "HIGH_CONFIDENCE" for i in queue_data["queue"]):
            assert queue_data["queue"][0]["engine_decision"] == "HIGH_CONFIDENCE"

        # 4. Mapping generation refuses to run with zero human approvals
        blocked = client.post("/api/mappings/generate", headers=headers)
        assert blocked.status_code == 200
        assert blocked.json()["status"] == "no_approved_candidates"
        assert blocked.json()["mappings_created"] == 0

        # 4b. A human approves one candidate -- then mappings can be generated
        approve_target = queue_data["queue"][0]["id"]
        action_resp = client.post(
            f"/api/review/queue/{approve_target}/action",
            headers=headers,
            json={"action": "APPROVE", "reviewer_comments": "E2E human approval"},
        )
        assert action_resp.status_code == 200
        assert action_resp.json()["candidate"]["review_status"] == "APPROVED"

        mapping_resp = client.post("/api/mappings/generate", headers=headers)
        assert mapping_resp.status_code == 200
        mapping_data = mapping_resp.json()
        assert mapping_data["status"] == "success"
        assert mapping_data["mappings_created"] > 0
        assert len(MAPPINGS) == mapping_data["mappings_created"]

        # 5. Audit trail is written by the HUMAN, not by "system:engine"
        approved_events = [e for e in AUDIT_EVENTS if e["event_type"] == "MATCH_APPROVED"]
        assert len(approved_events) >= 1
        assert all(e["actor"] == "admin@mira.gov.in" for e in approved_events)
        assert not [e for e in AUDIT_EVENTS if e["event_type"] == "MATCH_AUTO_APPROVED"]

    finally:
        store.reset_stores()
        MAPPINGS.clear()
        AUDIT_EVENTS.clear()


def test_mapping_generation_strictly_excludes_pending_and_different():
    """Verify that mapping generation rejects PENDING and DIFFERENT candidate pairs."""
    store.reset_stores()
    MAPPINGS.clear()
    AUDIT_EVENTS.clear()

    headers = auth_header("admin@mira.gov.in", "Admin@123")

    try:
        # Add test materials
        store.MATERIALS.extend([
            {"id": 1, "cpse": "IOCL", "material_code": "IOC-01", "description": "GATE VALVE 150 LB", "category": "Valve"},
            {"id": 2, "cpse": "BHEL", "material_code": "BHL-01", "description": "GATE VALVE 300 LB", "category": "Valve"},
            {"id": 3, "cpse": "NTPC", "material_code": "NTP-01", "description": "GATE VALVE 150 LB", "category": "Valve"},
            {"id": 4, "cpse": "BHEL", "material_code": "BHL-02", "description": "GATE VALVE 150 LB", "category": "Valve"},
        ])

        # Add only a DIFFERENT candidate and a PENDING candidate.
        #
        # NOTE: the persistent store maps onto the match_suggestions table,
        # which enforces UNIQUE (source_material_id, target_material_id)
        # ("unique_material_pair"). Each candidate therefore needs its own
        # material pair -- reusing (1, 2) for both is rejected by the DB.
        store.CANDIDATES.extend([
            {
                "id": 1,
                "source_material_id": 1,
                "target_material_id": 2,
                "source_cpse": "IOCL",
                "target_cpse": "BHEL",
                "source_code": "IOC-01",
                "target_code": "BHL-01",
                "source_description": "GATE VALVE 150 LB",
                "target_description": "GATE VALVE 300 LB",
                "scores": {"final_score": 0.40},
                "critical_checks": [{"field": "pressure_rating", "status": "CONFLICT"}],
                "engine_decision": "DIFFERENT",
                "review_status": "DIFFERENT",
            },
            {
                "id": 2,
                "source_material_id": 3,
                "target_material_id": 4,
                "source_cpse": "NTPC",
                "target_cpse": "BHEL",
                "source_code": "NTP-01",
                "target_code": "BHL-02",
                "source_description": "GATE VALVE",
                "target_description": "GATE VALVE",
                "scores": {"final_score": 0.70},
                "critical_checks": [{"field": "pressure_rating", "status": "UNKNOWN"}],
                "engine_decision": "REVIEW",
                "review_status": "PENDING",
            },
        ])

        mapping_resp = client.post("/api/mappings/generate", headers=headers)
        assert mapping_resp.status_code == 200
        assert mapping_resp.json()["status"] == "no_approved_candidates"
        assert mapping_resp.json()["mappings_created"] == 0

    finally:
        store.reset_stores()
        MAPPINGS.clear()
        AUDIT_EVENTS.clear()