from app.services.harmonization.service import UNKNOWN
from app.services.harmonization.service import build_common_material_record


def make_material(
    material_id,
    cpse,
    material_code,
    description,
    *,
    normalized_description,
    category="Valve",
    material_grade="SS304",
    dimensions=None,
    parsed_specifications=None,
):
    return {
        "id": material_id,
        "cpse": cpse,
        "material_code": material_code,
        "description": description,
        "normalized_description": normalized_description,
        "category": category,
        "material_grade": material_grade,
        "dimensions": dimensions,
        "parsed_specifications": parsed_specifications or {},
        "specifications": {},
        "source_file": f"{cpse}.csv",
        "source_page": 1,
    }


def test_approved_cluster_can_become_common_material_record():
    materials = [
        make_material(
            1,
            "NTPC",
            "NTPC-001",
            "SS 304 GATE VALVE 2 IN 150 LB",
            normalized_description="SS 304 GATE VALVE 2 IN 150 LB",
            dimensions={"value": 2.0, "unit": "IN"},
            parsed_specifications={
                "material_grade": "SS304",
                "dimensions": {"value": 2.0, "unit": "IN"},
                "pressure_rating": {"value": 150.0, "unit": "LB"},
            },
        ),
        make_material(
            2,
            "BHEL",
            "BHEL-001",
            "SS304 GATE VALVE 2 IN 150 LB",
            normalized_description="SS 304 GATE VALVE 2 IN 150 LB",
            dimensions={"value": 2.0, "unit": "IN"},
            parsed_specifications={
                "material_grade": "SS304",
                "dimensions": {"value": 2.0, "unit": "IN"},
                "pressure_rating": {"value": 150.0, "unit": "LB"},
            },
        ),
    ]

    cmr = build_common_material_record(materials)

    assert cmr["approval_status"] == "PROVISIONAL"
    assert cmr["canonical_description"] == "SS 304 GATE VALVE 2 IN 150 LB"
    assert cmr["category"] == "Valve"

    assert (
        cmr["canonical_technical_attributes"]["material_grade"]
        == "SS304"
    )

    assert (
        cmr["canonical_technical_attributes"]["pressure_rating"]
        == {"value": 150.0, "unit": "LB"}
    )

    assert cmr["provenance"]["source_count"] == 2


def test_conflicting_cluster_keeps_canonical_value_unknown():
    materials = [
        make_material(
            1,
            "NTPC",
            "NTPC-001",
            "SS304 GATE VALVE 2 IN 150 LB",
            normalized_description="SS304 GATE VALVE 2 IN 150 LB",
            dimensions={"value": 2.0, "unit": "IN"},
            parsed_specifications={
                "material_grade": "SS304",
                "dimensions": {"value": 2.0, "unit": "IN"},
                "pressure_rating": {"value": 150.0, "unit": "LB"},
            },
        ),
        make_material(
            2,
            "BHEL",
            "BHEL-001",
            "SS304 GATE VALVE 2 IN 300 LB",
            normalized_description="SS304 GATE VALVE 2 IN 300 LB",
            dimensions={"value": 2.0, "unit": "IN"},
            parsed_specifications={
                "material_grade": "SS304",
                "dimensions": {"value": 2.0, "unit": "IN"},
                "pressure_rating": {"value": 300.0, "unit": "LB"},
            },
        ),
    ]

    cmr = build_common_material_record(materials)

    assert (
        cmr["canonical_technical_attributes"]["pressure_rating"]
        == UNKNOWN
    )

    assert "pressure_rating" in cmr["critical_unknown_fields"]


def test_cmr_preserves_every_source_material():
    materials = [
        make_material(
            10,
            "NTPC",
            "NTPC-VALVE-1",
            "SS304 GATE VALVE",
            normalized_description="SS304 GATE VALVE",
        ),
        make_material(
            20,
            "BHEL",
            "BHEL-VALVE-9",
            "SS304 GATE VALVE",
            normalized_description="SS304 GATE VALVE",
        ),
    ]

    cmr = build_common_material_record(materials)

    assert cmr["provenance"]["material_ids"] == [10, 20]

    assert cmr["source_materials"] == [
        {
            "material_id": 10,
            "cpse": "NTPC",
            "material_code": "NTPC-VALVE-1",
            "description": "SS304 GATE VALVE",
            "source_file": "NTPC.csv",
            "source_page": 1,
        },
        {
            "material_id": 20,
            "cpse": "BHEL",
            "material_code": "BHEL-VALVE-9",
            "description": "SS304 GATE VALVE",
            "source_file": "BHEL.csv",
            "source_page": 1,
        },
    ]
