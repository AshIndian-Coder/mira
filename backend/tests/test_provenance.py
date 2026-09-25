"""
Tests for Provenance Resolution and Multi-Format Ingestion.
"""

import io
import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import store
from app.core.database import SessionLocal
from app.core.security import create_access_token, hash_password
from app.core.seed import seed_default_users_and_cpses
from app.models.user import User
from app.services.ingestion.parsers.excel_parser import parse_excel
from app.services.ingestion.provenance import (
    ProvenanceLevel,
    extract_cpse_from_code,
    extract_cpse_from_text,
    normalize_cpse_name,
    resolve_provenance,
)

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
    yield
    store.reset_stores()


def test_normalize_cpse_name():
    assert normalize_cpse_name("BHEL") == "BHEL"
    assert normalize_cpse_name("Bharat Heavy Electricals Limited") == "BHEL"
    assert normalize_cpse_name("Indian Oil Corporation") == "IOCL"
    assert normalize_cpse_name("national thermal power corporation") == "NTPC"
    assert normalize_cpse_name("Steel Authority of India") == "SAIL"
    assert normalize_cpse_name("UNKNOWN") is None
    assert normalize_cpse_name(None) is None


def test_extract_cpse_from_code():
    assert extract_cpse_from_code("BHEL-10023") == "BHEL"
    assert extract_cpse_from_code("IOCL_9921") == "IOCL"
    assert extract_cpse_from_code("PO661146780") == "POLYCAB"
    assert extract_cpse_from_code("YA758392401") == "YANTRAIN"
    assert extract_cpse_from_code("MC260744062") == "MCL"
    assert extract_cpse_from_code("SRF-FAS-314952") == "SRF"
    assert extract_cpse_from_code("RANDOM-999") is None


def test_extract_cpse_from_text():
    assert extract_cpse_from_text("bhel_procurement_data_2026.csv") == "BHEL"
    assert extract_cpse_from_text("ONGC Offshore Drilling Catalog.xlsx") == "ONGC"
    assert extract_cpse_from_text("Header: Indian Oil Corporation refinery items") == "IOCL"
    assert extract_cpse_from_text("plain_catalog.csv") is None


def test_provenance_hierarchy_levels():
    # 1. EXPLICIT_ROW
    res1 = resolve_provenance(row={"cpse": "BHEL", "material_code": "GEN-01"})
    assert res1.level == ProvenanceLevel.EXPLICIT_ROW
    assert res1.cpse == "BHEL"
    assert res1.confidence == 1.0
    assert not res1.conflict_detected

    # 2. SHEET_NAME
    res2 = resolve_provenance(row={"material_code": "GEN-01"}, sheet_name="IOCL_Master")
    assert res2.level == ProvenanceLevel.SHEET_NAME
    assert res2.cpse == "IOCL"
    assert res2.confidence == 0.95

    # 3. FILE_HEADER
    res3 = resolve_provenance(row={"material_code": "GEN-01"}, file_header="Source: NTPC Power Plant")
    assert res3.level == ProvenanceLevel.FILE_HEADER
    assert res3.cpse == "NTPC"
    assert res3.confidence == 0.90

    # 4. FILENAME_METADATA
    res4 = resolve_provenance(row={"material_code": "GEN-01"}, filename="SAIL_Raw_Materials.csv")
    assert res4.level == ProvenanceLevel.FILENAME_METADATA
    assert res4.cpse == "SAIL"
    assert res4.confidence == 0.85

    # 5. OBSERVED_CODE_PATTERN
    res5 = resolve_provenance(row={"material_code": "PO661146780"})
    assert res5.level == ProvenanceLevel.OBSERVED_CODE_PATTERN
    assert res5.cpse == "POLYCAB"
    assert res5.confidence == 0.80

    # 6. UNKNOWN fallback
    res6 = resolve_provenance(row={"material_code": "GEN-01", "description": "Steel Nut"})
    assert res6.level == ProvenanceLevel.UNKNOWN
    assert res6.cpse == "UNKNOWN"
    assert res6.confidence == 0.0


def test_provenance_conflict_detection():
    # Row explicitly says BHEL, but filename says IOCL
    res = resolve_provenance(
        row={"cpse": "BHEL", "material_code": "GEN-01"},
        filename="IOCL_Materials_2026.csv",
    )
    assert res.cpse == "BHEL"  # Primary is explicit row
    assert res.confidence == 1.0
    assert res.conflict_detected is True
    assert res.requires_review is True
    assert len(res.conflicting_evidence) == 1
    assert res.conflicting_evidence[0]["cpse"] == "IOCL"


def test_multi_sheet_excel_provenance():
    wb = openpyxl.Workbook()
    # Sheet 1: BHEL
    ws1 = wb.active
    ws1.title = "BHEL_Items"
    ws1.append(["material_code", "description", "unit"])
    ws1.append(["BH-001", "Gate Valve 2 IN 150 LB", "NOS"])

    # Sheet 2: IOCL
    ws2 = wb.create_sheet(title="IOCL_Items")
    ws2.append(["material_code", "description", "unit"])
    ws2.append(["IO-002", "Seamless Pipe 50 NB SS316", "MTR"])

    buf = io.BytesIO()
    wb.save(buf)
    content = buf.getvalue()

    records = parse_excel(content, filename="jumbled_master.xlsx")
    assert len(records) == 2

    # Check that sheet names are preserved
    assert records[0]["_sheet_name"] == "BHEL_Items"
    assert records[1]["_sheet_name"] == "IOCL_Items"

    # Test resolution
    prov0 = resolve_provenance(records[0], sheet_name=records[0]["_sheet_name"])
    prov1 = resolve_provenance(records[1], sheet_name=records[1]["_sheet_name"])

    assert prov0.cpse == "BHEL"
    assert prov0.level == ProvenanceLevel.SHEET_NAME
    assert prov1.cpse == "IOCL"
    assert prov1.level == ProvenanceLevel.SHEET_NAME


def test_materials_upload_with_provenance():
    csv_content = (
        "material_code,description,unit,source_org\n"
        "VAL-101,SS304 Gate Valve 2 IN 150 LB,NOS,Bharat Heavy Electricals\n"
        "PIP-202,Seamless Pipe 50 NB SS316,MTR,\n"
    )
    response = client.post(
        "/api/materials/upload",
        files={"file": ("ONGC_inventory.csv", csv_content.encode("utf-8"), "text/csv")},
        headers=auth_header(),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["records_ingested"] == 2

    # First record had explicit source_org "Bharat Heavy Electricals" -> BHEL (with conflict against ONGC filename)
    rec1 = data["sample"][0]
    assert rec1["cpse"] == "BHEL"
    assert rec1["provenance_level"] == "EXPLICIT_ROW"
    assert rec1["provenance_conflict"] is True
    assert rec1["requires_review"] is True

    # Second record had no explicit cpse, so resolved from filename ONGC_inventory.csv -> ONGC
    rec2 = data["sample"][1]
    assert rec2["cpse"] == "ONGC"
    assert rec2["provenance_level"] == "FILENAME_METADATA"
    assert rec2["provenance_confidence"] == 0.85
    assert rec2["provenance_conflict"] is False
