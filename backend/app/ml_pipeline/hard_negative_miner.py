"""Step 2 - Mine hard negatives (the core MIRA differentiator).

Hard negatives are pairs that LOOK similar (same category, high lexical
overlap) but are NOT equivalent because a critical specification differs:

    "BRG BALL 6205 2RS"  vs  "BRG BALL 6305 2RS"      (size)
    "VLV GATE 150NB CS"  vs  "VLV GATE 150NB CS PN25" (pressure)
    "BOLT M16 MS"        vs  "BOLT M16 SS"            (grade)

Lexical similarity must never imply technical equivalence - this dataset
is what teaches the model that.

Output: app/ml_pipeline/data/training/hard_negatives.csv
Format: material_1_desc,material_2_desc,label (label always 0)
"""
from __future__ import annotations

import argparse
import csv
import os
import random
import re
from typing import List, Tuple

from app.services.preprocessing.text_cleaner import clean_description

# Critical field mutation templates: (regex to find, callable that turns the
# match text into a DIFFERENT variant, or None to skip this match).
# Only ONE critical value changes per pair - everything else stays shared.
def _mutate_size(original: str) -> str:
    digits = re.sub(r"\D", "", original)
    if not digits:
        return original
    last = str((int(digits[-1]) + 1) % 10)
    return original[: -len(digits)] + digits[:-1] + last if len(digits) > 1 else digits + last


def _mutate_nb_mm(original: str) -> str:
    digits = re.sub(r"\D", "", original)
    if not digits:
        return original
    value = int(digits)
    new_value = {50: 80, 80: 100, 100: 150, 150: 200, 200: 50}.get(value, value + 25)
    unit = "NB" if "NB" in original.upper() else "MM"
    return f"{new_value}{unit}"


def _mutate_pressure(original: str) -> str:
    digits = re.sub(r"\D", "", original)
    if not digits:
        return original
    value = int(digits)
    new_value = {10: 16, 16: 25, 25: 40, 40: 10}.get(value, value + 5)
    return f"PN{new_value}" if "PN" in original.upper() else f"{new_value} BAR"


def _mutate_voltage(original: str) -> str:
    digits = re.sub(r"\D", "", original)
    if not digits:
        return original
    value = int(digits)
    new_value = {3: 6, 6: 11, 11: 33, 33: 11}.get(value, value + 3)
    return f"{new_value}KV" if "K" in original.upper() else f"{new_value}V"


def _mutate_grade(original: str) -> str:
    grades = ["CARBON STEEL", "MILD STEEL", "STAINLESS STEEL"]
    for grade in grades:
        if grade in original.upper():
            others = [g for g in grades if g != grade]
            return original.replace(grade, others[0], 1)
    return original


def _mutate_thread(original: str) -> str:
    digits = re.sub(r"\D", "", original)
    if not digits:
        return original
    value = int(digits)
    new_value = {12: 16, 16: 20, 20: 24, 24: 12}.get(value, value + 4)
    prefix = original[: original.upper().find(digits)].strip() or "M"
    return f"{prefix}{new_value}"


_MUTATIONS: List[Tuple[str, callable]] = [
    (r"\bPN\s*\d{1,2}\b", _mutate_pressure),
    (r"\b\d{1,2}\s*KV\b", _mutate_voltage),
    (r"\b(CARBON STEEL|MILD STEEL|STAINLESS STEEL)\b", _mutate_grade),
    (r"\bM\d{1,2}\b", _mutate_thread),
    (r"\b\d{1,3}\s*(?:NB|MM)\b", _mutate_nb_mm),
    (r"\b\d{4}\b", _mutate_size),
]


def _mutate_critical(description: str, rng: random.Random) -> Tuple[str, bool]:
    """Change exactly one critical value to a different variant."""
    order = list(_MUTATIONS)
    rng.shuffle(order)
    for pattern, mutate in order:
        match = re.search(pattern, description, re.IGNORECASE)
        if not match:
            continue
        replacement = mutate(match.group(0))
        if replacement and replacement.upper() != match.group(0).upper():
            new_description = (
                description[: match.start()] + replacement + description[match.end():]
            )
            if clean_description(new_description) != clean_description(description):
                return new_description, True
    return description, False


def mine_hard_negatives(
    sources: List[Tuple[str, str]],
    count: int = 800,
    seed: int = 7,
) -> List[Tuple[str, str, int]]:
    """Create hard-negative pairs from seed (description, category) pairs.

    ``sources`` should be seed materials; pairs are built as
    (original, single-critical-field-mutant) - same category by
    construction, different ground-truth material.
    """
    rng = random.Random(seed)
    pairs: List[Tuple[str, str, int]] = []
    seen = set()
    attempts = 0
    while len(pairs) < count and attempts < count * 40:
        attempts += 1
        base, _category = sources[rng.randrange(len(sources))]
        mutated, ok = _mutate_critical(base, rng)
        if not ok:
            continue
        d1, d2 = clean_description(base), clean_description(mutated)
        key = tuple(sorted((d1, d2)))
        if key in seen or d1 == d2:
            continue
        seen.add(key)
        pairs.append((d1, d2, 0))
    return pairs


_DEFAULT_SEEDS: List[Tuple[str, str]] = [
    # Bearings (size-code mutations)
    ("BRG BALL 6205 2RS", "Bearing"),
    ("BRG BALL 6305 ZZ", "Bearing"),
    ("BRG BALL 6206 2RS", "Bearing"),
    ("BRG BALL 6204 2Z", "Bearing"),
    ("BEARING TAPERED ROLLER 32210 C3", "Bearing"),
    ("BEARING TAPERED ROLLER 32212 C3", "Bearing"),
    ("BEARING CILINDRICAL ROLLER NU210", "Bearing"),
    ("BEARING NEEDLE K80140", "Bearing"),
    ("BEARING SLEEVE 1216", "Bearing"),
    # Valves (pressure / size mutations)
    ("VLV GATE 150NB CS PN16", "Valve"),
    ("VLV GLOBE 150NB CS PN16", "Valve"),
    ("GATE VALVE 100NB CARBON STEEL PN16", "Valve"),
    ("VLV BALL 50NB SS PN25", "Valve"),
    ("CHECK VALVE 200NB CARBON STEEL PN16", "Valve"),
    ("BUTTERFLY VALVE 80NB CS PN10", "Valve"),
    ("GLOBE VALVE 50NB STAINLESS STEEL PN25", "Valve"),
    # Pipes (bore mutations)
    ("PIPE SCH40 2 INCH CS", "Pipe"),
    ("PIPE DN50 SCHEDULE 40 CS", "Pipe"),
    ("PIPE 150NB GALVANIZED", "Pipe"),
    ("STEEL PIPE DN80 SCHEDULE 40", "Pipe"),
    ("PIPE 89MM CARBON STEEL", "Pipe"),
    # Fasteners (thread / grade mutations)
    ("BOLT M16 X 60 MS GR8.8", "Fastener"),
    ("HEX BOLT M20 X 80 CS GR10.9", "Fastener"),
    ("HEX BOLT M24 X 100 CS GR8.8", "Fastener"),
    ("NUT HEX M16 MS", "Fastener"),
    ("STUD M20 X 120 CS", "Fastener"),
    ("WASHER FLAT 150NB SS", "Gasket"),
    ("GASKET FLAT 100NB CS", "Gasket"),
    # Electrical (voltage mutations)
    ("CABLE 3X2.5 SQMM COPPER", "Cable"),
    ("CABLE 4X4 SQMM COPPER", "Cable"),
    ("CONNECTOR 11KV ALUMINIUM", "Electrical Connector"),
    ("CONNECTOR 33KV COPPER", "Electrical Connector"),
    ("SWITCH 11KV VACUUM", "Switch"),
    ("CONTACTOR 6.6KV", "Contact"),
    ("TRANSFORMER 33KV 500KVA", "Transformer"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine hard-negative training pairs")
    parser.add_argument("--count", type=int, default=800)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    out_dir = args.output_dir or os.path.join(os.path.dirname(__file__), "data", "training")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "hard_negatives.csv")

    pairs = mine_hard_negatives(_DEFAULT_SEEDS, count=args.count, seed=args.seed)
    with open(out_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["material_1_desc", "material_2_desc", "label"])
        writer.writerows(pairs)

    print(f"Wrote {len(pairs)} hard negatives (seed={args.seed}) -> {out_path}")


if __name__ == "__main__":
    main()

