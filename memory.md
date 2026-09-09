# MIRA — Project Memory

## Project

**SIH26099 — AI-Driven Standardization and Harmonization of Material Codes Across CPSEs**

**Deadline:** 18 days hard freeze.

## Team Roles

- Person 1 — Data & Evaluation
- Person 2 — Matching Engine
- Person 3 — Backend & Database
- Person 4 — Frontend & Review + frontend-facing API integration
- Person 5 — Integration, Clustering & Demo
- Person 6 — Coordination, documentation, testing and presentation

## Frozen Architecture

CPSE Material Master → Ingestion → Normalization/Units → Parser/Attribute Extraction → Category/Blocking → Candidate Generation → Hybrid Scoring → Critical Gates → HIGH_CONFIDENCE/REVIEW/DIFFERENT → Human Review → Approved Relationships → Clustering/Conflict Detection → Common Material Record → Common National Material Code → CPSE Code Mapping → Audit/Export/API.

## AI Architecture

MIRA uses a layered AI approach.

### Core AI

- Local `all-MiniLM-L6-v2` sentence-transformer for semantic similarity.
- Embeddings run locally/on-premises.
- Semantic similarity is one component of the frozen hybrid score.
- AI similarity never directly approves a material.

### AI-Assisted Attribute Extraction

- Deterministic normalization, regex parsing, technical dictionaries and unit handling are the first extraction layer.
- An LLM may be used as an optional fallback for messy or ambiguous procurement descriptions.
- LLM output must be structured before entering matching.
- Uncertain or missing critical attributes remain UNKNOWN.
- LLM output cannot override critical conflicts or directly approve equivalence.
- The provider must remain replaceable.

### Intelligent Classification

- Material categorization is part of the AI-assisted pipeline.
- MVP classification may combine deterministic rules, normalized attributes and embedding/category similarity.
- A trained classifier may be added if sufficient reliable labels exist.
- Classification does not override critical technical gates.

## Frozen Decisions

- Preserve every original CPSE material code.
- Never overwrite source records with a common code.
- `final_score = 0.20 text + 0.20 semantic + 0.35 specification + 0.15 material/grade + 0.10 other attributes`.
- Only numeric weights may be tuned on DEV; formula shape is frozen.
- Score is calculated before gates.
- Missing applicable critical fields = UNKNOWN → REVIEW.
- Conflicting critical fields → REVIEW.
- No fixed 0.92 auto-accept rule.
- Text/semantic similarity alone cannot safely approve a material.
- AI/LLM output cannot directly approve equivalence.
- Critical canonical specifications are never invented, averaged or majority-voted.
- LLM extraction is optional enhancement, not a core dependency.
- Core matching must function without a cloud LLM.
- UNSPSC is optional supporting classification/blocking/analytics, not a dependency.
- Common National Material Code is an explicit SIH capability; exact syntax is our design decision.
- Common Material approval requires safe canonical fields; critical UNKNOWN blocks APPROVED.
- SAP/ERP integration is represented by integration-ready REST/CSV interfaces; no live SAP claim without an actual integration.
- Matching logic is treated as frozen pending proper DEV/HELD-OUT evaluation.

## SIH Requirement Coverage

The implementation covers AI matching, duplicate/near-duplicate/equivalent identification, standardization, intelligent classification, Common National Material Code generation/recommendation, CPSE mapping, legacy rationalization/migration, human validation, dashboard analytics, audit/governance, SAP/ERP integration capability and One Nation — One Material Code traceability.

## Evaluation

Dataset A consists of:
- DEV
- blind HELD-OUT
- blind HARD-NEGATIVES

Dataset B is separate.

B1 requires positive evidence via:
- matching manufacturer part number, OR
- matching industry/standard designation, OR
- complete structured specifications without critical conflict.

If fewer than 50 qualifying agreed B1 pairs exist by end of Day 4, switch to B2.

Report:
- precision
- recall
- F1
- automation rate
- aggregate false-positive rate
- hard-negative false-HIGH_CONFIDENCE rate

**Day 17:** genuine blind held-out result.

**Day 18:** post-correction result; never present it as an independent blind test.

### Current Evaluation Implementation

- Dataset A feature extraction and evaluation pipeline exists.
- The current Dataset A evaluator is a **score-only benchmark** because the Dataset A records currently do not contain sufficient category/critical-field information for the production critical-gate logic.
- DEV is used for threshold selection.
- The selected threshold is then evaluated on HELD-OUT.
- Hard negatives are evaluated separately for false-HIGH_CONFIDENCE rate.
- Production scoring includes `other_attributes_similarity = 1.0` when both sides have no other attributes; the Dataset A evaluator must be kept aligned with production scoring before final reported results.
- Weak labels are not ground truth and must not be presented as verified training labels.

## Dataset / Tender Data

The useful unit from tender/BOQ sources is the material/item record, not the tender itself.

- Retain material/item descriptions and technical specifications.
- Strip rate/price information.
- Preserve source/CPSE provenance where appropriate.
- Extract material codes where available.
- Preserve manufacturer, part number, grade, dimensions, unit and other technical attributes where available.
- Do not assume public accessibility implies redistribution rights.
- Raw tender documents do not automatically constitute final Dataset B.
- Actual samples must be inspected before finalizing ingestion assumptions.
- Public-source collection must respect access controls and applicable terms.
- Large local datasets must not be casually committed to Git.

## Backend Status

### Core matching implementation

Implemented:

- FastAPI foundation
- normalization
- rule-based technical parsing
- local `all-MiniLM-L6-v2`
- candidate blocking
- frozen weighted hybrid scoring
- category-aware specification similarity
- critical gates
- HIGH_CONFIDENCE/REVIEW/DIFFERENT classifier
- `POST /api/matching/compare`
- regression tests

Verified:

- equivalent valve descriptions → HIGH_CONFIDENCE, observed final score 0.9148
- conflicting pressure rating → REVIEW
- missing critical pressure rating → REVIEW

### Ingestion / evaluation additions

Implemented:

- canonical `MaterialRecord`
- PDF text extraction with page provenance
- CPSE-specific ingestion parsers/adapters
- validation layer
- normalization + specification enrichment
- record combination/export
- Dataset A generation
- Dataset A feature extraction
- Dataset A evaluation
- candidate pair generation
- cross-CPSE candidate generation
- production scoring of cross-CPSE candidates
- weak-label generation

Important:
- `training/` currently contains training infrastructure/placeholders and weak-label preparation.
- There is **not yet a verified trained ML classifier**.
- Do not claim that MIRA has trained/fine-tuned its own classifier unless this is actually implemented and evaluated.

### Phase 5/6 API surface

Implemented:

- `app/store.py` — shared in-memory MATERIALS + CANDIDATES store, designed to be DB-swappable.
- `POST /api/materials/upload` — CSV ingestion → store
- `GET /api/materials` — list with query/CPSE/category filters + pagination
- `GET /api/materials/stats` — summary counts
- `GET /api/materials/{id}`
- `POST /api/matching/run-batch` — blocking + scoring across ingested materials
- `GET /api/matching/candidates` — filtered candidate list
- `GET /api/matching/candidates/{id}`
- `GET /api/matching/stats` — automation rate, blocking reduction, score percentiles
- `GET /api/review/queue` — real REVIEW-decision candidates
- `POST /api/review/queue/{id}/action` — APPROVE/REJECT with audit emission
- `GET /api/review/summary`
- `GET /api/audit`
- `GET /api/audit/export`
- `GET /api/analytics/overview`
- `GET /api/analytics/by-cpse`
- `GET /api/analytics/categories`
- `GET /api/analytics/scores`
- `POST /api/mappings/generate` — Union-Find based NMC generation from APPROVED pairs
- `GET /api/mappings`
- `GET /api/mappings/export/flat`

### Backend limitations still remaining

- PostgreSQL persistence is not yet the active material/candidate store.
- pgvector persistence/search is not yet wired into the active API pipeline.
- In-memory `app/store.py` is currently the runtime store.
- SAP integration is not a live connection; the current architecture is integration-ready.
- End-to-end integration tests for `run-batch` should still be added.
- Real tender/BOQ data may require parser and blocking adjustments.
- Dataset-level production-style evaluation still needs to be completed.

## Frontend Status

Completed screens:

- Dashboard
- Materials
- Match Review
- Common Materials
- Mappings
- ERP Integration
- Analytics
- Audit Trail
- Settings

Frontend architecture:

- React
- Vite
- TypeScript
- modular pages/components/services/types
- enterprise/master-data-management style UI

Current state:

- Frontend screens are implemented.
- API wiring is the next major frontend task.
- Person 4 owns frontend-facing API integration.
- Match Review remains the most important workflow screen.

Primary workflow:

Upload → Materials → Matching → HIGH_CONFIDENCE/REVIEW/DIFFERENT → Human Review → Approved → Common Material → CPSE→NMC Mapping.

## Repository / Data Handling

Repository:

- GitHub remote: `https://github.com/AshIndian-Coder/MIRA.git`
- Local branch: `main`
- Local backend/ingestion/evaluation work has been committed.
- Remote `main` was pulled and merged locally before the latest push.
- Large/local datasets under `data/` should remain out of Git unless explicitly selected for repository distribution.
- Existing committed sample/synthetic dataset files may still exist in the remote repository and should be reviewed separately rather than rewriting history casually.
- Temporary review dumps such as `mira_code_diff.txt` and `mira_code_review_v2.txt` should not be treated as project source files.

## Current Next Action

### Person 4 — Frontend

Wire the existing frontend to the backend API:

1. `GET /api/materials` → Materials page
2. `GET /api/review/queue` → Match Review page
3. `GET /api/analytics/overview` → Dashboard
4. `POST /api/matching/run-batch` → trigger matching from UI
5. `POST /api/mappings/generate` → Mappings page
6. Replace mock/demo records with API responses
7. Preserve loading, empty, error and approval states

### Backend / Matching Priorities

1. Write integration-style tests for `run-batch`.
2. Inspect real tender/BOQ data when available and tune blocking anchors carefully.
3. Complete dataset-level DEV/HELD-OUT evaluation.
4. Align evaluator scoring exactly with production scoring.
5. Consolidate duplicate candidate-generation implementations and avoid unnecessary O(n²) cross-CPSE loops.
6. Move active persistence toward PostgreSQL/pgvector.
7. Implement/verify clustering and conflict detection against approved relationships.
8. Optional: LLM-assisted attribute extraction fallback (stretch only).
9. Do not add actual model training unless it improves validated performance and can be evaluated properly.

## Current Project Principle

**Similarity finds the candidate. Specifications decide whether it is safe. Humans control the final mapping.**

Evaluation principle:

**Evaluate against held-out ground truth, not against data used to design the matcher.**

Product principle:

**Preserve CPSE source codes and create a traceable common material representation/code rather than replacing the source master.**