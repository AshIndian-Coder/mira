# MIRA — Project Memory

## Project

**SIH26099 — AI-Driven Standardization and Harmonization of Material Codes Across CPSEs**

Official problem statement:
- Organization: Ministry of Petroleum & Natural Gas
- Department: Chennai Petroleum Corporation Limited (CPCL)
- Category: Software
- Theme: Smart Automation
- Official requirements include:
  - AI-based material matching/recommendation
  - duplicate, near-duplicate and functionally equivalent identification
  - material standardization and technical attribute handling
  - intelligent classification/categorization
  - Common National Material Code generation/recommendation
  - CPSE code mapping and legacy rationalization/migration support
  - human validation and approval workflow
  - dashboard/material analytics
  - audit trail/governance
  - SAP/ERP integration capability
  - traceability from common material back to individual CPSE material codes
- Product goal: **One Nation — One Material Code**, while preserving source CPSE codes.

## Requirements / Design Authority

Use these sources in this order:

1. **Official SIH26099 problem statement** — requirement authority.
2. **Current repository/source code and active backend API** — implementation authority.
3. **Teammate frontend PDF** — proposed product/UI roadmap.

The teammate frontend PDF is useful because it intentionally proposes capabilities beyond the official minimum, including:
- authentication/JWT
- role-based routing
- CPSE selector
- richer MatchCard/AI reasoning
- CNMC/Common Material registry
- ROI/savings calculator
- SAP integration status/sync UI
- admin/user management
- richer charts, tables and modals.

These are **proposed product capabilities**, not official SIH-mandated folder names or API contracts.

Do not rebuild the existing frontend simply to reproduce the PDF's folder structure. Add high-value capabilities incrementally when they are useful and genuinely supportable.

Never fake unsupported functionality.

## Team Roles

- Person 1 — Data & Evaluation
- Person 2 — Matching Engine
- Person 3 — Backend & Database
- Person 4 — Frontend & Review + frontend-facing API integration
- Person 5 — Integration, Clustering & Demo
- Person 6 — Coordination, documentation, testing and presentation

## Frozen Architecture

CPSE Material Master → Ingestion → Normalization/Units → Parser/Attribute Extraction → Category/Blocking → Candidate Generation → Hybrid Scoring → Critical Gates → HIGH_CONFIDENCE/REVIEW/DIFFERENT → Human Review → Approved Relationships → Clustering/Conflict Detection → Common Material Record → Common National Material Code → CPSE Code Mapping → Audit/Export/API.

Core principle:

**Similarity finds the candidate. Specifications decide whether it is safe. Humans control the final mapping.**

## AI Architecture

### Core AI

- Local `all-MiniLM-L6-v2` sentence-transformer for semantic similarity.
- Embeddings run locally/on-premises.
- Semantic similarity is one component of the frozen hybrid score.
- AI similarity never directly approves a material.

### AI-Assisted Attribute Extraction

- Deterministic normalization, regex parsing, technical dictionaries and unit handling are the first extraction layer.
- LLM is an optional fallback for messy or ambiguous procurement descriptions.
- LLM output must be structured before entering matching.
- Uncertain or missing critical attributes remain UNKNOWN.
- LLM output cannot override critical conflicts or directly approve equivalence.
- Provider must remain replaceable.

### Intelligent Classification

- Material categorization is part of the AI-assisted pipeline.
- MVP classification may combine deterministic rules, normalized attributes and embedding/category similarity.
- A trained classifier may be added only if sufficient reliable labels exist.
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
- SAP/ERP integration is integration-ready REST/CSV unless an actual live integration exists.
- Matching logic is treated as frozen pending proper DEV/HELD-OUT evaluation.
- Do not create a separate parser for every CPSE. Generic ingestion should handle unfamiliar structures unless a recurring structural need is demonstrated.

## Official SIH Requirement Coverage

The current implementation covers the core official requirements:

- AI-assisted material matching/recommendation
- duplicate/near-duplicate/equivalent identification
- standardization and technical attribute extraction
- intelligent classification/categorization
- Common National Material Code recommendation/generation
- CPSE code → common-code mapping
- human validation/approval workflow
- dashboard and analytics
- audit trail/governance
- integration-ready SAP/ERP exchange/export
- traceability from common material to CPSE source codes.

The solution should aim to exceed the baseline where additional functionality creates genuine product value.

## Backend Status

### Core Matching

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
- regression tests.

Verified:
- equivalent valve descriptions → HIGH_CONFIDENCE, observed final score 0.9148
- conflicting pressure rating → REVIEW
- missing critical pressure rating → REVIEW

### Ingestion Architecture

Current architecture is **generic-first**.

Completed cleanup:
- removed CPSE-specific BHEL adapter
- removed BHEL technical adapter
- removed NALCO adapter
- removed BHEL parser
- removed NALCO parser
- removed NTPC parser
- removed adapter registry
- removed old ingestion service
- removed obsolete CPSE-specific combination/export/enrichment modules
- removed CPSE-specific detection rules
- removed hardcoded CPSE inference
- removed `cpse_hint`
- `GenericAdapter` uses `cpse="UNKNOWN"` when CPSE information is unavailable
- `document_inspector.py` performs generic inspection
- `pipeline.py` uses the generic adapter without CPSE-specific imports/dynamic parser loading
- pipeline report type is `generic`.

Principle:

**Do not encode CPSE identity as parser logic. Extract the material record generically and preserve CPSE provenance as data when available.**

### Deterministic Parser

Verified extraction includes:
- voltage ranges
- frequency
- power ranges
- CCT
- CRI
- beam angle
- IP rating
- luminous efficiency
- material grade and existing technical fields.

HCL real-document validation produced one valid record and extracted:
- 80–140 V
- 50 Hz
- 18–20 W
- CCT 5700–6500 K
- CRI 70
- beam angle 120 DEG
- IP 66
- >=130 LM/W.

The HCL record did not invoke the LLM because its unmapped evidence was technical rather than evidence of missing identity fields.

### Parser Regression Fix — 2026-09-13

For:

`PIPE OD60.3 X 5.54THK MM`

the parser now emits separate tokens:
- OD → 60.3 MM
- THICKNESS → 5.54 MM

instead of one combined `OD_THICKNESS` token.

Known test result:
**48/48 pytest tests pass.**

### LLM Fallback

Implemented under `backend/app/services/ingestion/llm/`:
- provider abstraction
- Ollama/local provider
- Groq provider
- JSON parser
- prompts
- resolver
- extraction service.

Providers:
- `none`
- `local` / Ollama
- `groq`

Testing model:
- `openai/gpt-oss-20b`

Strict schema:
- `material_grade`
- `manufacturer`
- `manufacturer_part_number`
- `model`
- `dimensions`

`other_specifications` was intentionally removed.

Resolver rules:
- deterministic values remain authoritative
- LLM only fills missing fields
- conflicts recorded in `raw_attributes["llm_conflicts"]`
- LLM cannot directly approve equivalence
- LLM failure must not break ingestion
- missing fields alone do not trigger LLM
- low/medium extraction confidence can trigger escalation
- explicit ambiguity can trigger escalation
- explicit labels such as `MOC:`, `MANUFACTURER:`, `MAKE:`, `MODEL:`, `PART NO:` and dimension labels can trigger escalation
- generic unmapped technical lines alone do not trigger escalation
- evidence construction is separated into `build_evidence_text(record)`.

Conclusion:

**LLM extraction is functional optional fallback/stretch functionality. Deterministic extraction and matching remain the core path.**

## Active Backend API Contract

Do not invent frontend APIs.

Current API surface:

- `GET /api/materials`
- `GET /api/materials/stats`
- `GET /api/materials/{id}`
- `POST /api/materials/upload`
- `POST /api/matching/run-batch`
- `GET /api/matching/candidates`
- `GET /api/matching/candidates/{id}`
- `GET /api/matching/stats`
- `GET /api/review/queue`
- `POST /api/review/queue/{id}/action`
- `GET /api/review/summary`
- `GET /api/analytics/overview`
- `GET /api/analytics/by-cpse`
- `GET /api/analytics/categories`
- `GET /api/analytics/scores`
- `POST /api/mappings/generate`
- `GET /api/mappings`
- `GET /api/mappings/{id}`
- `GET /api/mappings/export/flat`
- `GET /api/audit`
- `GET /api/audit/export`
- `GET /health`
- `GET /`

If a requested feature has no backend support, identify it as a new feature rather than fabricating a UI result.

## PostgreSQL Persistence

PostgreSQL is the active runtime store.

Implemented:
- `backend/mira_full_schema.sql`
- `backend/app/db_adapter.py`
- `backend/app/store.py`
- DB-backed mappings
- DB-backed audit events
- landing page
- setup/documentation.

Verified:
- upload → match → approve → mappings → audit → analytics over PostgreSQL
- state survives backend restart
- IDs continue safely after restart
- PostgreSQL is active runtime persistence.

## Current Backend Limitations

- pgvector persistence/search is not yet wired into the active API pipeline.
- SAP integration is not a live connection; current architecture is integration-ready.
- end-to-end integration tests for `run-batch` should still be added.
- real tender/BOQ data may require parser/blocking adjustments.
- dataset-level production-style evaluation remains pending.
- clustering/conflict detection still needs verification against approved relationships.
- final NMC/CNMC governance and numbering policy is still a design decision.
- authentication/user management is not currently part of the active backend contract.

## Frontend Status

### Completed Screens

- Dashboard
- Materials
- Match Review
- Common Materials
- Mappings
- ERP Integration
- Analytics
- Audit Trail
- Settings.

Frontend stack:
- React
- Vite
- TypeScript
- React Router DOM
- Recharts
- Lucide React
- plain CSS in `frontend/src/index.css`.

The frontend is API-connected and no longer relies on mock/demo records.

Primary workflow:

**Upload → Materials → Matching → HIGH_CONFIDENCE/REVIEW/DIFFERENT → Human Review → Approved → Common Material → CPSE→NMC Mapping → Export/Audit/Analytics.**

### Frontend Completion

Completed and pushed:
- Materials API integration
- CSV upload
- batch matching trigger
- Match Review queue
- approve/reject actions
- Dashboard analytics
- Common Materials/mappings
- mapping generation/export
- ERP export preparation
- Analytics
- Audit Trail
- truthful Settings/capability display
- loading/error/empty states
- removal of unused legacy services/types
- removal of Vite starter assets.

Frontend production build passed.

Vite's large-chunk warning is non-blocking and is not a current priority.

### ERP Integration Truthfulness

The ERP page must not claim live SAP synchronization.

Current behavior:
- reads real analytics/mapping data
- shows ingested CPSE source availability
- shows real mapping statuses
- prepares real mapping export data
- describes the environment as integration-ready.

## Teammate Frontend Roadmap

The teammate's proposed frontend blueprint is accepted as a **roadmap**, not as a reason to rebuild the current application.

Potential high-value additions:
- login/authentication and role-based routing if backend auth is implemented
- CPSE selector
- richer MatchCard with AI reasoning
- Common Material/CNMC registry experience
- ROI/savings calculator
- richer charts/tables
- approval/upload modals
- SAP integration status/sync workflow
- admin/user management.

Prioritize additions according to:
1. official SIH value
2. demo impact
3. actual backend support
4. engineering feasibility
5. measurable usefulness.

Do not add decorative/fake features merely to match the PDF.

## Evaluation

Dataset A:
- DEV
- blind HELD-OUT
- blind HARD-NEGATIVES.

Dataset B is separate.

B1 positive evidence:
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
- hard-negative false-HIGH_CONFIDENCE rate.

Day 17:
- genuine blind held-out result.

Day 18:
- post-correction result; never present it as an independent blind test.

### Current Evaluation Implementation

Dataset A feature extraction/evaluation pipeline exists.

Current Dataset A evaluator is a **score-only benchmark** because Dataset A records currently lack enough category/critical-field information for the production critical-gate logic.

- DEV is used for threshold selection.
- Selected threshold is evaluated on HELD-OUT.
- Hard negatives are evaluated separately.
- Production scoring includes `other_attributes_similarity = 1.0` when both sides have no other attributes.
- Evaluator must remain aligned with production scoring.
- Weak labels are not ground truth.
- Final dataset-level production-style evaluation is still pending.

### Evaluation Working Tree

There is newer untracked evaluation work:
- `backend/app/services/evaluation/synthetic/`
  - `generator.py` implemented
  - `transformations.py` implemented
  - `hard_negatives.py` currently empty
  - `splits.py` currently empty
  - `__init__.py` empty
- generated evaluation datasets/features are local/untracked.

Do not accidentally commit unfinished/generated evaluation artifacts with unrelated frontend work.

## Data / Tender Handling

Useful unit from tender/BOQ sources is the material/item record, not the tender itself.

- retain material/item descriptions and technical specifications
- strip rate/price information
- preserve source/CPSE provenance where appropriate
- extract material codes where available
- preserve manufacturer, part number, grade, dimensions, unit and other technical attributes where available
- do not assume public accessibility implies redistribution rights
- raw tender documents do not automatically constitute final Dataset B
- inspect actual samples before finalizing ingestion assumptions
- public-source collection must respect access controls and applicable terms
- large local datasets must not be casually committed to Git.

## Git / Repository Status

Repository:
- GitHub remote: `https://github.com/AshIndian-Coder/MIRA.git`
- branch: `main`.

Latest relevant history:
- `9c14188` — `Complete frontend integration and cleanup`
- `8870eb9` — `Refactor schema for cpses, users, and materials tables`
- `2c178ab` — `project memory`

The frontend commit was rebased cleanly onto the remote schema refactor and pushed successfully.

Untracked local artifacts remain intentionally outside the frontend commit:
- `backend/app/services/evaluation/synthetic/`
- `data/evaluation/*.csv`
- `data/evaluation/features/`
- `data/evaluation/synthetic/`
- `data/processed/`
- `data/raw/`
- `data/training/`
- `makt.csv`
- `mara.csv`
- `mard.csv`

Do **not** use `git add .` until these artifacts have an explicit repository policy.

`.gitignore` already covers Python caches, virtual environments, frontend/node build artifacts, local environments, logs, database dumps, model/cache directories and temporary/generated exports.

It does not currently ignore all raw/processed/training datasets, so their repository policy needs deliberate treatment.

## Testing

Backend:

```bash
cd ~/Desktop/mira/backend && PYTHONPATH=. pytest -q