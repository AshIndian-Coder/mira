"""STAGE 1 - Data cleaning & normalization.

Pipeline for a raw material description:
    text_cleaner.clean_description()
    -> abbreviation_expander.expand_abbreviations()
    -> uom_normalizer.normalize_uom()

``preprocess_description`` runs the first two steps and returns the
canonical description used for embeddings and fuzzy matching.
"""
from app.services.preprocessing.text_cleaner import clean_description, remove_extra_spaces, remove_special_chars, normalize_case
from app.services.preprocessing.abbreviation_expander import expand_abbreviations
from app.services.preprocessing.uom_normalizer import normalize_uom, is_known_uom


def preprocess_description(raw_description: str) -> str:
    """Full text normalization pipeline for a material description."""
    if not raw_description:
        return ""
    cleaned = clean_description(raw_description)
    expanded = expand_abbreviations(cleaned)
    return clean_description(expanded)  # final pass collapses spacing again


__all__ = [
    "clean_description",
    "remove_special_chars",
    "remove_extra_spaces",
    "normalize_case",
    "expand_abbreviations",
    "normalize_uom",
    "is_known_uom",
    "preprocess_description",
]

