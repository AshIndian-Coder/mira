# MIRA --- System Architecture

## 1. Purpose
MIRA is an AI-driven cross-CPSE material harmonization platform for SIH26099. It analyzes heterogeneous material masters, identifies duplicate/near-duplicate/equivalent materials, standardizes material information, recommends common material representations and Common National Material Codes, preserves original CPSE codes, and provides human-controlled approval, mapping, governance and integration workflows.

MIRA is a harmonization layer, not an ERP/SAP replacement.

## 2. Design Principles
1. Preserve source truth.
2. Separate similarity from technical safety.
3. Use AI where semantic ambiguity exists.
4. Use deterministic rules where exact technical correctness is required.
5. Never let an LLM directly approve equivalence.
6. Humans control uncertain/technically ambiguous cases.
7. Preserve source traceability.
8. Keep model providers replaceable.
9. Keep frontend independent of backend language.
10. Evaluate against held-out ground truth.

## 3. High-Level Architecture
```text
CPSE MATERIAL SOURCES
        |
     INGESTION
        |
NORMALIZATION / UNITS
        |
ATTRIBUTE EXTRACTION
   /              RULES          OPTIONAL LLM
   \              /
        |
CLASSIFICATION
        |
BLOCKING
        |
CANDIDATE GENERATION
        |
+-------+----------------+
|                        |
TEXT SIMILARITY     SEMANTIC SIMILARITY
|                   MiniLM Embeddings
+----------+-------------+
           |
SPECIFICATION COMPARISON
           |
HYBRID SCORE ENGINE
           |
CRITICAL GATES
     /      |        HIGH     REVIEW   DIFFERENT
CONF.       |
     HUMAN VALIDATION
           |
APPROVED RELATIONSHIPS
           |
CLUSTERING / CONFLICT CHECK
           |
COMMON MATERIAL RECORD
           |
COMMON NATIONAL MATERIAL CODE
           |
CPSE CODE → NMC MAPPING
           |
     +-----+-----+------+
     |           |      |
   AUDIT     ANALYTICS EXPORT/API
                        |
                      ERP/SAP
```

## 4. Technology Stack
### Frontend
- React
- Vite
- TypeScript
- REST API
- Recharts

### Backend
- Python
- FastAPI
- Pydantic
- SQLAlchemy
- PostgreSQL
- pgvector

### AI / ML
- `sentence-transformers`
- `all-MiniLM-L6-v2`
- Optional LLM provider for difficult attribute extraction
- Optional embedding/category classification enhancement

## 5. AI Architecture

### 5.1 Semantic Similarity
The core semantic model is `sentence-transformers/all-MiniLM-L6-v2`.

It converts descriptions into embeddings for semantic comparison. Inference runs locally.

### 5.2 Deterministic Attribute Extraction
The first extraction layer uses:
- text normalization
- abbreviation mappings
- unit normalization
- regex
- technical dictionaries
- category-specific patterns

Examples:
```text
SS-304 / SS304 / STAINLESS STEEL 304 → SS304
150# / 150 POUND → 150 LB
```

### 5.3 Optional LLM Attribute Extraction
An LLM may convert difficult descriptions into structured attributes.

Example:
```text
"SS GATE V/V 50NB CL150 RF ENDS"
```

Possible structured result:
```json
{
  "type": "GATE VALVE",
  "material": "SS",
  "size": "50 MM",
  "pressure_class": "150",
  "connection": "RF"
}
```

The LLM is an extraction assistant, not the final equivalence judge.

Rules:
- output must be structured
- uncertainty remains UNKNOWN
- critical conflicts remain conflicts
- LLM output cannot create HIGH_CONFIDENCE directly
- core matching works without a cloud LLM
- provider is replaceable

Potential boundary:
```text
LLMProvider
  ├── GeminiProvider
  ├── LocalLLMProvider
  └── OtherProvider
```

## 6. Intelligent Classification
Classification can combine:
- deterministic category rules
- normalized attributes
- parsed specifications
- embedding/category similarity

If sufficient reliable labels exist, a supervised classifier can be introduced.

Classification supports category-specific critical fields and does not override critical gates.

## 7. Normalization
Normalize safe variations in:
- case
- punctuation
- separators
- abbreviations
- units
- technical aliases

Never erase technically meaningful distinctions.

## 8. Specification Parsing
Extract:
- material grade
- pressure rating
- dimensions
- voltage class
- category-specific attributes

Parser output is separate from the original description.

## 9. Critical Fields
### FASTENER
- material_grade
- dimensions

### VALVE
- pressure_rating
- dimensions

### PIPE
- pressure_rating
- dimensions

### ELECTRICAL CONNECTOR
- voltage_class
- dimensions

## 10. Blocking
Candidate keys may include:
- manufacturer part number
- category
- category + grade
- material type anchors

Blocking is candidate generation, not equivalence proof. Measure both reduction and candidate recall.

## 11. Hybrid Matching
```text
final_score =
    0.20 × text_similarity
  + 0.20 × semantic_similarity
  + 0.35 × specification_similarity
  + 0.15 × material_grade_similarity
  + 0.10 × other_attributes_similarity
```

Formula structure is frozen. Only numeric weights may be tuned on DEV.

## 12. Critical Gates
Possible states:
- PASS
- UNKNOWN
- CONFLICT

Rules:
```text
Critical UNKNOWN  → cannot be HIGH_CONFIDENCE
Critical CONFLICT → cannot be HIGH_CONFIDENCE
Strong score + all applicable fields PASS → HIGH_CONFIDENCE
```

## 13. Match Classification
Returns:
- HIGH_CONFIDENCE
- REVIEW
- DIFFERENT

No fixed 0.92 auto-accept rule is used.

## 14. Human Review
Reviewers see:
- source/target materials
- original/normalized descriptions
- extracted specifications
- similarity scores
- critical checks
- AI recommendation
- reasons for uncertainty/conflict

Actions:
- Approve
- Reject
- Override where governance permits

Every decision is auditable.

## 15. Common Material Record
Contains:
- canonical description
- canonical category
- canonical technical attributes
- source CPSE materials
- original CPSE material codes
- approval state
- provenance

If sources disagree or a critical field is unavailable:
`canonical field = UNKNOWN`

Never average, majority-vote or invent critical technical values.

## 16. Common National Material Code
The SIH problem statement requires recommendation/generation of a Common National Material Code.

Exact syntax is a MIRA design decision.

The code must:
- uniquely identify the common representation
- remain traceable to source records
- not replace original CPSE codes
- support mapping and migration/export

## 17. Clustering
High-confidence relationships form candidate clusters. Internal conflicts trigger review or cluster splitting rather than blind merging.

## 18. Database
PostgreSQL stores:
- source materials
- normalized descriptions
- parsed attributes
- embeddings where appropriate
- match results
- review decisions
- common materials
- mappings
- integration records
- audit events

pgvector supports vector search.

## 19. API Boundary
Current (all live, Postgres-backed — see memory.md "Latest Update — 2026-09-12"):
```text
GET  /
GET  /health
POST /api/materials/upload
GET  /api/materials
GET  /api/materials/stats
GET  /api/materials/{id}
POST /api/matching/compare
POST /api/matching/run-batch
GET  /api/matching/candidates
GET  /api/matching/candidates/{id}
GET  /api/matching/stats
GET  /api/review/queue
GET  /api/review/queue/{id}
POST /api/review/queue/{id}/action
GET  /api/review/summary
GET  /api/audit
GET  /api/audit/export
GET  /api/analytics/overview
GET  /api/analytics/by-cpse
GET  /api/analytics/categories
GET  /api/analytics/scores
GET  /api/mappings
GET  /api/mappings/{id}
POST /api/mappings/generate
GET  /api/mappings/export/flat
```

Planned:
```text
GET  /api/common-materials
POST /api/common-materials
GET  /api/integrations
POST /api/integrations/{id}/sync
```

## 20. ERP / SAP Integration
MIRA exposes integration-ready boundaries rather than claiming a live SAP connection.

```text
MIRA API
   |
ERP Integration Adapter
   ├── Mock ERP
   ├── SAP Adapter
   └── Future ERP adapters
```

## 21. Governance
Audit events should cover:
- MATCH_CREATED
- MATCH_REVIEWED
- MATCH_APPROVED
- MATCH_REJECTED
- COMMON_MATERIAL_CREATED
- MAPPING_CREATED
- EXPORT_GENERATED
- MATERIAL_UPDATED

## 22. Analytics
Metrics include:
- materials by CPSE
- materials by category
- match decisions
- review backlog
- harmonization progress
- duplicate/near-duplicate counts
- confidence distribution
- blocking reduction
- mapping progress

## 23. Evaluation
Dataset A:
- DEV
- HELD-OUT
- HARD-NEGATIVES

Dataset B is separate and follows its own collection/evidence rules.

## 24. Scale
```text
reduction_ratio =
1 - candidate_pairs / all_possible_pairs
```

A single-server PostgreSQL prototype is not proof of production-scale performance for millions of records.

## 25. Current Implementation
Implemented:
- frontend screens
- FastAPI foundation
- normalization
- rule-based parser
- local MiniLM semantic similarity
- blocking
- hybrid scoring
- category-aware specification comparison
- critical gates
- match classifier
- full matching/materials/review/audit/analytics/mappings API
- **PostgreSQL persistence for materials, candidates, mappings, audit** (`db_adapter.py` + `mira_full_schema.sql`, verified incl. restart test)
- CSV material ingestion, dataset-level matching, human review with audit
- provisional NMC mapping generation
- regression tests

**38 tests passing** (8 pre-existing failures are environmental only: no HuggingFace access in one sandbox).

Next:
1. Inspect tender/BOQ samples.
2. Connect Materials frontend (backend ready).
3. Common Material Record (canonical form beyond provisional NMC).
4. Clustering/conflict detection verification.
5. pgvector search integration.
6. Optional LLM extraction/classification if justified.
7. Blind evaluation.
