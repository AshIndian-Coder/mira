"""
Provenance Resolution Service for MIRA Ingestion.

Implements multi-format provenance extraction and conflict detection across:
- CSV, TXT, XML, JSON, XLS, XLSX formats.

Evidence Hierarchy:
1. EXPLICIT_ROW (1.00) - Direct row fields: 'cpse', 'source_org', 'company', 'organization'
2. SHEET_NAME   (0.95) - Recognized CPSE from Excel sheet tab name
3. FILE_HEADER  (0.90) - Top file metadata or header comments
4. FILENAME_METADATA (0.85) - Recognized CPSE token in filename
5. OBSERVED_CODE_PATTERN (0.80) - Known material code prefix pattern
6. UNKNOWN      (0.00) - Fallback when no evidence is found

Safety Constraints:
- Detects conflicts between row-level and container/file-level evidence.
- Flags records for review when contradictions are detected.
- Never guesses or hallucinates CPSE using embeddings or generative text models.
"""

from enum import Enum
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ProvenanceLevel(str, Enum):
    EXPLICIT_ROW = "EXPLICIT_ROW"
    SHEET_NAME = "SHEET_NAME"
    FILE_HEADER = "FILE_HEADER"
    FILENAME_METADATA = "FILENAME_METADATA"
    OBSERVED_CODE_PATTERN = "OBSERVED_CODE_PATTERN"
    UNKNOWN = "UNKNOWN"


CONFIDENCE_MAP: dict[ProvenanceLevel, float] = {
    ProvenanceLevel.EXPLICIT_ROW: 1.0,
    ProvenanceLevel.SHEET_NAME: 0.95,
    ProvenanceLevel.FILE_HEADER: 0.90,
    ProvenanceLevel.FILENAME_METADATA: 0.85,
    ProvenanceLevel.OBSERVED_CODE_PATTERN: 0.80,
    ProvenanceLevel.UNKNOWN: 0.0,
}

# Canonical CPSE aliases and normalization map
KNOWN_CPSE_ALIASES: dict[str, str] = {
    # Major Indian CPSEs and Industrial Entities
    "BHEL": "BHEL",
    "BHARAT HEAVY ELECTRICALS": "BHEL",
    "BHARAT HEAVY ELECTRICALS LIMITED": "BHEL",
    "IOCL": "IOCL",
    "INDIAN OIL": "IOCL",
    "INDIAN OIL CORPORATION": "IOCL",
    "INDIAN OIL CORPORATION LIMITED": "IOCL",
    "ONGC": "ONGC",
    "OIL AND NATURAL GAS CORPORATION": "ONGC",
    "NTPC": "NTPC",
    "NATIONAL THERMAL POWER CORPORATION": "NTPC",
    "SAIL": "SAIL",
    "STEEL AUTHORITY OF INDIA": "SAIL",
    "HPCL": "HPCL",
    "HINDUSTAN PETROLEUM": "HPCL",
    "BPCL": "BPCL",
    "BHARAT PETROLEUM": "BPCL",
    "GAIL": "GAIL",
    "GAS AUTHORITY OF INDIA": "GAIL",
    "COALINDIA": "COALINDIA",
    "COAL INDIA": "COALINDIA",
    "CIL": "COALINDIA",
    "NALCO": "NALCO",
    "NATIONAL ALUMINIUM": "NALCO",
    "BEL": "BEL",
    "BHARAT ELECTRONICS": "BEL",
    "BEML": "BEML",
    "HAL": "HAL",
    "HINDUSTAN AERONAUTICS": "HAL",
    "OIL": "OIL",
    "OIL INDIA": "OIL",
    "PFC": "PFC",
    "POWER FINANCE CORPORATION": "PFC",
    "REC": "REC",
    "RURAL ELECTRIFICATION": "REC",
    "POWERGRID": "POWERGRID",
    "POWER GRID": "POWERGRID",
    "PGCIL": "POWERGRID",
    "RINL": "RINL",
    "RASHTRIYA ISPAT NIGAM": "RINL",
    "VIZAG STEEL": "RINL",
    "NMDC": "NMDC",
    "NATIONAL MINERAL DEVELOPMENT": "NMDC",
    "EIL": "EIL",
    "ENGINEERS INDIA": "EIL",
    "SJVN": "SJVN",
    "NHPC": "NHPC",
    "THDC": "THDC",
    "MOIL": "MOIL",
    "KIOCL": "KIOCL",
    "MIDHANI": "MIDHANI",
    "MISHRA DHATU NIGAM": "MIDHANI",
    "GRSE": "GRSE",
    "MDL": "MDL",
    "MAZAGON DOCK": "MDL",
    "BDL": "BDL",
    "BHARAT DYNAMICS": "BDL",
    "HOC": "HOC",
    "HINDUSTAN ORGANIC CHEMICALS": "HOC",
    "HOCL": "HOC",
    "POLYCAB": "POLYCAB",
    "YANTRAIN": "YANTRAIN",
    "SRF": "SRF",
    "GMR": "GMR",
    "MCL": "MCL",
    "MAHANADI COALFIELDS": "MCL",
    "NCL": "NCL",
    "NORTHERN COALFIELDS": "NCL",
    "WCL": "WCL",
    "WESTERN COALFIELDS": "WCL",
    "SECL": "SECL",
    "SOUTH EASTERN COALFIELDS": "SECL",
    "ECL": "ECL",
    "EASTERN COALFIELDS": "ECL",
    "BCCL": "BCCL",
    "BHARAT COKING COAL": "BCCL",
    "SCCL": "SCCL",
    "SINGARENI": "SCCL",
    "MRPL": "MRPL",
    "MANGALORE REFINERY": "MRPL",
    "CPCL": "CPCL",
    "CHENNAI PETROLEUM": "CPCL",
    "NFL": "NFL",
    "NATIONAL FERTILIZERS": "NFL",
    "RCF": "RCF",
    "RASHTRIYA CHEMICALS AND FERTILIZERS": "RCF",
    "FACT": "FACT",
    "FERTILIZERS AND CHEMICALS TRAVANCORE": "FACT",
}

# Deterministic material code prefix patterns to CPSE
CODE_PREFIX_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^BHEL[-_]?", re.IGNORECASE), "BHEL"),
    (re.compile(r"^IOCL?[-_]?", re.IGNORECASE), "IOCL"),
    (re.compile(r"^ONGC[-_]?", re.IGNORECASE), "ONGC"),
    (re.compile(r"^NTPC[-_]?", re.IGNORECASE), "NTPC"),
    (re.compile(r"^SAIL[-_]?", re.IGNORECASE), "SAIL"),
    (re.compile(r"^HP(?:CL)?[-_]?", re.IGNORECASE), "HPCL"),
    (re.compile(r"^BP(?:CL)?[-_]?", re.IGNORECASE), "BPCL"),
    (re.compile(r"^GAIL[-_]?", re.IGNORECASE), "GAIL"),
    (re.compile(r"^NALCO[-_]?", re.IGNORECASE), "NALCO"),
    (re.compile(r"^BEL[-_]?", re.IGNORECASE), "BEL"),
    (re.compile(r"^BEML[-_]?", re.IGNORECASE), "BEML"),
    (re.compile(r"^HAL[-_]?", re.IGNORECASE), "HAL"),
    (re.compile(r"^PO\d+", re.IGNORECASE), "POLYCAB"),
    (re.compile(r"^YA\d+", re.IGNORECASE), "YANTRAIN"),
    (re.compile(r"^MC\d+", re.IGNORECASE), "MCL"),
    (re.compile(r"^SRF[-_]?", re.IGNORECASE), "SRF"),
    (re.compile(r"^M62\d+", re.IGNORECASE), "BHEL"),
]


class ProvenanceEvidence(BaseModel):
    level: ProvenanceLevel
    cpse: str
    confidence: float
    source_detail: str


class ProvenanceResolution(BaseModel):
    cpse: str = "UNKNOWN"
    confidence: float = 0.0
    level: ProvenanceLevel = ProvenanceLevel.UNKNOWN
    source: str = "No provenance evidence found"
    conflict_detected: bool = False
    requires_review: bool = False
    conflicting_evidence: list[dict[str, Any]] = Field(default_factory=list)
    all_evidence: list[dict[str, Any]] = Field(default_factory=list)


IGNORED_CPSE_WORDS = {
    "UNKNOWN",
    "N/A",
    "NONE",
    "NULL",
    "GENERIC",
    "CPSE GENERIC",
    "NOT AVAILABLE",
    "SHEET",
    "SHEET1",
    "SHEET2",
    "SHEET3",
    "WORKSHEET",
    "PAGE",
    "TABLE",
    "DATA",
    "MATERIALS",
    "ITEMS",
    "LIST",
    "REPORT",
    "EXPORT",
    "MASTER",
    "FILE",
    "SAMPLE",
    "TEMPLATE",
    "INPUT",
    "OUTPUT",
    "UNDEFINED",
    "DEFAULT",
    "ALL",
}


def normalize_cpse_name(name: str | None) -> str | None:
    """Normalize and match candidate CPSE strings against known aliases."""
    if not name:
        return None
    cleaned = re.sub(r"[^A-Za-z0-9\s]", " ", str(name)).strip().upper()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned or cleaned in IGNORED_CPSE_WORDS or cleaned.startswith("SHEET"):
        return None

    # Exact match in known aliases
    if cleaned in KNOWN_CPSE_ALIASES:
        return KNOWN_CPSE_ALIASES[cleaned]

    # Partial / substring check
    for alias, canonical in sorted(KNOWN_CPSE_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if alias == cleaned or (len(alias) > 3 and alias in cleaned):
            return canonical

    # If it looks like a clean uppercase acronym/word (e.g. "TATA", "JSW")
    if re.match(r"^[A-Z0-9]{2,12}$", cleaned) and cleaned not in IGNORED_CPSE_WORDS:
        return cleaned

    return None


def extract_cpse_from_code(code: str | None) -> str | None:
    """Deterministic extraction of CPSE based on material code prefix."""
    if not code:
        return None
    c = str(code).strip()
    for pattern, canonical in CODE_PREFIX_PATTERNS:
        if pattern.match(c):
            return canonical
    return None


def extract_cpse_from_text(text: str | None) -> str | None:
    """Scan arbitrary header or filename text for recognized CPSE tokens."""
    if not text:
        return None

    text_upper = str(text).upper()

    # 1. Check multi-word aliases first (sorted longest first to avoid substring confusion)
    for alias, canonical in sorted(KNOWN_CPSE_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if len(alias) >= 4 and alias in text_upper:
            return canonical

    # 2. Tokenize words/parts and check exact single-word matches
    tokens = re.split(r"[_\-\s\.\(\)\[\]/,]+", text_upper)
    for token in tokens:
        token = token.strip()
        if not token or token in {"UNKNOWN", "NONE", "NULL", "DATA", "CSV", "XLS", "XLSX", "XML", "JSON", "TXT"}:
            continue
        if token in KNOWN_CPSE_ALIASES:
            return KNOWN_CPSE_ALIASES[token]

    return None



def resolve_provenance(
    row: dict[str, Any] | None = None,
    sheet_name: str | None = None,
    file_header: str | None = None,
    filename: str | None = None,
) -> ProvenanceResolution:
    """
    Resolve CPSE provenance for a material record using the hierarchical evidence chain.
    Detects cross-source provenance conflicts without guessing.
    """
    evidence_list: list[ProvenanceEvidence] = []
    row = row or {}

    # 1. Check EXPLICIT_ROW
    row_cpse_raw = (
        row.get("cpse")
        or row.get("source_org")
        or row.get("company")
        or row.get("organization")
        or row.get("plant_company")
    )
    if row_cpse_raw:
        matched = normalize_cpse_name(str(row_cpse_raw))
        if matched and matched != "CPSE_GENERIC" and matched != "UNKNOWN":
            evidence_list.append(
                ProvenanceEvidence(
                    level=ProvenanceLevel.EXPLICIT_ROW,
                    cpse=matched,
                    confidence=CONFIDENCE_MAP[ProvenanceLevel.EXPLICIT_ROW],
                    source_detail=f"Explicit row column value: '{row_cpse_raw}'",
                )
            )

    # 2. Check SHEET_NAME
    if sheet_name:
        sheet_matched = normalize_cpse_name(sheet_name) or extract_cpse_from_text(sheet_name)
        if sheet_matched:
            evidence_list.append(
                ProvenanceEvidence(
                    level=ProvenanceLevel.SHEET_NAME,
                    cpse=sheet_matched,
                    confidence=CONFIDENCE_MAP[ProvenanceLevel.SHEET_NAME],
                    source_detail=f"Excel sheet name: '{sheet_name}'",
                )
            )

    # 3. Check FILE_HEADER
    if file_header:
        header_matched = extract_cpse_from_text(file_header)
        if header_matched:
            evidence_list.append(
                ProvenanceEvidence(
                    level=ProvenanceLevel.FILE_HEADER,
                    cpse=header_matched,
                    confidence=CONFIDENCE_MAP[ProvenanceLevel.FILE_HEADER],
                    source_detail=f"File header metadata: '{file_header[:60]}'",
                )
            )

    # 4. Check FILENAME_METADATA
    if filename:
        fn_matched = extract_cpse_from_text(filename)
        if fn_matched:
            evidence_list.append(
                ProvenanceEvidence(
                    level=ProvenanceLevel.FILENAME_METADATA,
                    cpse=fn_matched,
                    confidence=CONFIDENCE_MAP[ProvenanceLevel.FILENAME_METADATA],
                    source_detail=f"Filename: '{filename}'",
                )
            )

    # 5. Check OBSERVED_CODE_PATTERN
    code = row.get("material_code") or row.get("source_material_code")
    if code:
        code_matched = extract_cpse_from_code(str(code))
        if code_matched:
            evidence_list.append(
                ProvenanceEvidence(
                    level=ProvenanceLevel.OBSERVED_CODE_PATTERN,
                    cpse=code_matched,
                    confidence=CONFIDENCE_MAP[ProvenanceLevel.OBSERVED_CODE_PATTERN],
                    source_detail=f"Material code prefix pattern: '{code}'",
                )
            )

    if not evidence_list:
        return ProvenanceResolution(
            cpse="UNKNOWN",
            confidence=0.0,
            level=ProvenanceLevel.UNKNOWN,
            source="No provenance evidence found",
            conflict_detected=False,
            requires_review=False,
            conflicting_evidence=[],
            all_evidence=[],
        )

    # Check for conflicts across distinct non-empty CPSE identifications
    unique_cpses = {e.cpse for e in evidence_list}
    conflict_detected = len(unique_cpses) > 1
    requires_review = conflict_detected

    # Select highest-priority evidence
    primary = evidence_list[0]

    all_evidence_dicts = [
        {
            "level": e.level.value,
            "cpse": e.cpse,
            "confidence": e.confidence,
            "source_detail": e.source_detail,
        }
        for e in evidence_list
    ]

    conflicting_dicts = []
    if conflict_detected:
        conflicting_dicts = [d for d in all_evidence_dicts if d["cpse"] != primary.cpse]

    return ProvenanceResolution(
        cpse=primary.cpse,
        confidence=primary.confidence,
        level=primary.level,
        source=primary.source_detail,
        conflict_detected=conflict_detected,
        requires_review=requires_review,
        conflicting_evidence=conflicting_dicts,
        all_evidence=all_evidence_dicts,
    )
