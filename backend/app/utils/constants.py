"""Application-wide constants: roles, permissions, statuses, thresholds.

The MIRA matching parameters (weights, thresholds, critical fields) are
reproduced here so services can be imported without loading full settings.
Values mirror ``app.config.settings`` and are the frozen baseline described
in the MIRA matching specification.
"""
from __future__ import annotations

from typing import Dict, List, Set

# ---------------------------------------------------------------------- #
# RBAC roles
# ---------------------------------------------------------------------- #
ROLE_ADMIN = "admin"
ROLE_DATA_STEWARD = "data_steward"
ROLE_REVIEWER = "reviewer"
ROLE_AUDITOR = "auditor"

ROLES: List[str] = [ROLE_ADMIN, ROLE_DATA_STEWARD, ROLE_REVIEWER, ROLE_AUDITOR]
ALL_ROLES: Set[str] = set(ROLES)

# Permission matrix: action -> roles allowed to perform it.
# Every authenticated user can read (view_*), the rest is restricted.
PERMISSIONS: Dict[str, Set[str]] = {
    # Ingestion
    "upload_data": {ROLE_ADMIN, ROLE_DATA_STEWARD},
    "view_materials": ALL_ROLES,
    "sap_sync": {ROLE_ADMIN, ROLE_DATA_STEWARD},
    "view_sap": {ROLE_ADMIN, ROLE_DATA_STEWARD, ROLE_AUDITOR},
    # Matching
    "run_matching": {ROLE_ADMIN, ROLE_DATA_STEWARD},
    "view_matches": ALL_ROLES,
    # Review workflow
    "review_match": {ROLE_ADMIN, ROLE_REVIEWER},
    # CNMC
    "generate_cnmc": {ROLE_ADMIN, ROLE_DATA_STEWARD},
    "update_cnmc": {ROLE_ADMIN, ROLE_DATA_STEWARD},
    "view_cnmc": ALL_ROLES,
    # Mapping
    "create_mapping": {ROLE_ADMIN, ROLE_DATA_STEWARD},
    "view_mappings": ALL_ROLES,
    # Analytics
    "view_dashboard": ALL_ROLES,
    "view_roi": ALL_ROLES,
    # Governance
    "view_audit": {ROLE_ADMIN, ROLE_AUDITOR},
    "manage_users": {ROLE_ADMIN},
    "trigger_retraining": {ROLE_ADMIN},
}

# ---------------------------------------------------------------------- #
# Material / suggestion / mapping statuses
# ---------------------------------------------------------------------- #
MATERIAL_STATUS_ACTIVE = "active"
MATERIAL_STATUS_OBSOLETE = "obsolete"
MATERIAL_STATUS_MERGED = "merged"

SUGGESTION_STATUS_PENDING = "pending"
SUGGESTION_STATUS_APPROVED = "approved"
SUGGESTION_STATUS_REJECTED = "rejected"

MAPPING_STATUS_ACTIVE = "active"
MAPPING_STATUS_REJECTED = "rejected"
MAPPING_STATUS_SUPERSEDED = "superseded"

MAPPING_TYPE_AI_SUGGESTED = "ai_suggested"
MAPPING_TYPE_MANUAL = "manual"
MAPPING_TYPE_AUTO_APPROVED = "auto_approved"

FEEDBACK_APPROVE = "approve"
FEEDBACK_REJECT = "reject"

SYNC_STATUS_SUCCESS = "success"
SYNC_STATUS_FAILED = "failed"
SYNC_STATUS_RUNNING = "running"

# ---------------------------------------------------------------------- #
# MIRA decision labels (output of the ensemble ranker)
# ---------------------------------------------------------------------- #
DECISION_HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
DECISION_REVIEW = "REVIEW"
DECISION_DIFFERENT = "DIFFERENT"

# Critical gate outcomes
GATE_PASS = "PASS"
GATE_UNKNOWN = "UNKNOWN"
GATE_CONFLICT = "CONFLICT"
GATE_CATEGORY_MISMATCH = "CATEGORY_MISMATCH"

# ---------------------------------------------------------------------- #
# MIRA frozen matching parameters
# final_score = 0.20*text + 0.20*semantic + 0.35*specification
#             + 0.15*material_grade + 0.10*other_attributes
# ---------------------------------------------------------------------- #
WEIGHT_TEXT = 0.20
WEIGHT_SEMANTIC = 0.20
WEIGHT_SPECIFICATION = 0.35
WEIGHT_MATERIAL_GRADE = 0.15
WEIGHT_OTHER_ATTRIBUTES = 0.10

HIGH_CONFIDENCE_THRESHOLD = 0.85
DIFFERENT_THRESHOLD = 0.45

VECTOR_TOP_K = 100  # candidates returned by the vector store per material

# Critical fields per category (frozen by the MIRA specification).
# Missing applicable critical field  -> UNKNOWN  -> REVIEW
# Conflicting critical field         -> CONFLICT -> REVIEW
# Category mismatch                  -> CONFLICT -> REVIEW
CRITICAL_FIELDS: Dict[str, List[str]] = {
    "FASTENER": ["material_grade", "dimensions"],
    "VALVE": ["pressure_rating", "dimensions"],
    "PIPE": ["pressure_rating", "dimensions"],
    "ELECTRICAL CONNECTOR": ["voltage_class", "dimensions"],
}
# Safe default for categories that are not explicitly listed: a dimension
# conflict (e.g. BRG 6205 vs 6205) is always treated as a conflict.
DEFAULT_CRITICAL_FIELDS: List[str] = ["dimensions"]

# ---------------------------------------------------------------------- #
# Standardized UOM vocabulary (uom_normalizer targets these)
# ---------------------------------------------------------------------- #
KNOWN_UOMS = [
    "NOS", "KG", "MT", "TNE", "MTR", "FT", "INCH", "MM", "CM",
    "SQR MTR", "CBM", "L", "SET", "HR", "BAG", "DRUM", "CAN",
    "ROLL", "PACKET", "BOX", "UNIT", "PAIR", "DOZEN", "BOLT",
    "KVA", "KW", "KWH", "AMP", "PSI", "BAR", "GSM", "LPM", "GPM",
]

# ---------------------------------------------------------------------- #
# Audit actions
# ---------------------------------------------------------------------- #
AUDIT_LOGIN = "login"
AUDIT_LOGOUT = "logout"
AUDIT_UPLOAD_DATA = "upload_data"
AUDIT_SAP_SYNC = "sap_sync"
AUDIT_SAP_PUSH = "sap_push"
AUDIT_RUN_MATCHING = "run_matching"
AUDIT_APPROVE_MATCH = "approve_match"
AUDIT_REJECT_MATCH = "reject_match"
AUDIT_CREATE_CNMC = "create_cnmc"
AUDIT_UPDATE_CNMC = "update_cnmc"
AUDIT_CREATE_MAPPING = "create_mapping"
AUDIT_CREATE_USER = "create_user"
AUDIT_UPDATE_USER = "update_user"
AUDIT_DEACTIVATE_USER = "deactivate_user"
AUDIT_TRIGGER_RETRAINING = "trigger_retraining"

# ---------------------------------------------------------------------- #
# Default seed CPSEs (created idempotently on first startup)
# ---------------------------------------------------------------------- #
DEFAULT_CPSES: List[Dict[str, str]] = [
    {"name": "Indian Oil Corporation Limited", "short_code": "IOCL"},
    {"name": "Bharat Petroleum Corporation Limited", "short_code": "BPCL"},
    {"name": "Chennai Petroleum Corporation Limited", "short_code": "CPCL"},
    {"name": "Steel Authority of India Limited", "short_code": "SAIL"},
    {"name": "NTPC Limited", "short_code": "NTPC"},
]

