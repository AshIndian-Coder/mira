import re
import unicodedata


# Abbreviations that can be safely expanded without changing
# the technical identity of the material.
ABBREVIATIONS = {
    " ASSY ": " ASSEMBLY ",
    " ASM ": " ASSEMBLY ",
    " HEX ": " HEXAGONAL ",
    " THK ": " THICKNESS ",
    " DIA ": " DIAMETER ",
    " OD ": " OUTER DIAMETER ",
    " ID ": " INNER DIAMETER ",
    " LG ": " LENGTH ",
    " HT ": " HEIGHT ",
    " WT ": " WEIGHT ",
    " BRG ": " BEARING ",
    " VLV ": " VALVE ",
    " PPL ": " PIPE ",
    " GSK ": " GASKET ",
    " WSH ": " WASHER ",
    " PLG ": " PLUG ",
    " SPRG ": " SPRING ",
    " FLT ": " FILTER ",
    " CLP ": " COUPLING ",
    " FLG ": " FLANGE ",
    " ELB ": " ELBOW ",
    " RDT ": " REDUCER ",
    " SHFT ": " SHAFT ",
    " CBL ": " CABLE ",
    " WIR ": " WIRE ",
    " SWCH ": " SWITCH ",
    " CNTC ": " CONTACTOR ",
    " RLY ": " RELAY ",
    " XFRMR ": " TRANSFORMER ",
}


UNIT_NORMALIZATION = {
    "INCHES": "IN",
    "INCH": "IN",
    '"': " IN ",
    "MM.": "MM",
    "KG.": "KG",
    "KGS": "KG",
    "LBS": "LB",
    "LB.": "LB",
    "VOLTS": "V",
    "VOLT": "V",
}


def normalize_text(value: str | None) -> str:
    """
    Deterministically normalize a material description.

    This function cleans and standardizes text but does not
    semantically reinterpret technical material grades.
    """

    if not value:
        return ""

    text = unicodedata.normalize("NFKC", value)

    # Normalize case.
    text = text.upper()

    # Normalize common separators.
    text = text.replace("-", " ")
    text = text.replace("_", " ")
    text = text.replace("/", " / ")

    # Normalize units.
    for source, target in UNIT_NORMALIZATION.items():
        text = text.replace(source, target)

    # Expand only safe abbreviations.
    padded = f" {text} "

    for source, target in ABBREVIATIONS.items():
        padded = padded.replace(source, target)

    text = padded.strip()

    # Normalize whitespace.
    text = re.sub(r"\s+", " ", text)

    # Normalize spacing around punctuation.
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"\s*/\s*", " / ", text)

    return text.strip()


def normalize_material_description(description: str) -> str:
    return normalize_text(description)
