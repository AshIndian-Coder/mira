from app.services.matching.scoring import calculate_match_score


def make_material(
    description,
    grade,
    size,
    pressure,
):
    return {
        "normalized_description": description,
        "material_grade": grade,
        "parsed_specifications": {
            "size": size,
            "pressure_rating": pressure,
        },
        "other_attributes": {},
    }


def test_identical_materials_score_high():
    material = make_material(
        "SS 304 GATE VALVE 2 IN 150 LB",
        "SS304",
        {"value": 2.0, "unit": "IN"},
        {"value": 150.0, "unit": "LB"},
    )

    result = calculate_match_score(material, material)

    assert result["final_score"] == 1.0


def test_different_pressure_reduces_specification_score():
    left = make_material(
        "SS 304 GATE VALVE 2 IN 150 LB",
        "SS304",
        {"value": 2.0, "unit": "IN"},
        {"value": 150.0, "unit": "LB"},
    )

    right = make_material(
        "SS 304 GATE VALVE 2 IN 300 LB",
        "SS304",
        {"value": 2.0, "unit": "IN"},
        {"value": 300.0, "unit": "LB"},
    )

    result = calculate_match_score(left, right)

    assert result["specification_similarity"] == 0.5
    assert result["final_score"] < 1.0


def test_different_grade_reduces_grade_score():
    left = make_material(
        "SS 304 GATE VALVE 2 IN 150 LB",
        "SS304",
        {"value": 2.0, "unit": "IN"},
        {"value": 150.0, "unit": "LB"},
    )

    right = make_material(
        "SS 316 GATE VALVE 2 IN 150 LB",
        "SS316",
        {"value": 2.0, "unit": "IN"},
        {"value": 150.0, "unit": "LB"},
    )

    result = calculate_match_score(left, right)

    assert result["material_grade_similarity"] == 0.0


def test_inches_and_mm_are_equivalent():
    assert value_similarity(
        {"value": 2, "unit": "IN"},
        {"value": 50.8, "unit": "MM"},
    ) == 1.0


def test_different_dimensions_conflict():
    assert value_similarity(
        {"value": 2, "unit": "IN"},
        {"value": 60, "unit": "MM"},
    ) == 0.0


def test_specification_uses_unit_conversion():
    left = {
        "dimensions": {
            "value": 2,
            "unit": "IN",
        }
    }

    right = {
        "dimensions": {
            "value": 50.8,
            "unit": "MM",
        }
    }

    assert specification_similarity(
        left,
        right,
        "FASTENER",
    ) == 1.0

from app.services.matching.similarity import (
    value_similarity,
    specification_similarity,
)
