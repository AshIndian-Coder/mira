import pytest

from app.services.parsing.service import (
    extract_dimensions,
    extract_fastener_dimensions,
    extract_grade,
    extract_pressure_rating,
    extract_voltage,
    parse_specifications,
    extract_nominal_bore,
    extract_metric_thread,
    extract_schedule,
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


def test_embedded_nominal_bore():
    result = extract_nominal_bore(
        "GALVANISED MS SOCKET ERW 25MMNB IS:1239"
    )

    assert result == {
        "value": 25.0,
        "unit": "NB",
    }


def test_plain_nominal_bore():
    result = extract_nominal_bore(
        "PIPE 300NB"
    )

    assert result == {
        "value": 300.0,
        "unit": "NB",
    }


def test_metric_thread_valid():
    result = extract_metric_thread(
        "HEX BOLT M8 X 1.25"
    )

    assert result == {
        "nominal_diameter": 8.0,
        "pitch": 1.25,
        "unit": "MM",
    }


def test_metric_thread_does_not_misread_length():
    result = extract_metric_thread(
        "HEX BOLT M8 X 40MM"
    )

    assert result is None


def test_metric_thread_large_diameter():
    result = extract_metric_thread(
        "BOLT M45 X 3"
    )

    assert result == {
        "nominal_diameter": 45.0,
        "pitch": 3.0,
        "unit": "MM",
    }


def test_fastener_grade():
    assert extract_grade(
        "HIGH TENSILE BOLT GR 12.9"
    ) == "GR12.9"


def test_sa_grade():
    assert extract_grade(
        "PLATE SA516 GR.70"
    ) == "SA516 GR70"


def test_ca6nm_grade():
    assert extract_grade(
        "IMPELLER MATERIAL CA6NM"
    ) == "CA6NM"


def test_extract_schedule():
    assert extract_schedule("PIPE SS304 NB 25 (1.0 IN) SCH40") == "SCH40"
    assert extract_schedule("PIPE SS304 NB 25 (1.0 IN) SCH 40") == "SCH40"
    assert extract_schedule("PIPE SS316 NB 25 (1.0 IN) SCH80") == "SCH80"
    assert extract_schedule("PIPE SS316 NB 25 (1.0 IN) SCH 80") == "SCH80"
    assert extract_schedule("PIPE CS NB 150 (5.9 IN) SCHXS") == "SCHXS"
    assert extract_schedule("PIPE CS NB 150 (5.9 IN) SCH XS") == "SCHXS"
    assert extract_schedule("pipe gi nb 15 (0.6 in) schedule 40 make tata") == "SCH40"
    assert extract_schedule("PIPE CS NB 150 (5.9 IN) SCHEDULE 80") == "SCH80"
    assert extract_schedule("PIPE CS NB 150 (5.9 IN) SCHEDULE XS MAKE ISMT") == "SCHXS"


def test_extract_schedule_absence():
    assert extract_schedule("GATE VALVE 2 IN 150 LB") is None
    assert extract_schedule("PIPE 50NB") is None
    assert extract_schedule("BOLT M45 X 3") is None
    assert extract_schedule("") is None


def test_parse_specifications_schedule():
    res1 = parse_specifications("PIPE SS304 NB 25 (1.0 IN) SCH 40")
    assert res1["schedule"] == "SCH40"

    res2 = parse_specifications("PIPE CS NB 150 (5.9 IN) SCHEDULE XS")
    assert res2["schedule"] == "SCHXS"

    res3 = parse_specifications("GATE VALVE 2 IN 150 LB")
    assert res3["schedule"] is None


def test_nominal_bore_with_material_grade():
    res1 = parse_specifications("PIPE SS 304 NB 80 (3.1 IN) SCH 80")
    assert res1["material_grade"] == "SS304"
    assert res1["nominal_bore"] == {"value": 80.0, "unit": "NB"}
    assert res1["schedule"] == "SCH80"

    res2 = parse_specifications("PIPE SS304 NB 80 (3.1 IN) SCH80")
    assert res2["material_grade"] == "SS304"
    assert res2["nominal_bore"] == {"value": 80.0, "unit": "NB"}
    assert res2["schedule"] == "SCH80"

    res3 = parse_specifications("PIPE SS 316 NB 200 (7.9 IN) SCH XS")
    assert res3["material_grade"] == "SS316"
    assert res3["nominal_bore"] == {"value": 200.0, "unit": "NB"}
    assert res3["schedule"] == "SCHXS"

    res4 = parse_specifications("PIPE SS304 NB 600 (23.6 IN) SCH 40")
    assert res4["material_grade"] == "SS304"
    assert res4["nominal_bore"] == {"value": 600.0, "unit": "NB"}
    assert res4["schedule"] == "SCH40"


def test_fastener_dimensions_iocl_example():
    res = parse_specifications("HEX HEAD BOLT M8 X 25 MM SS304 GRADE A2-70")
    assert res["material_grade"] == "SS304"
    assert res["dimensions"] == {
        "diameter": {"value": 8.0, "unit": "MM"},
        "length": {"value": 25.0, "unit": "MM"},
    }


def test_fastener_dimensions_ongc_example():
    res = parse_specifications("BOLT, HEX, SS304, A2-70, SIZE M8×30")
    assert res["material_grade"] == "SS304"
    assert res["dimensions"] == {
        "diameter": {"value": 8.0, "unit": "MM"},
        "length": {"value": 30.0, "unit": "MM"},
    }


def test_fastener_dimensions_variants():
    # Various callout formatting variants
    variants = [
        "M8 X 25 MM",
        "M8 x 25 mm",
        "M8×25",
        "M8 × 25",
        "SIZE M8×25",
        "BOLT M8X25",
        "HEX HEAD BOLT M8 X 25 MM",
        "HEXAGONAL HEAD BOLT, SS304, A2-70, SIZE M8x25",
    ]
    for variant in variants:
        dims = extract_fastener_dimensions(variant)
        assert dims is not None, f"Failed on {variant}"
        assert dims["diameter"] == {"value": 8.0, "unit": "MM"}, f"Wrong dia on {variant}"
        assert dims["length"] == {"value": 25.0, "unit": "MM"}, f"Wrong len on {variant}"


def test_fastener_dimensions_plain_callout():
    res = parse_specifications("MS HEX HD BOLT WITH NUT IS:1363 6X25MM")
    assert res["dimensions"] == {
        "diameter": {"value": 6.0, "unit": "MM"},
        "length": {"value": 25.0, "unit": "MM"},
    }


def test_fastener_dimensions_three_part():
    dims = extract_fastener_dimensions("STUD BOLT M140X4X810")
    assert dims == {
        "diameter": {"value": 140.0, "unit": "MM"},
        "pitch": {"value": 4.0, "unit": "MM"},
        "length": {"value": 810.0, "unit": "MM"},
    }


def test_fastener_dimensions_thread_pitch_not_misclassified():
    # M8 X 1.25 is a thread pitch, not length
    dims = extract_fastener_dimensions("HEX BOLT M8 X 1.25")
    assert dims is None

    res = parse_specifications("HEX BOLT M8 X 1.25")
    assert res["metric_thread"] == {
        "nominal_diameter": 8.0,
        "pitch": 1.25,
        "unit": "MM",
    }

