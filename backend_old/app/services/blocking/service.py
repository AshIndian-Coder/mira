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


def generate_candidates(source, targets):

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
