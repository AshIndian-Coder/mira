from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MaterialForBlocking:
    id: int
    category: str | None
    normalized_description: str
    material_grade: str | None = None
    manufacturer_part_number: str | None = None


def _token_set(text: str) -> set[str]:
    return {
        token
        for token in text.upper().split()
        if token
    }


def generate_block_keys(material: MaterialForBlocking) -> set[str]:
    """
    Generate deterministic blocking keys.

    Blocking only narrows the candidate space.
    It does NOT determine whether two materials match.
    """

    keys: set[str] = set()

    category = (material.category or "").strip().upper()
    grade = (material.material_grade or "").strip().upper()
    part_number = (
        (material.manufacturer_part_number or "")
        .strip()
        .upper()
    )

    tokens = _token_set(material.normalized_description)

    # Strong identity block when manufacturer part number exists.
    if part_number:
        keys.add(f"MPN:{part_number}")

    # Category-level block.
    if category:
        keys.add(f"CAT:{category}")

    # Category + grade block.
    if category and grade:
        keys.add(f"CAT_GRADE:{category}:{grade}")

    # A small set of useful description anchors.
    anchors = {
        "VALVE",
        "PIPE",
        "PUMP",
        "BEARING",
        "BOLT",
        "NUT",
        "CONNECTOR",
        "CABLE",
        "FLANGE",
        "GASKET",
        "FILTER",
        "MOTOR",
    }

    for anchor in anchors.intersection(tokens):
        if category:
            keys.add(f"TYPE:{category}:{anchor}")
        else:
            keys.add(f"TYPE:{anchor}")

    return keys


def generate_candidates(
    source: MaterialForBlocking,
    targets: list[MaterialForBlocking],
) -> list[MaterialForBlocking]:
    """
    Return target materials sharing at least one blocking key
    with the source material.
    """

    source_keys = generate_block_keys(source)

    if not source_keys:
        return []

    candidates = []

    for target in targets:
        if source.id == target.id:
            continue

        target_keys = generate_block_keys(target)

        if source_keys.intersection(target_keys):
            candidates.append(target)

    return candidates
