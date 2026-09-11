import re
from typing import Any


def extract_part_number(text: str) -> str | None:
    if not text:
        return None

    text = re.sub(r"\s+", " ", text).strip()

    # ---------------------------------------------------------
    # 1. Explicit part-number labels
    #
    # Explicit labels are strong evidence that the following
    # value is an identifier.
    # ---------------------------------------------------------
    explicit_patterns = [
        r"\b(?:P/?N|PART\s*(?:NO|NUMBER)|PT\s*NO)"
        r"\.?\s*[:#\-]?\s*"
        r"([A-Z0-9][A-Z0-9 ./_-]{1,40}?)"
        r"(?=\s+(?:FOR|MODEL|MOC|SL\.?\s*NO|TAG|LOCATION)\b|$)",

        r"\bPART\s*NO\.?\s*[:#\-]?\s*"
        r"([A-Z0-9][A-Z0-9 ./_-]{1,40})",

        r"\bPT\s*NO\.?\s*[:#\-]?\s*"
        r"([A-Z0-9][A-Z0-9 ./_-]{1,40})",
    ]

    for pattern in explicit_patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            value = match.group(1)

            value = re.split(
                r"\s+\b(?:FOR|MODEL|MOC|LOCATION|TAG)\b",
                value,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0]

            cleaned = _clean_identifier(value)

            if cleaned:
                return cleaned

    # ---------------------------------------------------------
    # 2. Embedded alphanumeric identifier
    #
    # Example:
    #   SEAL KIT REAR SUSPENSION,778SU00012
    #
    # We require a reasonably identifier-like structure.
    # ---------------------------------------------------------
    embedded_candidates = re.findall(
        r"(?<![A-Z0-9])"
        r"([0-9]{2,}[A-Z]{1,}[A-Z0-9_-]*)"
        r"(?![A-Z0-9])",
        text.upper(),
    )

    for candidate in embedded_candidates:
        if _looks_like_part_number(candidate):
            return candidate

    # ---------------------------------------------------------
    # 3. Structured unlabelled identifier
    #
    # Example:
    #   DRIVER SEAT 951 OS 02008
    #
    # Requires multiple identifier-like tokens rather than
    # accepting arbitrary technical expressions.
    # ---------------------------------------------------------
    match = re.search(
        r"(?<![A-Z0-9])"
        r"([0-9]{2,}(?:\s+[A-Z]{1,6})+\s+[0-9]{2,})"
        r"(?![A-Z0-9])",
        text.upper(),
    )

    if match:
        candidate = _clean_identifier(match.group(1))

        if _looks_like_part_number(candidate):
            return candidate

    return None


def extract_identifiers(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}

    part_number = extract_part_number(text)

    if part_number:
        result["part_number"] = part_number

    return result


def _clean_identifier(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return value.strip(" :-#.,;")


def _looks_like_part_number(value: str) -> bool:
    """
    Conservative heuristic for unlabeled identifiers.

    A generic identifier should contain both letters and digits,
    but ordinary technical expressions such as 18W-20W should
    not automatically qualify.
    """

    value = value.strip().upper()

    if len(value) < 5 or len(value) > 40:
        return False

    if not re.search(r"[A-Z]", value):
        return False

    if not re.search(r"\d", value):
        return False

    # ---------------------------------------------------------
    # Reject obvious technical measurement/rating expressions.
    # ---------------------------------------------------------
    if re.fullmatch(
        r"\d+(?:\.\d+)?\s*[A-Z]{1,5}"
        r"(?:\s*[-/]\s*\d+(?:\.\d+)?\s*[A-Z]{1,5})?",
        value,
    ):
        return False

    # Common engineering quantity/rating forms.
    if re.fullmatch(
        r"\d+(?:\.\d+)?\s*(?:V|KV|W|KW|MW|HZ|A|MA|BAR|"
        r"MM|CM|M|KG|KVA|VA)",
        value,
    ):
        return False

    # A pure single-token alphanumeric identifier such as
    # 778SU00012 is a strong candidate.
    if re.fullmatch(
        r"\d+[A-Z]+[A-Z0-9_-]*",
        value,
    ):
        return True

    # Multi-token structured identifiers such as:
    # 787 WT 03001
    # 951 OS 02008
    tokens = value.split()

    if len(tokens) >= 3:
        numeric_tokens = sum(
            bool(re.search(r"\d", token))
            for token in tokens
        )

        alpha_tokens = sum(
            bool(re.search(r"[A-Z]", token))
            for token in tokens
        )

        if numeric_tokens >= 2 and alpha_tokens >= 1:
            return True

    return False