"""STAGE 2 - Attribute extraction from material descriptions.

``attribute_extractor.extract_attributes("BRG BALL 6205 2RS")`` ->
    {"type": "Bearing", "subtype": "Ball", "size": "6205", "seal": "2RS", ...}

The runtime extractor is deterministic rule/regex-based (fast, offline,
reproducible for demos and unit tests). A spaCy/BERT-NER wrapper can be
slotted in later without changing the public API.
"""
from app.services.ner_extraction.attribute_extractor import extract_attributes, ATTRIBUTE_KEYS

__all__ = ["extract_attributes", "ATTRIBUTE_KEYS"]

