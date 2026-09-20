"""
Unit and regression tests for text_similarity implementation.
"""

from difflib import SequenceMatcher
import math
import pytest

from app.services.matching.similarity import text_similarity, _c_sequence_matcher


def python_reference_text_similarity(left: str, right: str) -> float:
    left = (left or "").upper().strip()
    right = (right or "").upper().strip()
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()


def test_text_similarity_exact_matches():
    assert text_similarity("GATE VALVE CS 150 LB 2 IN", "GATE VALVE CS 150 LB 2 IN") == 1.0
    assert text_similarity("SEAMLESS PIPE ASTM A106", "SEAMLESS PIPE ASTM A106") == 1.0
    assert text_similarity("HEX HEAD BOLT M8", "HEX HEAD BOLT M8") == 1.0


def test_text_similarity_case_and_whitespace():
    # Case insensitivity
    assert text_similarity("gate valve cs 150 lb", "GATE VALVE CS 150 LB") == 1.0
    assert text_similarity("Hex Bolt M8x25", "HEX BOLT M8X25") == 1.0
    # Whitespace stripping at edges
    assert text_similarity("  PIPE CS 50MM  ", "PIPE CS 50MM") == 1.0


def test_text_similarity_empty_and_null_inputs():
    assert text_similarity("", "") == 0.0
    assert text_similarity("   ", "") == 0.0
    assert text_similarity(None, "PIPE CS") == 0.0
    assert text_similarity("GATE VALVE", None) == 0.0
    assert text_similarity("", "GATE VALVE") == 0.0


def test_text_similarity_output_range():
    test_pairs = [
        ("VALVE GATE CS 150 LB 2 IN", "GATE VALVE CS 150 LB 2 IN"),
        ("BALL VALVE SS304 300 LB", "BALL VALVE SS316 300 LB"),
        ("ABC", "XYZ"),
        ("HEX BOLT M12 X 50 MM", "HEX BOLT M12 X 75 MM"),
        ("O-RING [VITON] 25.4MM ID", "O RING VITON 25.4"),
    ]
    for a, b in test_pairs:
        score = text_similarity(a, b)
        assert 0.0 <= score <= 1.0


def test_text_similarity_equivalence_to_reference():
    corpus = [
        ("GATE VALVE CS 150 LB 2 IN", "VALVE GATE 2 INCH 150# CS"),
        ("HEX HEAD BOLT M8 X 25 MM SS304 GRADE A2-70", "HEXAGONAL HEAD BOLT, SS304, A2-70, SIZE M8x25"),
        ("PIPE CS IS1239PRT1 ERW HVY 50MM NB", "PIPE CS 50MM NB ERW HEAVY"),
        ("DEEP GROOVE BALL BEARING 6205", "BALL BEARING DEEP GROOVE 6205 2RS"),
        ("NUMERIC DIGITAL RELAY 220V DC REF615", "RLY 220VDC:REF-615ABB:HBFHAEAGNDA1BNN11G"),
        ("SPIRAL WOUND GASKET SIZE 250X230X4 MM", "SPIRAL WOUND GASKET SS304 250X230X4"),
        ("1/4\" OLIVE FERRULE BRASS", "1/4 OLIVE FERRULE BRASS"),
        ("TUBE:SA213 T12:OD-38MM:TH-6MM", "TUBE SA213 T12 OD 38MM TH 6MM"),
        ("LED BASED STREET LIGHT - 65-80W", "LED STREET LIGHT 65W"),
        ("U-CLAMP:M.S.:350MM", "U CLAMP MS 350MM"),
    ]
    for a, b in corpus:
        v_prod = text_similarity(a, b)
        v_ref = python_reference_text_similarity(a, b)
        assert math.isclose(v_prod, v_ref, abs_tol=0.03), f"Mismatch for {a} vs {b}: prod={v_prod}, ref={v_ref}"


def test_c_acceleration_loaded():
    assert _c_sequence_matcher is not None, "C accelerator _c_sequence_matcher should be loaded in test environment"
