from app.services.blocking.service import (
    MaterialForBlocking,
    generate_block_keys,
    generate_candidates,
)


def test_category_and_grade_block():
    material = MaterialForBlocking(
        id=1,
        category="Valve",
        normalized_description="SS 304 GATE VALVE 2 IN 150 LB",
        material_grade="SS304",
    )

    keys = generate_block_keys(material)

    assert "CAT:VALVE" in keys
    assert "CAT_GRADE:VALVE:SS304" in keys


def test_manufacturer_part_number_block():
    material = MaterialForBlocking(
        id=1,
        category="Valve",
        normalized_description="GATE VALVE",
        manufacturer_part_number="ABC-123",
    )

    keys = generate_block_keys(material)

    assert "MPN:ABC-123" in keys


def test_candidates_share_block():
    source = MaterialForBlocking(
        id=1,
        category="Valve",
        normalized_description="SS304 GATE VALVE 2 IN",
        material_grade="SS304",
    )

    target = MaterialForBlocking(
        id=2,
        category="Valve",
        normalized_description="SS304 GATE VALVE 50 MM",
        material_grade="SS304",
    )

    candidates = generate_candidates(
        source,
        [target],
    )

    assert len(candidates) == 1
    assert candidates[0].id == 2


def test_different_category_is_not_candidate_without_shared_key():
    source = MaterialForBlocking(
        id=1,
        category="Valve",
        normalized_description="GATE VALVE",
    )

    target = MaterialForBlocking(
        id=2,
        category="Bearing",
        normalized_description="ROLLER BEARING",
    )

    candidates = generate_candidates(
        source,
        [target],
    )

    assert candidates == []
