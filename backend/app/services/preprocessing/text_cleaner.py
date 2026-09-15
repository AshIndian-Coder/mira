from __future__ import annotations

import re

_KEEP_CHARS = re.compile(r"[^A-Z0-9 \-/.\\*]+")
_MULTIPLE_SPACES = re.compile(r"\s{2,}")
_DANGLING_DASH = re.compile(r"^-|-$")

_TRANSLATE_TABLE = str.maketrans({
    "\u00d7": "X",   # multiplication sign in dimensions
    "\u2013": "-",   # en dash
    "\u2014": "-",   # em dash
    "\u2018": "'",   # left single quote
    "\u2019": "'",   # right single quote
    "\u201c": '"',   # left double quote
    "\u201d": '"',   # right double quote
    "\u00b5": "u",   # micro sign
    "\u00a0": " ",   # non-breaking space
})


def normalize_case(text: str) -> str:
    """Upper-case (material descriptions are conventionally uppercase)."""
    return text.upper()


def remove_special_chars(text: str) -> str:
    """Drop noise characters, keeping letters, digits and safe technical symbols."""
    text = text.translate(_TRANSLATE_TABLE)
    text = text.upper()
    text = _KEEP_CHARS.sub(" ", text)
    return text


def remove_extra_spaces(text: str) -> str:
    """Collapse whitespace runs to single spaces and trim ends/dangling dashes."""
    text = " ".join(text.split())
    return _DANGLING_DASH.sub("", text).strip()


def clean_description(text: str) -> str:
    """Full cleaning pipeline for a single description string."""
    if not text or not isinstance(text, str):
        return ""
    text = normalize_case(text)
    text = remove_special_chars(text)
    text = remove_extra_spaces(text)
    return text
