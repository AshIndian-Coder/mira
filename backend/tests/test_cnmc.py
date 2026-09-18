import pytest
from app import store
from app.services.cnmc.canonicalization import (
    build_canonical_identity_string,
    compute_identity_hash,
)
from app.services.cnmc.service import generate_or_get_cnmc
from app.services.cnmc.taxonomy import resolve_type_and_category
from app.services.harmonization.service import build_common_material_record


@pytest.fixture(autouse=True)
def clean_db():
    store.reset_stores()
    yield
    store.reset_stores()


def make_material_record(
    material_id: int,
    cpse: str,
    code: str,
    description: str,
    *,
    category: str = "Valve",
    material_grade: str | None = "SS304",
    pressure_rating: dict | None = None,
    dimensions: dict | None = None,
    nominal_bore: dict | None = None,
    schedule: str | None = None,
):
    parsed = {}
    if material_grade:
        parsed["material_grade"] = material_grade
    if pressure_rating:
        parsed["pressure_rating"] = pressure_rating
    if dimensions:
        parsed["dimensions"] = dimensions
    if nominal_bore:
        parsed["nominal_bore"] = nominal_bore
    if schedule:
        parsed["schedule"] = schedule

    return {
        "id": material_id,
        "cpse": cpse,
        "material_code": code,
        "description": description,
        "normalized_description": description.upper(),
        "category": category,
        "material_grade": material_grade,
        "dimensions": dimensions,
        "parsed_specifications": parsed,
        "specifications": {},
        "source_file": f"{cpse}.csv",
        "source_page": 1,
    }


def test_first_new_material_receives_cnmc():
    """1. First new material receives a CNMC."""
    mat = make_material_record(
        1, "NTPC", "NTPC-001", "SS 304 GATE VALVE 2 IN 150 LB",
        category="Valve",
        material_grade="SS304",
        pressure_rating={"value": 150.0, "unit": "LB"},
        dimensions={"value": 2.0, "unit": "IN"},
    )
    cmr = build_common_material_record([mat])
    cnmc_info = generate_or_get_cnmc([mat], cmr)

    assert cnmc_info is not None
    assert cnmc_info["is_new"] is True
    assert cnmc_info["global_id"] == 1


def test_cnmc_format_and_no_leading_zero_padding():
    """2 & 3. CNMC follows MIRA-TYPE-CATEGORY-GLOBAL_ID and has no artificial fixed-width zero padding."""
    mat = make_material_record(
        1, "NTPC", "NTPC-001", "GATE VALVE CS 150 NB 80",
        category="Valve",
        material_grade="CS",
        pressure_rating={"value": 150.0, "unit": "LB"},
        nominal_bore={"value": 80.0, "unit": "MM"},
    )
    cmr = build_common_material_record([mat])
    cnmc_info = generate_or_get_cnmc([mat], cmr)

    code = cnmc_info["cnmc_code"]
    parts = code.split("-")
    assert len(parts) == 4
    assert parts[0] == "MIRA"
    assert parts[1] == "VLV"
    assert parts[2] == "17"
    assert parts[3] == "1"  # Not 000001 or 001
    assert code == "MIRA-VLV-17-1"


def test_global_id_increments_across_categories():
    """4. Global ID increments monotonically across different categories."""
    valve_mat = make_material_record(
        1, "NTPC", "VALVE-01", "GATE VALVE 150 LB",
        category="Valve",
        material_grade="SS304",
        pressure_rating={"value": 150.0, "unit": "LB"},
    )
    pipe_mat = make_material_record(
        2, "BHEL", "PIPE-01", "SEAMLESS PIPE 2 IN SCH 40",
        category="Pipe",
        material_grade="A106",
        dimensions={"value": 2.0, "unit": "IN"},
        schedule="40",
    )
    bearing_mat = make_material_record(
        3, "IOCL", "BRG-01", "ROLLER BEARING 50 MM",
        category="Bearing",
        material_grade=None,
        dimensions={"value": 50.0, "unit": "MM"},
    )

    valve_cmr = build_common_material_record([valve_mat])
    pipe_cmr = build_common_material_record([pipe_mat])
    bearing_cmr = build_common_material_record([bearing_mat])

    valve_cnmc = generate_or_get_cnmc([valve_mat], valve_cmr)
    pipe_cnmc = generate_or_get_cnmc([pipe_mat], pipe_cmr)
    bearing_cnmc = generate_or_get_cnmc([bearing_mat], bearing_cmr)

    assert valve_cnmc["cnmc_code"] == "MIRA-VLV-17-1"
    assert pipe_cnmc["cnmc_code"] == "MIRA-PIP-23-2"
    assert bearing_cnmc["cnmc_code"] == "MIRA-BRG-08-3"

    assert valve_cnmc["global_id"] == 1
    assert pipe_cnmc["global_id"] == 2
    assert bearing_cnmc["global_id"] == 3


def test_same_canonical_identity_reuses_cnmc():
    """5. Same canonical identity returns the SAME CNMC."""
    mat_ntpc = make_material_record(
        1, "NTPC", "NTPC-V1", "GATE VALVE CS 150 NB 80",
        category="Valve",
        material_grade="CS",
        pressure_rating={"value": 150.0, "unit": "LB"},
        nominal_bore={"value": 80.0, "unit": "MM"},
    )
    cmr1 = build_common_material_record([mat_ntpc])
    cnmc1 = generate_or_get_cnmc([mat_ntpc], cmr1)

    mat_bhel = make_material_record(
        2, "BHEL", "BHEL-V99", "GATE VALVE CS 150 NB 80",
        category="Valve",
        material_grade="CS",
        pressure_rating={"value": 150.0, "unit": "LB"},
        nominal_bore={"value": 80.0, "unit": "MM"},
    )
    cmr2 = build_common_material_record([mat_bhel])
    cnmc2 = generate_or_get_cnmc([mat_bhel], cmr2)

    assert cnmc1["cnmc_code"] == cnmc2["cnmc_code"]
    assert cnmc1["global_id"] == cnmc2["global_id"]
    assert cnmc1["identity_hash"] == cnmc2["identity_hash"]
    assert cnmc2["is_new"] is False


def test_different_canonical_identities_receive_different_cnmcs():
    """6. Different canonical identities receive DIFFERENT CNMCs."""
    mat1 = make_material_record(
        1, "NTPC", "V-150", "GATE VALVE CS 150 LB",
        category="Valve",
        material_grade="CS",
        pressure_rating={"value": 150.0, "unit": "LB"},
    )
    mat2 = make_material_record(
        2, "NTPC", "V-300", "GATE VALVE CS 300 LB",
        category="Valve",
        material_grade="CS",
        pressure_rating={"value": 300.0, "unit": "LB"},
    )

    cmr1 = build_common_material_record([mat1])
    cmr2 = build_common_material_record([mat2])

    cnmc1 = generate_or_get_cnmc([mat1], cmr1)
    cnmc2 = generate_or_get_cnmc([mat2], cmr2)

    assert cnmc1["cnmc_code"] != cnmc2["cnmc_code"]
    assert cnmc1["global_id"] != cnmc2["global_id"]
    assert cnmc1["identity_hash"] != cnmc2["identity_hash"]


def test_cpse_source_codes_do_not_alter_identity():
    """7. Different CPSE source codes do not alter the identity fingerprint."""
    mat_a = make_material_record(
        100, "IOCL", "IOCL-CODE-XYZ-12345", "BALL VALVE SS316 1000 WOG",
        category="Valve",
        material_grade="SS316",
        pressure_rating={"value": 1000.0, "unit": "PSI"},
    )
    mat_b = make_material_record(
        999, "ONGC", "ONGC-CODE-99999-ABC", "BALL VALVE SS316 1000 WOG",
        category="Valve",
        material_grade="SS316",
        pressure_rating={"value": 1000.0, "unit": "PSI"},
    )

    cmr_a = build_common_material_record([mat_a])
    cmr_b = build_common_material_record([mat_b])

    type_a, cat_a = resolve_type_and_category(cmr_a.get("category"), cmr_a.get("canonical_description"), [mat_a])
    type_b, cat_b = resolve_type_and_category(cmr_b.get("category"), cmr_b.get("canonical_description"), [mat_b])

    ident_a = build_canonical_identity_string(cmr_a, type_a, cat_a)
    ident_b = build_canonical_identity_string(cmr_b, type_b, cat_b)

    assert ident_a == ident_b
    assert compute_identity_hash(ident_a) == compute_identity_hash(ident_b)


def test_missing_attributes_handled_deterministically():
    """8. Missing attributes are handled deterministically without silent coercion."""
    mat1 = make_material_record(
        1, "NTPC", "V1", "GATE VALVE",
        category="Valve",
        material_grade=None,
        pressure_rating=None,
    )
    mat2 = make_material_record(
        2, "BHEL", "V2", "GATE VALVE",
        category="Valve",
        material_grade=None,
        pressure_rating=None,
    )

    cmr1 = build_common_material_record([mat1])
    cmr2 = build_common_material_record([mat2])

    type_1, cat_1 = resolve_type_and_category(cmr1.get("category"), cmr1.get("canonical_description"), [mat1])
    type_2, cat_2 = resolve_type_and_category(cmr2.get("category"), cmr2.get("canonical_description"), [mat2])

    ident_1 = build_canonical_identity_string(cmr1, type_1, cat_1)
    ident_2 = build_canonical_identity_string(cmr2, type_2, cat_2)

    assert "PRESSURE_RATING:UNKNOWN" in ident_1
    assert "MATERIAL_GRADE:UNKNOWN" in ident_1
    assert ident_1 == ident_2


def test_source_cpse_mappings_and_cmr_remain_intact():
    """9, 10, 11. Source CPSE mappings, CMR and cluster generation remain intact."""
    mat1 = make_material_record(10, "NTPC", "NTPC-VALVE-1", "SS304 GATE VALVE 2 IN 150 LB")
    mat2 = make_material_record(20, "BHEL", "BHEL-VALVE-2", "SS304 GATE VALVE 2 IN 150 LB")

    cmr = build_common_material_record([mat1, mat2])
    cnmc_info = generate_or_get_cnmc([mat1, mat2], cmr)

    assert cmr["provenance"]["source_count"] == 2
    assert cmr["provenance"]["material_ids"] == [10, 20]
    assert cnmc_info["cnmc_code"] == "MIRA-VLV-17-1"


def test_concurrent_cnmc_generation_unique_ids():
    """13. Concurrent/new registry allocation cannot create duplicate global IDs."""
    import concurrent.futures

    def allocate_material(idx: int):
        mat = make_material_record(
            idx,
            "CPSE_TEST",
            f"CODE-{idx}",
            f"SPECIAL VALVE SPECIFICATION {idx} 150 LB",
            category="Valve",
            material_grade=f"SS{300 + idx}",
            pressure_rating={"value": 150.0 + idx, "unit": "LB"},
        )
        cmr = build_common_material_record([mat])
        return generate_or_get_cnmc([mat], cmr)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(allocate_material, range(1, 11)))

    global_ids = [r["global_id"] for r in results]
    cnmc_codes = [r["cnmc_code"] for r in results]

    # Uniqueness check
    assert len(global_ids) == len(set(global_ids))
    assert len(cnmc_codes) == len(set(cnmc_codes))
    assert set(global_ids) == set(range(1, 11))

