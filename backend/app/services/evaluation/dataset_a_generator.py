import csv
import json
import random
import re
from pathlib import Path


INPUT = Path("data/processed/ntpc_materials_enriched.csv")
OUTPUT_DIR = Path("data/evaluation")

SEED = 26099

DEV_SIZE = 500
HELDOUT_SIZE = 500
NEGATIVES_PER_SPLIT = 250
REAL_CONFLICT_POOL = 300


SPEC_FIELDS = [
    "material_grade",
    "pressure_rating",
    "voltage_class",
    "dimensions",
    "nominal_bore",
    "metric_thread",
]


def load_materials():
    with INPUT.open(encoding="utf-8", newline="") as f:
        materials = list(csv.DictReader(f))

    for material in materials:
        material["parsed_specifications"] = json.loads(
            material.get("parsed_specifications") or "{}"
        )

    return materials


def clean(text):
    return re.sub(r"\s+", " ", (text or "").strip())


def has_value(value):
    if value is None:
        return False

    if isinstance(value, str):
        return bool(value.strip())

    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)

    return True


def normalize_key(text):
    return re.sub(
        r"[^A-Z0-9]+",
        "",
        clean(text).upper(),
    )


def tokenize(text):
    return set(
        re.findall(
            r"[A-Z0-9]+(?:\.[A-Z0-9]+)?",
            clean(text).upper(),
        )
    )


def token_similarity(a, b):
    ta = tokenize(a)
    tb = tokenize(b)

    if not ta or not tb:
        return 0.0

    return len(ta & tb) / len(ta | tb)


def specs_conflict(a, b):
    sa = a.get("parsed_specifications") or {}
    sb = b.get("parsed_specifications") or {}

    conflicts = []

    for field in SPEC_FIELDS:
        va = sa.get(field)
        vb = sb.get(field)

        if has_value(va) and has_value(vb) and va != vb:
            conflicts.append(field)

    return conflicts


# ------------------------------------------------------------------
# POSITIVE GENERATION
# ------------------------------------------------------------------

def transform_case(text):
    return text.lower()


def transform_punctuation(text):
    text = re.sub(r"\s*,\s*", " ", text)
    text = re.sub(r"\s*:\s*", " ", text)
    text = re.sub(r"\s*-\s*", " ", text)
    return clean(text)


def transform_whitespace(text):
    return re.sub(r"\s+", "  ", text).strip()


def transform_common_abbreviations(text):
    replacements = [
        (r"\bASSEMBLY\b", "ASSY"),
        (r"\bASSY\b", "ASSEMBLY"),
        (r"\bSTAINLESS STEEL\b", "SS"),
        (r"\bMILD STEEL\b", "MS"),
        (r"\bTHICKNESS\b", "THK"),
        (r"\bDIAMETER\b", "DIA"),
        (r"\bNUMBER\b", "NO"),
    ]

    result = text

    for pattern, replacement in replacements:
        result = re.sub(
            pattern,
            replacement,
            result,
            count=1,
            flags=re.IGNORECASE,
        )

    return result


def transform_units(text):
    result = text

    result = re.sub(
        r"(\d+(?:\.\d+)?)MM",
        r"\1 MM",
        result,
        flags=re.IGNORECASE,
    )

    result = re.sub(
        r"(\d+(?:\.\d+)?)KV",
        r"\1 KV",
        result,
        flags=re.IGNORECASE,
    )

    result = re.sub(
        r"(\d+(?:\.\d+)?)V\b",
        r"\1 V",
        result,
        flags=re.IGNORECASE,
    )

    return clean(result)


def transform_reorder(text):
    parts = [
        part.strip()
        for part in re.split(r"[:,]", text)
        if part.strip()
    ]

    if len(parts) < 3:
        return None

    # Move the first attribute to the end.
    return " ".join(parts[1:] + parts[:1])


def generate_positive_variant(text, variant_id):
    transforms = [
        transform_case,
        transform_punctuation,
        transform_whitespace,
        transform_common_abbreviations,
        transform_units,
        transform_reorder,
    ]

    result = transforms[variant_id % len(transforms)](text)

    if result is None:
        return None

    if clean(result) == clean(text):
        return None

    return result


def build_positive(material, pair_id, variant_id):
    source = clean(material["description"])

    target = generate_positive_variant(
        source,
        variant_id,
    )

    if target is None:
        return None

    return {
        "pair_id": pair_id,
        "source_material_code": material["material_code"],
        "target_material_code": f"SYNTH_{pair_id:06d}",
        "source_description": source,
        "target_description": target,
        "source_specs": json.dumps(
            material["parsed_specifications"],
            ensure_ascii=False,
        ),
        "target_specs": json.dumps(
            material["parsed_specifications"],
            ensure_ascii=False,
        ),
        "ground_truth": "SAME",
        "generation_type": "controlled_positive",
        "transformation": (
            f"variant_{variant_id % 6}"
        ),
    }


# ------------------------------------------------------------------
# CONTROLLED NEGATIVE GENERATION
# ------------------------------------------------------------------

def mutate_numeric_attribute(text, rng):
    """
    Change a clearly numeric technical token.

    This is only accepted when the description contains
    an obvious numeric specification.
    """

    pattern = re.compile(
        r"(?<![A-Z0-9])(\d+(?:\.\d+)?)(MM|NB|KV|V|A|PSI)\b",
        re.IGNORECASE,
    )

    matches = list(pattern.finditer(text))

    if not matches:
        return None

    match = rng.choice(matches)

    old_value = float(match.group(1))
    unit = match.group(2)

    if old_value == 0:
        new_value = 1
    elif old_value < 10:
        new_value = old_value * 2
    else:
        new_value = old_value / 2

    if new_value.is_integer():
        replacement = f"{int(new_value)}{unit}"
    else:
        replacement = f"{new_value:g}{unit}"

    return (
        text[:match.start()]
        + replacement
        + text[match.end():]
    )


def mutate_grade(text, rng):
    replacements = [
        (r"\bSS\s*304\b", "SS316"),
        (r"\bSS\s*316\b", "SS304"),
        (r"\bSA516\s*GR\s*70\b", "SA387 GR12"),
        (r"\bSA387\s*GR\s*12\b", "SA516 GR70"),
    ]

    for pattern, replacement in replacements:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return re.sub(
                pattern,
                replacement,
                text,
                count=1,
                flags=re.IGNORECASE,
            )

    return None


def mutate_dimension(text, rng):
    pattern = re.compile(
        r"(\d+(?:\.\d+)?)\s*[Xx]\s*(\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )

    match = pattern.search(text)

    if not match:
        return None

    first = float(match.group(1))
    second = float(match.group(2))

    new_first = first * 2 if first != 0 else 1

    if new_first.is_integer():
        first_text = str(int(new_first))
    else:
        first_text = f"{new_first:g}"

    return (
        text[:match.start()]
        + f"{first_text}X{second:g}"
        + text[match.end():]
    )


def build_mutated_negative(material, pair_id, rng):
    source = clean(material["description"])

    mutation_functions = [
        ("numeric_attribute_mutation", mutate_numeric_attribute),
        ("grade_mutation", mutate_grade),
        ("dimension_mutation", mutate_dimension),
    ]

    rng.shuffle(mutation_functions)

    for name, function in mutation_functions:
        target = function(source, rng)

        if target is None:
            continue

        if normalize_key(target) == normalize_key(source):
            continue

        return {
            "pair_id": pair_id,
            "source_material_code": material["material_code"],
            "target_material_code": f"MUTATED_{pair_id:06d}",
            "source_description": source,
            "target_description": target,
            "source_specs": json.dumps(
                material["parsed_specifications"],
                ensure_ascii=False,
            ),
            "target_specs": json.dumps(
                material["parsed_specifications"],
                ensure_ascii=False,
            ),
            "ground_truth": "DIFFERENT",
            "generation_type": "controlled_negative",
            "transformation": name,
        }

    return None


# ------------------------------------------------------------------
# REAL RECORD HARD NEGATIVES
# ------------------------------------------------------------------

def build_real_conflict_candidates(materials):
    candidates = []

    for i, source in enumerate(materials):
        for j in range(i + 1, len(materials)):
            target = materials[j]

            conflicts = specs_conflict(
                source,
                target,
            )

            if not conflicts:
                continue

            similarity = token_similarity(
                source["normalized_description"],
                target["normalized_description"],
            )

            if similarity < 0.35:
                continue

            candidates.append(
                (
                    similarity,
                    source,
                    target,
                    conflicts,
                )
            )

    candidates.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    return candidates


def build_real_hard_negative(
    candidate,
    pair_id,
):
    similarity, source, target, conflicts = candidate

    return {
        "pair_id": pair_id,
        "source_material_code": source["material_code"],
        "target_material_code": target["material_code"],
        "source_description": source["description"],
        "target_description": target["description"],
        "source_specs": json.dumps(
            source["parsed_specifications"],
            ensure_ascii=False,
        ),
        "target_specs": json.dumps(
            target["parsed_specifications"],
            ensure_ascii=False,
        ),
        "ground_truth": "DIFFERENT",
        "generation_type": "real_hard_negative",
        "transformation": (
            "high_similarity_structured_conflict"
        ),
        "token_similarity": f"{similarity:.4f}",
        "conflicting_fields": "|".join(conflicts),
    }


# ------------------------------------------------------------------
# OUTPUT
# ------------------------------------------------------------------

def write_csv(path, rows):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fields = [
        "pair_id",
        "source_material_code",
        "target_material_code",
        "source_description",
        "target_description",
        "source_specs",
        "target_specs",
        "ground_truth",
        "generation_type",
        "transformation",
        "token_similarity",
        "conflicting_fields",
    ]

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fields,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)


def main():
    rng = random.Random(SEED)

    materials = load_materials()

    materials = [
        material
        for material in materials
        if clean(material.get("description"))
    ]

    rng.shuffle(materials)

    split_end = DEV_SIZE + HELDOUT_SIZE

    if len(materials) < split_end:
        raise RuntimeError(
            "Not enough materials for requested splits."
        )

    dev_materials = materials[:DEV_SIZE]

    heldout_materials = materials[
        DEV_SIZE:split_end
    ]

    negative_materials = materials[
        split_end:
    ]

    # --------------------------------------------------------------
    # Positive datasets
    # --------------------------------------------------------------

    dev_rows = []

    for index, material in enumerate(dev_materials):
        for attempt in range(6):
            row = build_positive(
                material,
                index,
                attempt,
            )

            if row is not None:
                dev_rows.append(row)
                break

    heldout_rows = []

    for index, material in enumerate(heldout_materials):
        for attempt in range(6):
            row = build_positive(
                material,
                100000 + index,
                attempt,
            )

            if row is not None:
                heldout_rows.append(row)
                break

    # --------------------------------------------------------------
    # Controlled negatives
    # --------------------------------------------------------------

    dev_negative_rows = []

    negative_pool = list(negative_materials)

    rng.shuffle(negative_pool)

    for index, material in enumerate(
        negative_pool[:NEGATIVES_PER_SPLIT]
    ):
        row = build_mutated_negative(
            material,
            300000 + index,
            rng,
        )

        if row is not None:
            dev_negative_rows.append(row)

    heldout_negative_rows = []

    offset = NEGATIVES_PER_SPLIT

    for index, material in enumerate(
        negative_pool[
            offset:offset + NEGATIVES_PER_SPLIT
        ]
    ):
        row = build_mutated_negative(
            material,
            400000 + index,
            rng,
        )

        if row is not None:
            heldout_negative_rows.append(row)

    # --------------------------------------------------------------
    # Real hard negatives
    # --------------------------------------------------------------

    print("Searching for real structured-conflict pairs...")

    conflict_candidates = build_real_conflict_candidates(
        negative_materials
    )

    real_hard_candidates = conflict_candidates[
        :REAL_CONFLICT_POOL
    ]

    real_hard_rows = []

    for index, candidate in enumerate(
        real_hard_candidates
    ):
        real_hard_rows.append(
            build_real_hard_negative(
                candidate,
                500000 + index,
            )
        )

    # --------------------------------------------------------------
    # Save
    # --------------------------------------------------------------

    write_csv(
        OUTPUT_DIR / "dataset_a_dev.csv",
        dev_rows + dev_negative_rows,
    )

    write_csv(
        OUTPUT_DIR / "dataset_a_heldout.csv",
        heldout_rows + heldout_negative_rows,
    )

    write_csv(
        OUTPUT_DIR / "dataset_a_hard_negatives.csv",
        real_hard_rows,
    )

    print("\nDataset A v3 generated")
    print(f"  Source materials:       {len(materials)}")
    print(f"  DEV SAME:               {len(dev_rows)}")
    print(f"  DEV DIFFERENT:          {len(dev_negative_rows)}")
    print(f"  HELD-OUT SAME:          {len(heldout_rows)}")
    print(f"  HELD-OUT DIFFERENT:     {len(heldout_negative_rows)}")
    print(f"  REAL HARD NEGATIVES:    {len(real_hard_rows)}")
    print(f"  Output directory:       {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
