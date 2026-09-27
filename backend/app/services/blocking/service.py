from dataclasses import dataclass
import re


@dataclass(frozen=True)
class MaterialForBlocking:
    id: int
    category: str | None
    normalized_description: str
    material_grade: str | None = None
    manufacturer_part_number: str | None = None


STOPWORDS = {
    "THE",
    "AND",
    "FOR",
    "WITH",
    "FROM",
    "PART",
    "PARTS",
    "ITEM",
    "TYPE",
    "NO",
    "NUMBER",
    "ASSY",
    "ASSEMBLY",
    "SET",
    "UNIT",
    "MAKE",
    "MODEL",
    "SEAL",
    "KIT",
    "SET",
    "ASSLY",
    "ASSY",
}


ANCHORS = {
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
    "DISHED",
    "ELLIP",
    "SUSPENSION",
    "RIM",
    "WEDGE",
    "HUB",
    "SEAL",
    "DRIVER",
    "SEAT",
}


def _token_set(text: str) -> set[str]:
    tokens = re.findall(
        r"[A-Z0-9]+(?:[.:/-][A-Z0-9]+)*",
        text.upper(),
    )

    return {
        token
        for token in tokens
        if token and token not in STOPWORDS
    }


def generate_block_keys(
    material: MaterialForBlocking,
) -> set[str]:

    keys = set()

    category = (
        (material.category or "")
        .strip()
        .upper()
    )

    grade = (
        (material.material_grade or "")
        .strip()
        .upper()
    )

    part_number = (
        (material.manufacturer_part_number or "")
        .strip()
        .upper()
    )

    tokens = _token_set(
        material.normalized_description
    )

    # Strong identifiers.
    if part_number:
        keys.add(f"MPN:{part_number}")

    if category:
        keys.add(f"CAT:{category}")

    if category and grade:
        keys.add(
            f"CAT_GRADE:{category}:{grade}"
        )

    # Category + technical anchor.
    for anchor in ANCHORS.intersection(tokens):
        if category:
            keys.add(
                f"TYPE:{category}:{anchor}"
            )

    # Fallback lexical blocking.
    #
    # Only technical-looking / sufficiently
    # distinctive tokens are used here.
    for token in tokens:

        if len(token) < 4:
            continue

        # Ignore pure short numbers.
        if token.isdigit() and len(token) < 5:
            continue

        keys.add(f"DESC:{token}")

    return keys


def build_block_index(
    materials: list[MaterialForBlocking],
) -> dict[str, list[int]]:
    """Build an inverted block index mapping each block key to a list of material IDs."""
    block_index: dict[str, list[int]] = {}
    for material in materials:
        for key in generate_block_keys(material):
            block_index.setdefault(key, []).append(material.id)
    return block_index


def generate_candidates(
    source: MaterialForBlocking,
    targets: list[MaterialForBlocking] | None = None,
    *,
    block_index: dict[str, list[int]] | None = None,
    target_map: dict[int, MaterialForBlocking] | None = None,
    target_order: dict[int, int] | None = None,
    source_keys: set[str] | None = None,
) -> list[MaterialForBlocking]:
    """
    Generate candidate target materials that share at least one block key with source.

    If block_index is provided, uses inverted index lookup for O(1) candidate retrieval
    without recomputing target block keys. Otherwise falls back to evaluating targets directly.
    """
    if source_keys is None:
        source_keys = generate_block_keys(source)

    if not source_keys:
        return []

    if block_index is not None:
        if target_map is None:
            if targets is None:
                raise ValueError(
                    "Either target_map or targets must be provided when block_index is used"
                )
            target_map = {t.id: t for t in targets}

        key_counts: dict[int, int] = {}
        for key in source_keys:
            for tid in block_index.get(key, ()):
                if tid != source.id and tid in target_map:
                    key_counts[tid] = key_counts.get(tid, 0) + 1

        if not key_counts:
            return []

        if target_order is not None:
            sorted_ids = sorted(
                key_counts.keys(),
                key=lambda tid: (-key_counts[tid], target_order.get(tid, 0)),
            )
        elif targets is not None:
            order_map = {t.id: i for i, t in enumerate(targets)}
            sorted_ids = sorted(
                key_counts.keys(),
                key=lambda tid: (-key_counts[tid], order_map.get(tid, 0)),
            )
        else:
            sorted_ids = sorted(
                key_counts.keys(),
                key=lambda tid: (-key_counts[tid], tid),
            )

        return [target_map[tid] for tid in sorted_ids]

    if targets is None:
        return []

    scored_candidates = []

    for idx, target in enumerate(targets):
        if source.id == target.id:
            continue

        target_keys = generate_block_keys(target)
        overlap = len(source_keys.intersection(target_keys))

        if overlap > 0:
            scored_candidates.append((overlap, idx, target))

    scored_candidates.sort(key=lambda x: (-x[0], x[1]))
    return [c[2] for c in scored_candidates]
