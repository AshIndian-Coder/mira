# MIRA --- Project Requirements

## 1. SIH Problem
**SIH26099 --- AI-Driven Standardization and Harmonization of Material Codes Across CPSEs**

MIRA addresses heterogeneous material masters by identifying common, duplicate, near-duplicate and potentially equivalent materials while preserving each CPSE's original identity.

## 2. Requirement-to-Implementation Mapping

| SIH Requirement | MIRA Implementation | Status |
|---|---|---|
| AI-based description/specification matching | MiniLM semantic similarity + text similarity + specification-aware hybrid scoring | Core implemented |
| Duplicate identification | Blocking + pairwise matching | Core implemented |
| Near-duplicate identification | Normalization + text/semantic similarity + specification comparison | Core implemented |
| Equivalent material identification | Hybrid score + critical gates + human review | Core implemented |
| Automated standardization | Normalization, abbreviation handling, unit normalization, parsed attributes, canonical representation | Core implemented / expanding |
| Intelligent classification | Category rules + embedding/category similarity + optional supervised classifier | In progress |
| Common National Material Code | Common Material Record + NMC generation/recommendation | Planned |
| CPSE code mapping | CPSE material → common material/NMC mapping | Planned |
| Legacy rationalization/migration | Mapping and export workflow preserving original codes | Planned |
| User validation/approval | Match Review UI + approval/rejection API workflow | UI implemented / backend pending |
| Dashboard analytics | React analytics dashboard + backend aggregation | UI implemented / backend pending |
| Audit trail | Governance UI + persistent audit events | UI implemented / backend pending |
| SAP/ERP integration | REST/CSV interfaces + adapter architecture | Integration-ready |
| Traceability | Source CPSE/material code preserved in common material and mappings | Architectural requirement |

## 3. AI Requirements

### 3.1 Semantic Matching
Current model:
`sentence-transformers/all-MiniLM-L6-v2`

Requirements:
- local inference
- no cloud embedding dependency
- semantic similarity is one matcher component
- model output cannot directly determine technical equivalence

### 3.2 AI-Assisted Attribute Extraction
Core extraction:
- normalization
- regex
- technical dictionaries
- abbreviation mappings
- unit normalization
- category-specific parsing

Optional LLM enhancement:
- difficult/irregular descriptions
- structured attribute extraction
- explicit uncertainty
- UNKNOWN for unresolved critical attributes
- no direct equivalence approval

### 3.3 Intelligent Classification
Classification should use:
- deterministic category rules
- normalized description features
- parsed technical attributes
- semantic/category similarity

A supervised classifier may be added when sufficient reliable labels exist.

## 4. Matching Requirements
```text
final_score =
    0.20 × text_similarity
  + 0.20 × semantic_similarity
  + 0.35 × specification_similarity
  + 0.15 × material_grade_similarity
  + 0.10 × other_attributes_similarity
```

Only numeric weights may be tuned using DEV. Formula shape is frozen.

Critical rules:
- score before gates
- applicable UNKNOWN → REVIEW
- CONFLICT → REVIEW
- text/semantic similarity alone cannot safely approve
- no fixed 0.92 auto-accept
- HIGH_CONFIDENCE requires strong similarity and passing applicable gates

## 5. Critical Specifications
### FASTENER
- material grade
- dimensions

### VALVE
- pressure rating
- dimensions

### PIPE
- pressure rating
- dimensions

### ELECTRICAL CONNECTOR
- voltage class
- dimensions

## 6. Standardization
Standardization transforms heterogeneous descriptions into normalized structured representations without destroying source information.

Source descriptions remain preserved.

## 7. Common Material Record
Contains:
- common/canonical description
- category
- canonical technical attributes
- source CPSE
- original material code
- provenance
- approval status

Canonical values must not be invented. Critical UNKNOWN prevents APPROVED.

## 8. Common National Material Code
MIRA must generate or recommend a Common National Material Code for approved common representations.

Exact syntax is a project design decision.

Requirements:
- unique in MIRA's common-material namespace
- traceable
- mapped to CPSE material codes
- does not replace original codes

## 9. CPSE Mapping
```text
CPSE
Original Material Code
        ↓
Common Material
        ↓
Common National Material Code
```

## 10. Legacy Rationalization and Migration
Support:
- redundant-code identification
- legacy-to-common mapping
- migration/export
- historical traceability

No destructive overwrite/deletion.

## 11. Human Review
Reviewers inspect descriptions, specifications, similarity components, critical checks and AI recommendation.

Actions:
- approve
- reject
- override where permitted

Decisions must be auditable.

## 12. Classification
Classification supports:
- category assignment
- category-aware specifications
- analytics
- blocking
- matching improvement

Uncertainty remains visible.

## 13. Audit and Governance
Record:
- material import/creation
- match generation
- review
- approval/rejection
- common material creation
- mapping
- migration/export

## 14. Dashboard and Analytics
Required:
- material counts by CPSE
- category distribution
- duplicate/match counts
- decision distribution
- confidence distribution
- review backlog
- harmonization progress
- mapping progress
- blocking reduction

## 15. SAP / ERP Integration
Provide:
- REST APIs
- CSV import/export
- ERP adapter boundaries

Do not claim a live SAP connection unless actually implemented and demonstrated.

## 16. Data Ingestion
Possible inputs:
- CSV
- Excel
- JSON
- structured APIs
- extracted tender/BOQ material records

Typical fields:
```text
cpse
material_code
description
category
unit
manufacturer
manufacturer_part_number
material_grade
dimensions
specifications
other_attributes
```

## 17. Tender / BOQ Data Rules
- retain item/material descriptions
- retain technical specifications
- strip rates/prices
- avoid unnecessary vendor-identifying information
- preserve provenance where appropriate
- respect access and redistribution restrictions

## 18. Evaluation
Dataset A:
- DEV
- blind HELD-OUT
- blind HARD-NEGATIVES

Dataset B is separate.

B1 genuine overlap requires:
- matching manufacturer part number, OR
- matching industry/standard designation, OR
- matching complete structured specifications without critical conflict

If fewer than 50 qualifying agreed B1 pairs exist by Day 4, switch to B2.

Report:
- Precision
- Recall
- F1
- Automation rate
- Aggregate false-positive rate
- Hard-negative false-HIGH_CONFIDENCE rate
- Candidate reduction ratio

REVIEW is an abstention state and is excluded from committed-decision FP/FN.

## 19. Security / Sovereignty
Core pipeline should run on-premises:
- normalization
- parsing
- embedding
- matching
- critical gating
- review

External LLM use is optional and must be governed.

## 20. Current Implementation
Implemented:
- React/Vite/TypeScript frontend
- primary screens
- FastAPI foundation
- normalization
- rule-based parsing
- local MiniLM
- blocking
- hybrid scoring
- category-aware specification similarity
- critical gates
- classifier
- `POST /api/matching/compare`
- regression tests

**28 backend tests passing.**

## 21. Remaining Implementation
1. Inspect actual tender/BOQ samples.
2. Finalize ingestion schema.
3. Implement PostgreSQL Material persistence.
4. Implement material ingestion APIs.
5. Connect Materials frontend.
6. Implement dataset-level candidate generation.
7. Persist match results.
8. Implement review APIs.
9. Implement Common Material Records.
10. Implement NMC generation.
11. Implement CPSE-to-NMC mapping.
12. Implement legacy migration/export.
13. Implement clustering/conflict detection.
14. Implement audit backend.
15. Implement analytics APIs.
16. Implement ERP adapter boundaries.
17. Add optional LLM-assisted extraction/classification where justified.
18. Run DEV tuning and blind evaluation.
19. Prepare final demo and presentation.

## 22. Acceptance Principle
> **Similarity finds the candidate. Specifications decide whether it is safe. Humans control the final mapping.**
