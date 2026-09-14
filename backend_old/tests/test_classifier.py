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

    assert result["decision"] == "REVIEW"

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

    assert result["decision"] == "REVIEW"
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
