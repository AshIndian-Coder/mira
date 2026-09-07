from app.services.normalization.service import normalize_material_description


def test_case_and_separator_normalization():
    assert normalize_material_description(
        'SS 304 GATE VALVE 2" 150 LB'
    ) == "SS 304 GATE VALVE 2 IN 150 LB"


def test_equivalent_descriptions_normalize_identically():
    first = normalize_material_description(
        'SS 304 GATE VALVE 2" 150 LB'
    )

    second = normalize_material_description(
        "ss-304 gate valve 2 inch 150 lbs"
    )

    assert first == second


def test_safe_abbreviation_expansion():
    result = normalize_material_description(
        "MFG ASSY - DIA 25 MM"
    )

    assert result == "MFG ASSEMBLY DIAMETER 25 MM"


def test_empty_input():
    assert normalize_material_description("") == ""
    assert normalize_material_description(None) == ""
