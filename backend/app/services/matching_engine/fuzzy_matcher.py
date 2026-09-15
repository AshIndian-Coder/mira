"""String similarity metrics (typo/spelling robustness).

Pure Python (stdlib only):
  * normalized Levenshtein distance
  * Jaccard token overlap
  * token-sort ratio (order-insensitive SequenceMatcher)

``calculate_fuzzy_score`` blends them into the single 0..1 ``text``
component of the MIRA hybrid score.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import List

_TOKEN_SPLIT = re.compile(r"[\s\-_/.,()]+")


def _tokens(text: str) -> List[str]:
    return [tok for tok in _TOKEN_SPLIT.split((text or "").lower()) if tok]


def levenshtein_distance(a: str, b: str) -> int:
    """Classic edit distance, two-row dynamic programming (O(len(a)*len(b)))."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            insert_cost = current[j - 1] + 1
            delete_cost = previous[j] + 1
            substitute_cost = previous[j - 1] + (0 if ca == cb else 1)
            current.append(min(insert_cost, delete_cost, substitute_cost))
        previous = current
    return previous[-1]


def normalized_levenshtein(a: str, b: str) -> float:
    """1 - distance/max_len, in [0, 1]."""
    if not a and not b:
        return 1.0
    longest = max(len(a), len(b))
    if longest == 0:
        return 1.0
    distance = levenshtein_distance(a, b)
    return 1.0 - (distance / longest)


def jaccard_similarity(a: str, b: str) -> float:
    """Token-level Jaccard overlap."""
    tokens_a, tokens_b = set(_tokens(a)), set(_tokens(b))
    if not tokens_a and not tokens_b:
        return 1.0
    union = tokens_a | tokens_b
    if not union:
        return 1.0
    return len(tokens_a & tokens_b) / len(union)


def token_sort_ratio(a: str, b: str) -> float:
    """Order-insensitive similarity over sorted token strings."""
    tokens_a = " ".join(sorted(_tokens(a)))
    tokens_b = " ".join(sorted(_tokens(b)))
    if not tokens_a and not tokens_b:
        return 1.0
    return SequenceMatcher(None, tokens_a, tokens_b).ratio()


def calculate_fuzzy_score(text1: str, text2: str) -> float:
    """Blended text similarity in [0, 1] (the 0.20-weighted MIRA component).

    0.45 * normalized Levenshtein
  + 0.35 * token-sort ratio
  + 0.20 * Jaccard overlap
    """
    t1 = (text1 or "").strip().lower()
    t2 = (text2 or "").strip().lower()
    if not t1 and not t2:
        return 1.0
    if not t1 or not t2:
        return 0.0
    score = (
        0.45 * normalized_levenshtein(t1, t2)
        + 0.35 * token_sort_ratio(t1, t2)
        + 0.20 * jaccard_similarity(t1, t2)
    )
    return max(0.0, min(1.0, score))

