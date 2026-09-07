# MIRA --- 18-Day Implementation Plan

## Goal
Deliver a credible SIH26099 prototype demonstrating:
- AI-assisted material matching
- duplicate/near-duplicate/equivalent detection
- standardization
- intelligent classification
- Common National Material Code recommendation
- CPSE code mapping
- legacy rationalization/migration
- human review
- analytics
- audit/governance
- ERP integration capability
- measurable evaluation

Prioritize matcher correctness, evaluation integrity and an end-to-end demo.

## Phase 1 --- Foundation and Source Alignment
### Day 1
**All**
- Freeze requirements, architecture, roles and evaluation rules.

**Person 1**
- Dataset A generator
- DEV/HELD-OUT/HARD-NEGATIVE separation
- Dataset B collection

**Person 2**
- normalization, parsing and matching engine

**Person 3**
- FastAPI/backend and PostgreSQL foundation

**Person 4**
- frontend skeleton
- API contracts
- mock-data boundaries

**Person 5**
- clustering/integration architecture

**Person 6**
- documentation/evaluation governance

## Phase 2 --- Core Matching
### Days 2–4
Person 2:
- normalization
- unit handling
- parsing
- blocking
- text similarity
- local MiniLM
- hybrid scoring
- category-aware specifications
- critical gates
- classifier
- regression tests

Person 3:
- backend structure
- database configuration
- schemas
- matching API
- persistence foundation

Person 1:
- controlled synthetic data
- DEV
- blind held-out
- hard negatives
- B1/B2 decision

Person 4:
- Materials UI
- Match Review UI
- API service layer
- frontend types

Person 5:
- clustering
- conflict detection
- Common Material workflow
- integration boundary

Person 6:
- requirements
- evidence
- test matrix
- presentation notes

### Day 4 B1 Gate
Person 2 + Person 4 hold B1 records.

Person 1 + Person 3 remain blind to individual B1 records/descriptions/labels before Day 17.

If fewer than 50 qualifying agreed genuine B1 pairs exist, switch to B2.

## Phase 3 --- Core Matcher Verification
### Days 5–6
Verify:
- parser
- normalization
- semantic similarity
- blocking
- scoring
- critical gates
- classifier

Test:
1. positive equivalent
2. wording variation
3. hard negative
4. critical conflict
5. critical unknown
6. category mismatch
7. missing attributes
8. unit variation

Do not tune on held-out data.

## Phase 4 --- Material Persistence and Ingestion
### Days 6–8
Person 3:
```text
Material model
POST /api/materials
GET /api/materials
GET /api/materials/{id}
```

Ingestion:
```text
CSV/Excel/JSON
      ↓
schema mapping
      ↓
normalization
      ↓
parsing
      ↓
database
```

Person 4:
```text
Materials UI
     ↓
GET /api/materials
     ↓
real backend data
```

Team:
- inspect actual tender/BOQ data
- finalize material fields
- provenance
- CPSE identification
- technical specification representation
- price/rate removal

## Phase 5 --- Dataset-Level Matching
### Days 8–10
```text
CPSE materials
      ↓
blocking
      ↓
candidate pairs
      ↓
hybrid matcher
      ↓
HIGH_CONFIDENCE / REVIEW / DIFFERENT
```

Persist candidates, scores, critical checks and decisions.

Measure candidate reduction and candidate recall.

## Phase 6 --- Human Review
### Days 9–11
Backend:
```text
GET /api/matches/review
GET /api/matches/{id}
POST /api/matches/{id}/decision
```

Frontend:
- connect Match Review
- score breakdown
- critical checks
- approve/reject
- refresh queue

Persist reviewer identity and decision time.

## Phase 7 --- Common Materials and NMC
### Days 10–12
```text
Approved relationships
        ↓
Common Material Record
        ↓
Canonical fields
        ↓
Common National Material Code
```

Rules:
- preserve source codes
- no unsafe canonical inference
- critical UNKNOWN blocks approval

Implement:
`CPSE material code → Common Material → NMC`

## Phase 8 --- Clustering and Conflict Detection
### Days 11–13
Implement:
- high-confidence relationship graph
- connected components
- cluster generation
- internal conflict detection
- cluster review/split

## Phase 9 --- Legacy Migration and Export
### Days 12–13
Implement:
- legacy-code mapping
- migration/export table
- common-code export
- source-code traceability

## Phase 10 --- Governance and Analytics
### Days 13–14
Audit:
- match created
- match reviewed
- match approved
- match rejected
- common material created
- mapping created
- export generated

Analytics:
- materials by CPSE
- category distribution
- decision distribution
- review backlog
- harmonization progress
- duplicate reduction
- mapping progress
- blocking reduction

Connect existing frontend charts.

## Phase 11 --- ERP Integration Capability
### Days 14–15
```text
ERPIntegration
    ├── Mock ERP
    └── SAP adapter interface
```

Demonstrate:
`Import → Harmonize → Approve → Export mapping`

Do not spend the schedule on live SAP unless an actual environment exists.

## Phase 12 --- AI Enhancement
### Days 14–16
Only after core matcher is stable and real data has been inspected.

### Optional LLM extraction
```text
Description
    ↓
Deterministic parser
    ↓
Confident?
   /  yes  no
 |     |
use   optional LLM
        ↓
structured attributes
        ↓
existing matcher
```

Rules:
- LLM cannot directly approve equivalence.
- UNKNOWN remains UNKNOWN.
- Critical gates remain authoritative.
- Core matcher works without cloud LLM.

### Classification
Improve using:
- rules
- embeddings
- category prototypes
- supervised model if sufficient labels exist

Do not train a model merely for appearance.

## Phase 13 --- Evaluation
### Days 16–17
DEV:
- tune numeric parameters
- finalize configuration

HELD-OUT:
- blind evaluation

Report:
- Precision
- Recall
- F1
- automation rate
- false-positive rate
- hard-negative false-HIGH_CONFIDENCE rate
- candidate reduction ratio

Day 17 produces the genuine blind result.

## Phase 14 --- Final Correction and Demo
### Day 18
Use Day 17 error analysis for targeted fixes.

Rerun and label:
> Post-correction result after Day 17 analysis.

Do not call it an independent blind test.

Finalize:
- end-to-end demo
- UI polish
- sample dataset
- architecture diagram
- evaluation charts
- governance story
- ERP integration story
- SIH presentation
- documentation

# End-to-End Demo Flow
```text
Upload CPSE datasets
        ↓
Normalize descriptions
        ↓
Extract technical attributes
        ↓
Classify materials
        ↓
Generate candidates
        ↓
AI semantic + specification matching
        ↓
Critical technical gates
        ↓
HIGH_CONFIDENCE / REVIEW / DIFFERENT
        ↓
Human review
        ↓
Approved relationships
        ↓
Common Material Record
        ↓
Common National Material Code
        ↓
CPSE → NMC mapping
        ↓
Legacy migration/export
        ↓
Audit + Analytics
        ↓
ERP/SAP integration capability
```

# Priority Rules

## Must-have
1. Real material ingestion
2. Core matcher
3. Critical gates
4. Held-out evaluation
5. Human review
6. Common Material Record
7. NMC
8. CPSE mapping
9. Audit trail
10. End-to-end demo

## Important
11. Classification
12. Dataset-level blocking
13. Clustering/conflict detection
14. Analytics backend
15. Migration/export
16. ERP adapter

## Stretch
17. LLM-assisted attribute extraction
18. Advanced classification model
19. Additional optimization
20. Production-scale infrastructure

The LLM must never displace evaluation, critical gates or human review.

# Current State
Completed:
- Frontend screens
- FastAPI foundation
- normalization
- rule-based parser
- local MiniLM semantic similarity
- blocking
- hybrid scoring
- category-aware specification similarity
- critical gates
- match classifier
- `POST /api/matching/compare`
- 28 passing backend tests

Verified:
```text
Equivalent descriptions → HIGH_CONFIDENCE
Critical conflict → REVIEW
Critical UNKNOWN → REVIEW
```

Immediate priorities:
1. Inspect teammate-collected tender/BOQ data.
2. Implement PostgreSQL Material persistence.
3. Implement `GET /api/materials`.
4. Connect Materials frontend.
5. Continue toward dataset-level matching and review persistence.
