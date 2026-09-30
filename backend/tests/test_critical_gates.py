from app.services.matching.critical_gates import (
    evaluate_critical_gates,
    gates_allow_high_confidence,
)


def valve(
    pressure,
    dimensions,
):
    return {
        "category": "Valve",
        "parsed_specifications": {
            "pressure_rating": pressure,
            "dimensions": dimensions,
        },
    }


def test_matching_critical_fields_pass():
    material_a = valve(
        {"value": 150, "unit": "LB"},
        {"size": "2 IN"},
    )

    material_b = valve(
        {"value": 150, "unit": "LB"},
        {"size": "2 IN"},
    )

    checks = evaluate_critical_gates(material_a, material_b)

    assert all(check["status"] == "PASS" for check in checks)
    assert gates_allow_high_confidence(checks)


def test_conflicting_pressure_rating_requires_review():
    material_a = valve(
        {"value": 150, "unit": "LB"},
        {"size": "2 IN"},
    )

    material_b = valve(
        {"value": 300, "unit": "LB"},
        {"size": "2 IN"},
    )

    checks = evaluate_critical_gates(material_a, material_b)

    assert any(
        check["field"] == "pressure_rating"
        and check["status"] == "CONFLICT"
        for check in checks
    )

    assert not gates_allow_high_confidence(checks)


def test_missing_critical_field_requires_review():
    material_a = valve(
        None,
        {"size": "2 IN"},
    )

    material_b = valve(
        {"value": 150, "unit": "LB"},
        {"size": "2 IN"},
    )

    checks = evaluate_critical_gates(material_a, material_b)

    assert any(
        check["field"] == "pressure_rating"
        and check["status"] == "UNKNOWN"
        for check in checks
    )

    assert not gates_allow_high_confidence(checks)


def test_different_categories_require_review():
    material_a = {
        "category": "Valve",
        "parsed_specifications": {},
    }

    material_b = {
        "category": "Pipe",
        "parsed_specifications": {},
    }

    checks = evaluate_critical_gates(material_a, material_b)

    assert checks[0]["field"] == "category"
    assert checks[0]["status"] == "CONFLICT"

    assert not gates_allow_high_confidence(checks)


def test_dimension_unit_conversion_passes():
    material_a = valve(
        {"value": 150, "unit": "LB"},
        {"value": 2, "unit": "IN"},
    )

    material_b = valve(
        {"value": 150, "unit": "LB"},
        {"value": 50.8, "unit": "MM"},
    )

    checks = evaluate_critical_gates(
        material_a,
        material_b,
    )

    assert all(
        check["status"] == "PASS"
        for check in checks
    )


def test_top_level_none_falls_back_to_parsed_specifications():
    material_a = {
        "category": "Valve",
        "dimensions": None,
        "parsed_specifications": {
            "pressure_rating": {"value": 150, "unit": "LB"},
            "dimensions": {"value": 2, "unit": "IN"},
        },
    }

    material_b = {
        "category": "Valve",
        "dimensions": None,
        "parsed_specifications": {
            "pressure_rating": {"value": 150, "unit": "LB"},
            "dimensions": {"value": 2, "unit": "IN"},
        },
    }

    checks = evaluate_critical_gates(material_a, material_b)

    assert all(check["status"] == "PASS" for check in checks)
    assert gates_allow_high_confidence(checks)


def test_fastener_dimensions_conflict_when_lengths_differ():
    from app.services.parsing.service import parse_specifications

    mat_iocl = {
        "category": "Fastener",
        "parsed_specifications": parse_specifications(
            "HEX HEAD BOLT M8 X 25 MM SS304 GRADE A2-70"
        ),
    }
    mat_ongc = {
        "category": "Fastener",
        "parsed_specifications": parse_specifications(
            "BOLT, HEX, SS304, A2-70, SIZE M8×30"
        ),
    }

    checks = evaluate_critical_gates(mat_iocl, mat_ongc)
    dim_check = next((c for c in checks if c["field"] == "dimensions"), None)
    grade_check = next((c for c in checks if c["field"] == "material_grade"), None)

    assert dim_check is not None
    assert dim_check["status"] == "CONFLICT"
    assert grade_check is not None
    assert grade_check["status"] == "PASS"
    assert not gates_allow_high_confidence(checks)


def test_fastener_dimensions_pass_when_matching():
    from app.services.parsing.service import parse_specifications

    mat_a = {
        "category": "Fastener",
        "parsed_specifications": parse_specifications(
            "HEX HEAD BOLT M8 X 25 MM SS304 GRADE A2-70"
        ),
    }
    mat_b = {
        "category": "Fastener",
        "parsed_specifications": parse_specifications(
            "HEXAGONAL HEAD BOLT, SS304, A2-70, SIZE M8x25"
        ),
    }

    checks = evaluate_critical_gates(mat_a, mat_b)
    assert all(check["status"] == "PASS" for check in checks)
    assert gates_allow_high_confidence(checks)

