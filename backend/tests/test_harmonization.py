from app.services.harmonization.service import (
    UNKNOWN,
    build_common_material_record,
)


def material(
    material_id,
    cpse,
    code,
    description,
    *,
    normalized_description=None,
    category="Valve",
    material_grade="SS304",
    dimensions=None,
    parsed_specifications=None,
):
    return {
        "id": material_id,
        "cpse": cpse,
        "material_code": code,
        "description": description,
        "normalized_description": (
            normalized_description
            if normalized_description is not None
            else description.upper()
        ),
        "category": category,
        "material_grade": material_grade,
        "dimensions": dimensions,
        "parsed_specifications": parsed_specifications or {},
        "specifications": {},
        "source_file": f"{cpse}.csv",
        "source_page": 1,
    }


def test_identical_sources_produce_canonical_values():
    materials = [
        material(
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
        material(
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

    result = build_common_material_record(materials)

    assert result["canonical_description"] == "SS 304 GATE VALVE 2 IN 150 LB"
    assert result["category"] == "Valve"
    assert result["canonical_technical_attributes"]["material_grade"] == "SS304"
    assert result["canonical_technical_attributes"]["dimensions"] == {
        "value": 2.0,
        "unit": "IN",
    }
    assert result["canonical_technical_attributes"]["pressure_rating"] == {
        "value": 150.0,
        "unit": "LB",
    }


def test_conflicting_critical_specification_becomes_unknown():
    materials = [
        material(
            1,
            "NTPC",
            "NTPC-001",
            "SS304 GATE VALVE 2 IN 150 LB",
            dimensions={"value": 2.0, "unit": "IN"},
            parsed_specifications={
                "material_grade": "SS304",
                "dimensions": {"value": 2.0, "unit": "IN"},
                "pressure_rating": {"value": 150.0, "unit": "LB"},
            },
        ),
        material(
            2,
            "BHEL",
            "BHEL-001",
            "SS304 GATE VALVE 2 IN 300 LB",
            dimensions={"value": 2.0, "unit": "IN"},
            parsed_specifications={
                "material_grade": "SS304",
                "dimensions": {"value": 2.0, "unit": "IN"},
                "pressure_rating": {"value": 300.0, "unit": "LB"},
            },
        ),
    ]

    result = build_common_material_record(materials)

    assert result["canonical_technical_attributes"]["pressure_rating"] == UNKNOWN
    assert "pressure_rating" in result["critical_unknown_fields"]


def test_missing_source_specification_becomes_unknown():
    materials = [
        material(
            1,
            "NTPC",
            "NTPC-001",
            "SS304 GATE VALVE 2 IN 150 LB",
            dimensions={"value": 2.0, "unit": "IN"},
            parsed_specifications={
                "material_grade": "SS304",
                "dimensions": {"value": 2.0, "unit": "IN"},
                "pressure_rating": {"value": 150.0, "unit": "LB"},
            },
        ),
        material(
            2,
            "BHEL",
            "BHEL-001",
            "SS304 GATE VALVE 2 IN",
            dimensions={"value": 2.0, "unit": "IN"},
            parsed_specifications={
                "material_grade": "SS304",
                "dimensions": {"value": 2.0, "unit": "IN"},
            },
        ),
    ]

    result = build_common_material_record(materials)

    assert result["canonical_technical_attributes"]["pressure_rating"] == UNKNOWN
    assert "pressure_rating" in result["critical_unknown_fields"]


def test_source_identity_and_provenance_are_preserved():
    materials = [
        material(
            101,
            "NTPC",
            "NTPC-VALVE-1",
            "SS304 GATE VALVE",
        ),
        material(
            202,
            "BHEL",
            "BHEL-VALVE-9",
            "SS304 GATE VALVE",
        ),
    ]

    result = build_common_material_record(materials)

    assert result["provenance"]["source_count"] == 2
    assert result["provenance"]["material_ids"] == [101, 202]

    assert result["source_materials"][0]["cpse"] == "NTPC"
    assert result["source_materials"][0]["material_code"] == "NTPC-VALVE-1"

    assert result["source_materials"][1]["cpse"] == "BHEL"
    assert result["source_materials"][1]["material_code"] == "BHEL-VALVE-9"


def test_description_conflict_is_not_resolved_by_picking_one_source():
    materials = [
        material(
            1,
            "NTPC",
            "NTPC-001",
            "SS304 GATE VALVE 2 IN 150 LB",
            normalized_description="SS304 GATE VALVE 2 IN 150 LB",
        ),
        material(
            2,
            "BHEL",
            "BHEL-001",
            "STAINLESS STEEL 304 GATE VALVE 2 IN 150 LB",
            normalized_description="STAINLESS STEEL 304 GATE VALVE 2 IN 150 LB",
        ),
    ]

    result = build_common_material_record(materials)

    assert result["canonical_description"] == UNKNOWN
