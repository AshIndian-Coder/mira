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
