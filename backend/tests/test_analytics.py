import pytest
from fastapi.testclient import TestClient

from app import store
from app.core.seed import seed_default_users_and_cpses
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_stores():
    store.reset_stores()
    yield
    store.reset_stores()


@pytest.fixture
def auth_headers():
    seed_default_users_and_cpses()
    resp = client.post(
        "/api/auth/login",
        json={"email": "admin@mira.gov.in", "password": "Admin@123"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_analytics_overview_empty(auth_headers):
    resp = client.get("/api/analytics/overview", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_materials"] == 0
    assert data["cpse_count"] == 0


def test_analytics_data_quality_metrics(auth_headers):
    # Ingest 3 mock materials with varied completeness
    store.MATERIALS.extend([
        {
            "id": 1,
            "cpse": "IOCL",
            "material_code": "MAT-001",
            "description": "GATE VALVE CS 150 LB 2 IN",
            "normalized_description": "GATE VALVE CS 150 LB 2 IN",
            "category": "Valve",
            "material_grade": "CS",
            "parsed_specifications": {
                "material_grade": "CS",
                "pressure_rating": {"value": 150.0, "unit": "LB"},
                "dimensions": {"value": 2.0, "unit": "IN"},
            },
        },
        {
            "id": 2,
            "cpse": "BHEL",
            "material_code": "MAT-002",
            "description": "UNSPECIFIED GENERAL ITEM",
            "normalized_description": "UNSPECIFIED GENERAL ITEM",
            "category": "General",
            "material_grade": None,
            "parsed_specifications": {},
        },
        {
            "id": 3,
            "cpse": "IOCL",
            "material_code": "MAT-003",
            "description": "SEAMLESS PIPE 4 IN SCH 40",
            "normalized_description": "SEAMLESS PIPE 4 IN SCH 40",
            "category": "Pipe",
            "material_grade": None,
            "parsed_specifications": {
                "dimensions": {"value": 4.0, "unit": "IN"},
                "schedule": "40",
            },
        },
    ])

    resp = client.get("/api/analytics/data-quality", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_materials"] == 3
    assert data["with_parsed_specs"] == 2
    assert data["parsing_failures"] == 1
    assert data["missing_description"] == 0
    assert data["missing_category"] == 1  # "General" category flagged as missing specific category
    assert data["missing_material_grade"] == 2  # MAT-002 and MAT-003 missing grade
    assert data["missing_dimensions"] == 1  # MAT-002 missing dimensions
    assert data["missing_pressure_rating"] == 2  # MAT-002 and MAT-003 missing pressure rating

    # Verify per-CPSE quality breakdown
    by_cpse = {row["cpse"]: row for row in data["by_cpse_quality"]}
    assert "IOCL" in by_cpse
    assert by_cpse["IOCL"]["total_materials"] == 2
    assert by_cpse["IOCL"]["with_parsed_specs"] == 2
    assert "BHEL" in by_cpse
    assert by_cpse["BHEL"]["total_materials"] == 1
    assert by_cpse["BHEL"]["with_parsed_specs"] == 0
