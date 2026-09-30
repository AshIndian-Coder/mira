from app.services.matching.classifier import classify_match


def make_valve(
    description,
    grade,
    pressure,
    size,
):
    return {
        "category": "Valve",
        "normalized_description": description,
        "material_grade": grade,
        "parsed_specifications": {
            "pressure_rating": pressure,
            "dimensions": size,
        },
        "other_attributes": {},
    }


def test_identical_materials_are_high_confidence():
    material = make_valve(
        "SS 304 GATE VALVE 2 IN 150 LB",
        "SS304",
        {"value": 150, "unit": "LB"},
        {"size": "2 IN"},
    )

    result = classify_match(material, material)

    assert result["decision"] == "HIGH_CONFIDENCE"


def test_conflicting_pressure_requires_review():
    source = make_valve(
        "SS 304 GATE VALVE 2 IN 150 LB",
        "SS304",
        {"value": 150, "unit": "LB"},
        {"size": "2 IN"},
    )

    target = make_valve(
        "SS 304 GATE VALVE 2 IN 300 LB",
        "SS304",
        {"value": 300, "unit": "LB"},
        {"size": "2 IN"},
    )

    result = classify_match(source, target)

    assert result["decision"] == "DIFFERENT"

    assert any(
        check["field"] == "pressure_rating"
        and check["status"] == "CONFLICT"
        for check in result["critical_checks"]
    )


def test_missing_pressure_requires_review():
    source = make_valve(
        "SS 304 GATE VALVE 2 IN",
        "SS304",
        None,
        {"size": "2 IN"},
    )

    target = make_valve(
        "SS 304 GATE VALVE 2 IN 150 LB",
        "SS304",
        {"value": 150, "unit": "LB"},
        {"size": "2 IN"},
    )

    result = classify_match(source, target)

    assert result["decision"] == "REVIEW"


def test_different_materials_are_not_high_confidence():
    source = make_valve(
        "SS 304 GATE VALVE 2 IN 150 LB",
        "SS304",
        {"value": 150, "unit": "LB"},
        {"size": "2 IN"},
    )

    target = {
        "category": "Bearing",
        "normalized_description": "ROLLER BEARING 50 MM",
        "material_grade": None,
        "parsed_specifications": {},
        "other_attributes": {},
    }

    result = classify_match(source, target)

    assert result["decision"] == "DIFFERENT"
    assert result["decision"] != "HIGH_CONFIDENCE"


def test_result_contains_frontend_required_data():
    material = make_valve(
        "SS 304 GATE VALVE 2 IN 150 LB",
        "SS304",
        {"value": 150, "unit": "LB"},
        {"size": "2 IN"},
    )

    result = classify_match(material, material)

    assert "scores" in result
    assert "critical_checks" in result
    assert "decision" in result

    assert "final_score" in result["scores"]


def test_hard_conflict_bolt_dimension_is_different():
    """M8 x 25 SS304 vs M8 x 30 SS304 has a hard dimension conflict -> DIFFERENT."""
    source = {
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
    target = {
        "category": "Fastener",
        "description": "HEX HEAD BOLT M8 X 30 MM SS304",
        "normalized_description": "HEX HEAD BOLT M8 X 30 MM SS304",
        "material_grade": "SS304",
        "parsed_specifications": {
            "thread_size": "M8",
            "thread_pitch": None,
            "bolt_length": {"value": 30.0, "unit": "MM"},
            "dimensions": "M8X30MM",
            "material_grade": "SS304",
        },
        "other_attributes": {},
    }
    result = classify_match(source, target)
    assert result["decision"] == "DIFFERENT"
    assert any(c["field"] == "dimensions" and c["status"] == "CONFLICT" for c in result["critical_checks"])


def test_unknown_dimensions_requires_review():
    """HEX HEAD BOLT SS304 with missing critical dimensions -> REVIEW."""
    source = {
        "category": "Fastener",
        "description": "HEX HEAD BOLT SS304",
        "normalized_description": "HEX HEAD BOLT SS304",
        "material_grade": "SS304",
        "parsed_specifications": {
            "material_grade": "SS304",
        },
        "other_attributes": {},
    }
    target = {
        "category": "Fastener",
        "description": "HEX HEAD BOLT SS304",
        "normalized_description": "HEX HEAD BOLT SS304",
        "material_grade": "SS304",
        "parsed_specifications": {
            "material_grade": "SS304",
        },
        "other_attributes": {},
    }
    result = classify_match(source, target)
    assert result["decision"] == "REVIEW"
    assert any(c["field"] == "dimensions" and c["status"] == "UNKNOWN" for c in result["critical_checks"])


def test_obvious_equivalent_is_high_confidence():
    """HEX HEAD BOLT M8 X 25 MM SS304 vs HEX HEAD BOLT M8 X 25 MM SS 304 -> HIGH_CONFIDENCE."""
    source = {
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
    target = {
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
    result = classify_match(source, target)
    assert result["decision"] == "HIGH_CONFIDENCE"
    assert all(c["status"] == "PASS" for c in result["critical_checks"])
