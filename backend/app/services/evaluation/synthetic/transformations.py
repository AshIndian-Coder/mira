from __future__ import annotations

import random
import re


# Conservative abbreviations commonly found in industrial material descriptions.
ABBREVIATIONS = {
    "stainless steel": "SS",
    "carbon steel": "CS",
    "mild steel": "MS",
    "steel": "STL",
    "aluminium": "AL",
    "aluminum": "AL",
    "copper": "CU",
    "millimeter": "MM",
    "millimetre": "MM",
    "centimeter": "CM",
    "centimeter": "CM",
    "kilogram": "KG",
    "kilograms": "KG",
    "meter": "M",
    "metre": "M",
    "meters": "M",
    "metres": "M",
}


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def change_case(text: str, rng: random.Random) -> str:
    choice = rng.choice(("upper", "lower", "title"))

    if choice == "upper":
        return text.upper()

    if choice == "lower":
        return text.lower()

    return text.title()


def change_spacing(text: str, rng: random.Random) -> str:
    text = normalize_spaces(text)

    transformations = [
        lambda x: x.replace(" x ", "x"),
        lambda x: x.replace(" X ", "X"),
        lambda x: x.replace(" - ", "-"),
        lambda x: x.replace("/", " / "),
        lambda x: re.sub(r"\s*([,;])\s*", r"\1 ", x),
    ]

    return normalize_spaces(rng.choice(transformations)(text))


def abbreviate_terms(text: str) -> str:
    result = text

    # Longer phrases first so "stainless steel" is processed before "steel".
    for source, replacement in sorted(
        ABBREVIATIONS.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        result = re.sub(
            rf"\b{re.escape(source)}\b",
            replacement,
            result,
            flags=re.IGNORECASE,
        )

    return normalize_spaces(result)


def remove_punctuation(text: str) -> str:
    result = re.sub(r"[,;:]+", " ", text)
    result = re.sub(r"[()]+", " ", result)
    return normalize_spaces(result)


def reorder_tokens(text: str, rng: random.Random) -> str:
    tokens = normalize_spaces(text).split()

    # Don't reorder very short descriptions.
    if len(tokens) < 4:
        return text

    rng.shuffle(tokens)
    return " ".join(tokens)


def generate_variation(
    description: str,
    rng: random.Random,
) -> tuple[str, list[str]]:
    """
    Generate one conservative synthetic variation.

    Returns:
        (variation, transformations_applied)
    """
    result = normalize_spaces(description)
    applied: list[str] = []

    operations = [
        ("case", lambda value: change_case(value, rng)),
        ("abbreviation", abbreviate_terms),
        ("spacing", lambda value: change_spacing(value, rng)),
        ("punctuation", remove_punctuation),
    ]

    rng.shuffle(operations)

    # Apply 1–3 transformations.
    number_of_operations = rng.randint(1, min(3, len(operations)))

    for name, operation in operations[:number_of_operations]:
        updated = operation(result)

        if updated != result:
            result = updated
            applied.append(name)

    return result, applied
