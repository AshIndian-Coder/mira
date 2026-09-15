"""
Step 1 - Generate synthetic positive training pairs.

Builds equivalent-material pairs from seed materials by applying *safe*
transformations only:
  * abbreviation swaps      (BRG <-> BEARING, VLV <-> VALVE, ...)
  * word-order shuffles
  * unit notations          (150NB <-> 150MM, DN150 <-> 150MM)
  * case/punctuation variants

CRITICAL RULE: technical values (sizes, ratings, grades, standards) are
NEVER mutated - that would manufacture false positives.

Output: app/ml_pipeline/data/training/synthetic_pairs.csv
Format: material_1_desc,material_2_desc,label
"""
from __future__ import annotations

import argparse
import csv
import os
import random
from typing import List, Tuple

from app.services.preprocessing.abbreviation_expander import ABBREVIATION_MAP, expand_abbreviations
from app.services.preprocessing.text_cleaner import clean_description

SEED_MATERIALS: List[Tuple[str, str]] = [
    ("BEARING BALL 6205 2RS", "Bearing"),
    ("BEARING BALL 6305 2RS", "Bearing"),
    ("BEARING TAPERED ROLLER 32210", "Bearing"),
    ("BEARING NEEDLE K80140", "Bearing"),
    ("VALVE GATE 150NB CARBON STEEL PN16", "Valve"),
    ("VALVE GLOBE 100NB CARBON STEEL PN25", "Valve"),
    ("VALVE BALL 50NB STAINLESS STEEL PN40", "Valve"),
    ("VALVE CHECK 200NB CARBON STEEL PN16", "Valve"),
    ("PIPE SCH40 2 INCH CARBON STEEL", "Pipe"),
    ("PIPE DN50 SCHEDULE 40 CARBON STEEL", "Pipe"),
    ("PIPE 89MM GALVANIZED STEEL", "Pipe"),
    ("BOLT M16 X 60 MILD STEEL GRADE 8.8", "Fastener"),
    ("HEXAGON BOLT M20 X 80 CARBON STEEL GRADE 10.9", "Fastener"),
    ("NUT HEX M16 MILD STEEL", "Fastener"),
    ("WASHER SPRING M16 STAINLESS STEEL", "Fastener"),
    ("GASKET FLAT 150NB MILD STEEL", "Gasket"),
    ("SPRING COMPRESSION 20MM STAINLESS STEEL", "Spring"),
    ("FILTER 25MM CARTRIDGE", "Filter"),
    ("CABLE POWER 3 CORE 2.5 SQMM COPPER", "Cable"),
    ("CONNECTOR ELECTRICAL 11KV", "Electrical Connector"),
]

ABBREV_TO_FULL = {k: v for k, v in ABBREVIATION_MAP.items() if k != v}
FULL_TO_ABBREV = {v: k for k, v in ABBREV_TO_FULL.items()}


def _swap_abbreviations(description: str, rng: random.Random) -> str:
    """Replace a few full terms by abbreviations (or the reverse)."""
    text = description
    candidates = []
    for full, abbr in FULL_TO_ABBREV.items():
        if full in text:
            candidates.append((full, abbr))
    for abbr, full in ABBREV_TO_FULL.items():
        if f" {abbr} " in f" {text} " and abbr not in text.split():
            candidates.append((abbr, full))
    rng.shuffle(candidates)
    for old, new in candidates[:2]:
        text = text.replace(old, new)
    return text


def _shuffle_words(description: str, rng: random.Random) -> str:
    """Move up to 2 non-critical tokens (not attached to numbers)."""
    tokens = description.split()
    movable = [i for i, tok in enumerate(tokens) if not any(ch.isdigit() for ch in tok)]
    rng.shuffle(movable)
    moves = 0
    for i in movable:
        if moves >= 2:
            break
        if i > 0:
            tokens[i], tokens[i - 1] = tokens[i - 1], tokens[i]
            moves += 1
    return " ".join(tokens)


def _unit_variant(description: str, rng: random.Random) -> str:
    variants = [
        ("150NB", "150MM"),
        ("150MM", "DN150"),
        ("DN150", "150NB"),
        ("2 INCH", "50MM"),
        ("50MM", "2 INCH"),
    ]
    for old, new in variants:
        if old in description:
            return description.replace(old, new, 1) if rng.random() < 0.5 else description
    return description


def _case_variant(description: str) -> str:
    return description.title()


def generate_pairs(
    count: int = 2000,
    seed: int = 42,
    negative_ratio: float = 0.3,
) -> List[Tuple[str, str, int]]:
    """Generate (desc1, desc2, label) pairs.

    Positive pairs: two transformations of the same seed material.
    Negative pairs: materials from different ground-truth groups
    (same-category preferred for difficulty).
    """
    rng = random.Random(seed)
    pairs: List[Tuple[str, str, int]] = []
    seen = set()
    positive_target = int(count * (1 - negative_ratio))
    negative_target = count - positive_target

    def _add(desc1: str, desc2: str, label: int) -> bool:
        d1, d2 = clean_description(desc1), clean_description(desc2)
        if not d1 or not d2 or d1 == d2:
            return False
        key = tuple(sorted((d1, d2)))
        if key in seen:
            return False
        seen.add(key)
        pairs.append((d1, d2, label))
        return True

    attempts = 0
    while len([p for p in pairs if p[2] == 1]) < positive_target and attempts < positive_target * 20:
        attempts += 1
        base, _category = SEED_MATERIALS[rng.randrange(len(SEED_MATERIALS))]
        view_1 = _swap_abbreviations(base, rng)
        view_2 = _shuffle_words(base, rng)
        if rng.random() < 0.5:
            view_1 = _unit_variant(view_1, rng)
        else:
            view_2 = _unit_variant(view_2, rng)
        if rng.random() < 0.2:
            view_1 = _case_variant(view_1)
        _add(view_1, view_2, 1)

    by_category: dict = {}
    for base, category in SEED_MATERIALS:
        by_category.setdefault(category, []).append(base)
    categories = list(by_category)
    attempts = 0
    while len([p for p in pairs if p[2] == 0]) < negative_target and attempts < negative_target * 20:
        attempts += 1
        cat = rng.choice(categories)
        siblings = by_category.get(cat, [base for base, _ in SEED_MATERIALS])
        if len(siblings) < 2:
            continue
        a, b = rng.sample(siblings, 2)
        if a == b:
            continue
        _add(_swap_abbreviations(a, rng), _shuffle_words(b, rng), 0)

    return pairs[:count]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic training pairs")
    parser.add_argument("--count", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    out_dir = args.output_dir or os.path.join(os.path.dirname(__file__), "data", "training")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "synthetic_pairs.csv")

    pairs = generate_pairs(count=args.count, seed=args.seed)
    with open(out_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["material_1_desc", "material_2_desc", "label"])
        writer.writerows(pairs)

    positives = sum(1 for p in pairs if p[2] == 1)
    print(
        f"Wrote {len(pairs)} pairs ({positives} positive / {len(pairs) - positives} negative) "
        f"seed={args.seed} -> {out_path}"
    )


if __name__ == "__main__":
    main()
