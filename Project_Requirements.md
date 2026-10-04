# MIRA - Project Requirements

**Problem statement:** SIH26099 - AI-Driven Standardization and Harmonization of
Material Codes Across CPSEs.

**Document status:** verified against repository commit `747d43a` (fork main, 2026-10-05).
Every "Implemented" line below was read from that source.

**How to read the status column**

- `Implemented` - code exists and is reachable from an API or UI path.
- `Measured` - a number reproduced by running the code.
- `Partial` - some of the requirement is real, the rest is listed in section 21.
- `Open` - not implemented yet, or implemented but not yet validated.

---

## 1. SIH Problem
**SIH26099 - AI-Driven Standardization and Harmonization of Material Codes Across CPSEs**

MIRA addresses heterogeneous material masters by identifying common, duplicate,
near-duplicate and potentially equivalent materials while preserving each CPSE's
original identity. Nothing is overwritten and nothing is deleted.

## 2. Requirement-to-Implementation Mapping

| SIH Requirement | MIRA Implementation | Status |
|---|---|---|
| AI-based description/spec matching | Qwen3 INT8 semantic + text + spec scoring | Implemented |
| Duplicate identification | Cross-CPSE blocking + pairwise matching | Implemented |
| Near-duplicate identification | Normalization + text/semantic + spec comparison | Implemented |
| Equivalent material identification | Hybrid score + critical gates + human review | Implemented |
| Automated standardization | Normalization, abbreviations, units, parsed attributes | Implemented |
| Intelligent classification | Category taxonomy + keyword inference + classifier | Implemented |
| Common National Material Code | Deterministic `MIRA-<TYPE>-<CAT>-<id>` per cluster | Implemented |
| CPSE code mapping | `/api/mappings` generate / approve / attach / export | Implemented |
| Legacy rationalization/migration | Legacy parsers, adapters, flat export | Implemented |
| User validation/approval | Review queue + approve/reject API with RBAC | Implemented |
| Dashboard analytics | `/api/analytics/*` + Dashboard/Analytics screens | Implemented |
| Audit trail | `/api/audit` + `/api/audit/export`, persistent events | Implemented |
| SAP/ERP integration | REST and CSV export surfaces; no live SAP connection | Partial |
| Traceability | Source CPSE and code retained on materials and mappings | Implemented |

## 3. AI Requirements

### 3.1 Semantic Matching
Current model: `AshIndian/Mira.ai` - a fine-tuned Qwen3 checkpoint published as an INT8
build. Hidden size **1024**, about 753 MB, public on Hugging Face.

Requirements and how they are met:

- local inference, CPU only - yes, no GPU is required;
- no cloud embedding dependency at run time - yes, after the one-time download;
- semantic similarity is one of five score components, never the decision;
- model output alone can never determine technical equivalence (see section 4).

Provisioning: when the model is missing the app downloads it, saves it, **loads it back
to verify**, checks that the dimension is 1024, and writes `MIRA_MODEL_PROVENANCE.txt`.
If provisioning fails, matching raises a loud `FileNotFoundError` instead of silently
degrading. Controlled by `MODEL_AUTO_DOWNLOAD`, `MODEL_HUB_ID`, `MIRA_MODELS_DIR`.

MiniLM (`sentence-transformers/all-MiniLM-L6-v2`) is retained only as a legacy
name/alias in the resolver. It is not used for scoring at run time.

### 3.2 AI-Assisted Attribute Extraction
Implemented: description normalization, regex extraction, technical dictionaries,
abbreviation handling, unit normalization and category-specific parsing.
`parse_specifications` returns `material_grade`, `pressure_rating`, `dimensions` and
`voltage_class`.

Optional LLM enhancement: an LLM service is wired via `MIRA_LLM_PROVIDER`
(`none` | `ollama` | `groq`, default `none`). It is off by default, must never approve
equivalence, and unresolved critical attributes stay `UNKNOWN`.

### 3.3 Intelligent Classification
- deterministic taxonomy with 9 material categories, stable type codes and numeric
  category codes (`services/cnmc/taxonomy.py`);
- keyword inference when the category is missing or generic;
- normalized description features and parsed technical attributes;
- learned-weight experiments under `services/evaluation/` (DEV side only).

### 3.4 Candidate Generation
Two independent, additive sources:

1. **Blocking** - deterministic cross-CPSE keys, capped per source material
   (default 50, maximum 500).
2. **Milvus ANN search** - collection `material_embeddings`, FLOAT_VECTOR dim 1024,
   COSINE metric, `top_k` default 50. Adds pairs that share no keyword.

Milvus only ever **adds** candidates. With Milvus down a run still completes and the
blocking count is unchanged, so a low candidate count is a signal to check
`MILVUS_ENABLED` and the containers rather than a silent quality drop.

## 4. Matching Requirements

Weights in force (`services/matching/scoring.py`):

```text
final_score =
    0.175 x text_similarity
  + 0.400 x semantic_similarity
  + 0.250 x specification_similarity
  + 0.125 x material_grade_similarity
  + 0.050 x other_attributes_similarity
```

Constraints asserted in source: every weight >= 0, weights sum to 1.0,
`w_spec >= 0.25` and `w_grade >= 0.10`. The five-component shape is frozen; only the
numeric weights move, and they were tuned on DEV inside those constraints.

Decision rules (`services/matching/classifier.py`):

| Condition | Decision |
|---|---|
| critical CONFLICT | DIFFERENT |
| score >= 0.85 **and** gates pass | HIGH_CONFIDENCE |
| UNKNOWN critical value, or score > 0.45 | REVIEW |
| otherwise | DIFFERENT |

The two thresholds (0.85 and 0.45) are overridable with `MIRA_HIGH_CONFIDENCE_SCORE`
and `MIRA_DIFFERENT_SCORE`. They are calibration values and should not be tuned in
the field.

Critical rules:

- the score is computed **before** the gates; gates can only downgrade, never upgrade;
- an applicable UNKNOWN forces REVIEW;
- a CONFLICT on a critical field makes the pair DIFFERENT (see the note below);
- text and semantic similarity alone can never approve a pair;
- no score auto-accepts: **HIGH_CONFIDENCE is a recommendation shown to a human**;
- the approval workflow has no automated path at all - `automation_rate` is 0 by design
  and `AUTO_APPROVED` is a legacy label that current code never writes.

> **Note on CONFLICT.** The previous revision of this document said CONFLICT -> REVIEW.
> The implementation classifies a critical conflict as DIFFERENT, which removes the pair
> from the approval queue. That is consistent with the rule that only DIFFERENT
> candidates may be excluded from review. Confirm this is the intended policy; if not,
> it is a one-line change in the classifier.

## 5. Critical Specifications

| Category | Critical fields |
|---|---|
| FASTENER | material_grade, dimensions |
| VALVE | pressure_rating, dimensions |
| PIPE | pressure_rating, dimensions |
| ELECTRICAL CONNECTOR | voltage_class, dimensions |

Gate states are `PASS`, `UNKNOWN` and `CONFLICT`. Only `PASS` counts as evidence for a
HIGH_CONFIDENCE recommendation. Other categories are still scored, but they have no
category gate and surface through REVIEW.

## 6. Standardization
Standardization transforms heterogeneous descriptions into a normalized, structured
representation without destroying source information. The source description and source
attributes are always retained; normalization never rewrites the source record.

## 7. Common Material Record
Built by `services/harmonization/service.py` from the materials of an approved cluster.
Contains: canonical description, category, canonical technical attributes, source CPSE,
original material code, provenance and approval status.

Canonical values are only filled where the sources agree. A critical UNKNOWN keeps a
record out of APPROVED.

## 8. Common National Material Code
Format: `MIRA-<TYPE>-<CATEGORY>-<global id>`, generated deterministically per mapping
cluster by `services/cnmc/service.py`.

- unique in MIRA's namespace - `generate_or_get_cnmc` returns the existing code for an
  identical canonical identity hash instead of minting a second one;
- traceable - the canonical identity string and its hash are stored;
- mapped to every CPSE code it covers;
- original CPSE codes are never replaced.

Taxonomy: 9 categories with stable type codes - VLV 17, PIP 23, BRG 08, FST 12,
ELC 31, GSK 14, CBL 26, FLG 19, PMP 45.

## 9. CPSE Mapping

```text
CPSE material (cpse, material_code)
        |
        v
Common Material Record (canonical, provenance)
        |
        v
Common National Material Code (MIRA-...)
```

Exposed by `/api/mappings`: list, generate, approve, attach a further material, and
`/export/flat` producing `cpse, material_code, nmc, category`. Approving a mapping sets
the mapping and its Common Material Record to APPROVED and writes a `MAPPING_APPROVED`
audit event.

## 10. Legacy Rationalization and Migration
Support provided:

- legacy formats parsed on upload: CSV, TXT, XML, JSON, XLS, XLSX (a separate PDF
  extractor exists for tender documents);
- site-specific adapters and parsers: generic, BHEL (including a technical variant),
  NALCO, NTPC;
- redundant-code identification via `services/clustering/service.py`;
- legacy-to-common mapping plus flat CSV export;
- historical traceability - each material keeps `source_file`, provenance level,
  provenance confidence and the full evidence trail.

No destructive overwrite or deletion exists anywhere in that path.

## 11. Human Review
Reviewers inspect both descriptions, parsed specifications, the per-component scores,
the critical checks and the engine recommendation.

- Queue = candidates with engine decision REVIEW and status PENDING.
- Actions: APPROVE or REJECT, gated by the `review_match` permission.
- Decisions are terminal: acting twice on the same candidate returns 409 rather than
  silently overwriting the first decision.
- DIFFERENT candidates are the only ones excluded from the queue.
- Every decision is auditable.
- Nothing is pre-approved - this holds for HIGH_CONFIDENCE as well.

## 12. Classification
Classification supports category assignment, category-aware specifications, analytics,
blocking and matching improvement. Uncertainty stays visible: unknown categories are not
guessed into a technical bucket, and UNKNOWN critical attributes force REVIEW.

## 13. Audit and Governance
A persistent audit log (`/api/audit`, `/api/audit/export`) records material
import/creation, match generation, review decisions, approval and rejection, common
material creation, mapping and export. It is filterable by event type and actor. Role
permissions gate every action, and seeded users are the only accounts that exist.

## 14. Dashboard and Analytics
`/api/analytics/overview` returns: total materials, CPSE count, candidate pairs,
high-confidence count, human-approved count, auto-approved count (legacy label),
pending review, different, approved, rejected and `automation_rate`.

Further endpoints: `/api/analytics/by-cpse`, `/categories`, `/scores`, `/data-quality`.
UI: Dashboard and Analytics screens, plus Common Materials and Mappings for the
harmonization state.

## 15. SAP / ERP Integration
Available today: the REST API (`/api/*`), CSV export (`/api/mappings/export/flat`, and
`/api/audit/export`), and an ERP Integration screen that drives those exports.

There is no live SAP connection, and this document does not claim one. The adapter
boundary work is listed in section 21.

## 16. Data Ingestion
Accepted uploads: CSV, TXT, XML, JSON, XLS, XLSX.

Columns actually read by `POST /api/materials/upload`:

```text
cpse
material_code       (fallback: source_material_code, item_code)
description         (fallback: material_description)
category
unit
manufacturer
manufacturer_part_number
material_grade
other_attributes    (object)
```

`pressure_rating`, `dimensions` and `voltage_class` are extracted from the description by
`parse_specifications`, not read from columns. Rows without a description are skipped.

CPSE provenance is resolved from the row, the sheet name and the filename. Unrecognised
CPSE values become `CPSE_GENERIC` and are never guessed. Because matching is cross-CPSE
only, a file whose rows all land in one bucket yields zero candidates - that is expected
behaviour, not a matching failure.

## 17. Tender / BOQ Data Rules
- retain item and material descriptions;
- retain technical specifications;
- strip rates and prices on import;
- avoid unnecessary vendor-identifying information;
- preserve provenance where appropriate;
- respect access and redistribution restrictions of the source documents.

## 18. Evaluation
Harness present: `services/evaluation/` (dataset A generator, feature extraction,
learned-weight experiments, stress and leakage audits, controlled A/B) and
`services/training/` (pair generation, weak labeling, cross-CPSE candidate scoring).

Dataset A: DEV, blind HELD-OUT, blind HARD-NEGATIVES. Dataset B is separate.

B1 genuine overlap requires: matching manufacturer part number, OR matching
industry/standard designation, OR matching complete structured specifications without
critical conflict. If fewer than 50 qualifying agreed B1 pairs exist by Day 4, switch
to B2.

Reported metrics: precision, recall, F1, automation rate, aggregate false-positive rate,
hard-negative false-HIGH_CONFIDENCE rate and candidate reduction ratio. REVIEW is an
abstention state and is excluded from committed-decision FP/FN.

Measured evidence so far:

- 150-row real cross-CPSE set (all valves): blocking candidates at cap 5 / 20 / 50 =
  656 / 2,440 / 4,848; uncapped 6,425;
- 12-row mixed-category demo: 51 possible cross-CPSE pairs reduced to 17 blocking
  candidates at cap 50, while keeping all 12 genuine same-item pairs;
- live UI run on 153 materials with Milvus enabled: 5,500+ candidate pairs,
  450 at review, 0 auto-approved;
- 20-row verifier: Milvus added pairs on top of blocking.

## 19. Security / Sovereignty
The core pipeline runs on-premises: normalization, parsing, embedding, matching, critical
gating, review and storage (PostgreSQL plus Milvus). Embedding inference is local.
External LLM use is optional, off by default (`MIRA_LLM_PROVIDER=none`), explicitly
chosen when enabled, and never part of approval.

Production hardening that is still open: replace `secret_key`, change the seeded demo
passwords, and restrict CORS (currently `*` for development).

## 20. Current Implementation
- FastAPI backend with 8 routers under `/api` and 39 endpoints: auth, users, materials,
  matching (compare, run-batch, candidates, stats, CNMC matching), review, audit,
  analytics, mappings.
- React 19 + Vite 8 + TypeScript frontend with 11 screens: Login, Dashboard, Materials,
  Match Review, Mappings, Common Materials, Audit Trail, Analytics, ERP Integration,
  Settings, User Management.
- PostgreSQL with 9 tables; Milvus vector store (etcd + MinIO + Milvus v2.6.23).
- Matching chain: normalization, rule-based parsing, blocking, hybrid scoring, critical
  gates, decision classifier, Milvus ANN search, CNMC matching against existing common
  materials.
- CNMC generation, harmonization into Common Material Records, mapping lifecycle and
  flat export.
- JWT authentication with role permissions. Seeded CPSEs: IOCL, BPCL, CPCL, SAIL, NTPC;
  four demo users, one per role.
- Embedding-model auto-download with verification and a provenance file.
- Tests: 35 modules / 278 test functions (counted from source). A 14-test certification
  subset was executed green against a live stack; the full suite has not been run
  end-to-end in this environment.

## 21. Remaining Implementation
1. Blind evaluation on HELD-OUT and HARD-NEGATIVES, the B1/B2 go/no-go decision, and a
   signed-off metrics report.
2. Test isolation: there is no `conftest.py`, so a suite run touches the development
   database.
3. Idempotent re-upload: uploading the same file twice currently ends in a 500.
4. Deployment packaging: `Dockerfile.backend`, `Dockerfile.frontend` and a top-level
   compose are missing; only the Milvus compose file exists.
5. An ERP adapter boundary against a real SAP/OData endpoint (REST and CSV export exist).
6. Governed enablement of LLM-assisted extraction - wired but off and unapproved.
7. Offline / air-gapped model provisioning guidance for restricted networks.
8. Analytics hygiene: legacy `AUTO_APPROVED` rows from earlier builds still distort the
   automation-rate denominators.
9. Sign-off on the CNMC namespace policy - who owns allocation of the global id in a
   multi-agency deployment.
10. Production hardening of secrets, CORS and demo accounts (section 19).

## 22. Acceptance Principle
> **Similarity finds the candidate. Specifications decide whether it is safe.
> Humans control the final mapping.**
