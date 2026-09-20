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


def test_build_block_index():
    m1 = MaterialForBlocking(
        id=1,
        category="Valve",
        normalized_description="SS304 GATE VALVE 2 IN",
        material_grade="SS304",
        manufacturer_part_number="ABC-100",
    )
    m2 = MaterialForBlocking(
        id=2,
        category="Valve",
        normalized_description="SS304 GLOBE VALVE 2 IN",
        material_grade="SS304",
    )
    m3 = MaterialForBlocking(
        id=3,
        category="Bearing",
        normalized_description="ROLLER BEARING 50MM",
    )

    from app.services.blocking.service import build_block_index

    index = build_block_index([m1, m2, m3])

    assert "CAT:VALVE" in index
    assert index["CAT:VALVE"] == [1, 2]
    assert "CAT:BEARING" in index
    assert index["CAT:BEARING"] == [3]
    assert "MPN:ABC-100" in index
    assert index["MPN:ABC-100"] == [1]
    assert "CAT_GRADE:VALVE:SS304" in index
    assert index["CAT_GRADE:VALVE:SS304"] == [1, 2]


def test_multiple_and_overlapping_block_keys_deduplication():
    # Source and Target share multiple keys: CAT:VALVE, CAT_GRADE:VALVE:SS304, TYPE:VALVE:VALVE, MPN:VLV-99
    source = MaterialForBlocking(
        id=1,
        category="Valve",
        normalized_description="GATE VALVE SS304",
        material_grade="SS304",
        manufacturer_part_number="VLV-99",
    )
    target_multi = MaterialForBlocking(
        id=2,
        category="Valve",
        normalized_description="BALL VALVE SS304",
        material_grade="SS304",
        manufacturer_part_number="VLV-99",
    )
    target_single = MaterialForBlocking(
        id=3,
        category="Valve",
        normalized_description="CHECK VALVE CS",
        material_grade="CS",
    )

    from app.services.blocking.service import build_block_index

    materials = [source, target_multi, target_single]
    index = build_block_index(materials)
    target_map = {m.id: m for m in materials}
    target_order = {m.id: i for i, m in enumerate(materials)}

    cands_unindexed = generate_candidates(source, materials)
    cands_indexed = generate_candidates(
        source,
        block_index=index,
        target_map=target_map,
        target_order=target_order,
    )

    assert [c.id for c in cands_indexed] == [c.id for c in cands_unindexed]
    assert [c.id for c in cands_indexed] == [2, 3]
    # Verify target 2 is only included once despite sharing 4+ block keys
    assert len([c for c in cands_indexed if c.id == 2]) == 1


def test_empty_and_no_match_blocks():
    from app.services.blocking.service import build_block_index

    empty_mat = MaterialForBlocking(
        id=10,
        category=None,
        normalized_description="",
    )
    assert generate_block_keys(empty_mat) == set()

    t1 = MaterialForBlocking(id=1, category="Valve", normalized_description="GATE VALVE")
    t2 = MaterialForBlocking(id=2, category="Bearing", normalized_description="ROLLER BEARING")
    index = build_block_index([t1, t2])
    target_map = {1: t1, 2: t2}

    # Empty source returns []
    assert generate_candidates(empty_mat, [t1, t2]) == []
    assert generate_candidates(empty_mat, block_index=index, target_map=target_map) == []

    # Source with keys that match nothing
    isolated_source = MaterialForBlocking(id=3, category="Pump", normalized_description="CENTRIFUGAL PUMP")
    assert generate_candidates(isolated_source, [t1, t2]) == []
    assert generate_candidates(isolated_source, block_index=index, target_map=target_map) == []


def test_deterministic_parity_between_unindexed_and_indexed():
    """Prove indexed candidate generation yields 100% identical candidate pairs and order."""
    from app.services.blocking.service import build_block_index

    dataset = [
        MaterialForBlocking(1, "Valve", "SS304 GATE VALVE 2 IN 150 LB", "SS304", "MPN-101"),
        MaterialForBlocking(2, "Valve", "CS GATE VALVE 2 IN 150 LB", "CS", "MPN-102"),
        MaterialForBlocking(3, "Valve", "SS304 GLOBE VALVE 4 IN 300 LB", "SS304", None),
        MaterialForBlocking(4, "Bearing", "DEEP GROOVE BALL BEARING 25 MM SKF 6205", None, "SKF-6205"),
        MaterialForBlocking(5, "Bearing", "SPHERICAL ROLLER BEARING 50 MM FAG 22210", None, "FAG-22210"),
        MaterialForBlocking(6, "Pump", "CENTRIFUGAL WATER PUMP 50 M3/HR", "CI", None),
        MaterialForBlocking(7, "Pipe", "SEAMLESS PIPE ASTM A106 GR B 2 IN", "A106-B", None),
        MaterialForBlocking(8, "Pipe", "ERW PIPE CS 6 IN SCH 80", "CS", None),
        MaterialForBlocking(9, "Valve", "SS316 BALL VALVE 3 IN 600 LB", "SS316", "MPN-101"),  # shared MPN with #1
        MaterialForBlocking(10, "Fastener", "HEX BOLT CS 2 IN", "CS", None),
    ]

    index = build_block_index(dataset)
    target_map = {m.id: m for m in dataset}
    target_order = {m.id: i for i, m in enumerate(dataset)}
    keys_cache = {m.id: generate_block_keys(m) for m in dataset}

    for source in dataset:
        unindexed = generate_candidates(source, dataset)
        indexed = generate_candidates(
            source,
            block_index=index,
            target_map=target_map,
            target_order=target_order,
            source_keys=keys_cache[source.id],
        )

        unindexed_ids = [c.id for c in unindexed]
        indexed_ids = [c.id for c in indexed]

        assert indexed_ids == unindexed_ids, f"Mismatch for source {source.id}: indexed={indexed_ids} vs unindexed={unindexed_ids}"

        # Verify max_candidates_per_material slicing equivalence
        for cap in [1, 2, 5]:
            assert indexed_ids[:cap] == unindexed_ids[:cap]
