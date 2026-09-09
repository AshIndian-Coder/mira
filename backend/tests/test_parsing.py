import pytest

from app.services.parsing.service import (
    extract_dimensions,
    extract_grade,
    extract_pressure_rating,
    extract_voltage,
    parse_specifications,
)


def test_extract_grade():
    assert extract_grade("SS304 GATE VALVE") == "SS304"


def test_extract_pressure_rating():
    assert extract_pressure_rating("GATE VALVE 150 LB") == {
        "value": 150.0,
        "unit": "LB",
    }


def test_extract_dimensions():
    assert extract_dimensions("GATE VALVE 2 IN") == {
        "value": 2.0,
        "unit": "IN",
    }


def test_extract_voltage():
    assert extract_voltage("ELECTRICAL CONNECTOR 415 V") == {
        "value": 415.0,
        "unit": "V",
    }


def test_parse_specifications():
    result = parse_specifications("SS304 GATE VALVE 2 IN 150 LB")

    assert result["material_grade"] == "SS304"
    assert result["pressure_rating"] == {
        "value": 150.0,
        "unit": "LB",
    }
    assert result["dimensions"] == {
        "value": 2.0,
        "unit": "IN",
    }


def test_pressure_pound_notation():
    result = parse_specifications("GATE VALVE 2 IN 150#")

    assert result["pressure_rating"] == {
        "value": 150.0,
        "unit": "LB",
    }


def test_pressure_pound_word():
    result = parse_specifications("GATE VALVE 2 IN 150 POUND")

    assert result["pressure_rating"] == {
        "value": 150.0,
        "unit": "LB",
    }


def test_extract_stainless_steel_grade():
    assert extract_grade("STAINLESS STEEL 304 GATE VALVE") == "SS304"


def test_compact_millimeter_dimension():
    result = parse_specifications("GALVANISED SOCKET 25MM")
    assert result["dimensions"] == {"value": 25.0, "unit": "MM"}


def test_compact_voltage():
    result = parse_specifications("PUSH BUTTON 415V")
    assert result["voltage_class"] == {"value": 415.0, "unit": "V"}


def test_kilovolt():
    result = parse_specifications("CABLE 11KV")
    assert result["voltage_class"] == {"value": 11.0, "unit": "KV"}


def test_nominal_bore():
    result = parse_specifications("PIPE 50NB")
    assert result["nominal_bore"] == {"value": 50.0, "unit": "NB"}


def test_metric_thread():
    result = parse_specifications("BOLT M45 X 3")
    assert result["metric_thread"] == {
        "nominal_diameter": 45.0,
        "pitch": 3.0,
        "unit": "MM",
    }


def test_multiple_dimension_tokens():
    result = parse_specifications("PIPE OD60.3 X 5.54THK MM")
    assert len(result["dimension_tokens"]) >= 2


def test_extract_dished_end_dimensions():
    from app.services.parsing.service import (
        extract_dished_end_dimensions,
    )

    result = extract_dished_end_dimensions(
        "DISHED END 2:1 ELLIP ID1700X25THK(MIN)"
    )

    assert result == {
        "internal_diameter": {
            "value": 1700.0,
            "unit": "MM",
        },
        "thickness": {
            "value": 25.0,
            "unit": "MM",
        },
    }
