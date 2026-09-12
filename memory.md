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

****Day 17:**** genuine blind held-out result.

****Day 18:**** post-correction result; never present it as an independent blind test.

### Current Evaluation Implementation

- Dataset A feature extraction and evaluation pipeline exists.

- The current Dataset A evaluator is a ****score-only benchmark**** because the Dataset A records currently do not contain sufficient category/critical-field information for the production critical-gate logic.

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

- There is ****not yet a verified trained ML classifier****.

- Do not claim that MIRA has trained/fine-tuned its own classifier unless this is actually implemented and evaluated.

### Phase 5/6 API surface

Implemented:

- `app/store.py` — Postgres-backed MATERIALS + CANDIDATES via `app/db_adapter.py` (`PersistentList`/`DBRow`; list-compatible interface, write-through mutation). See "Latest Update — 2026-09-12".

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

- `GET /api/mappings/{id}`

- `GET /api/mappings/export/flat`

- `GET /` — landing page (service status + links); `GET /health` unchanged

### Backend limitations still remaining

- PostgreSQL persistence **is now** the active material/candidate/mapping/audit store (done 2026-09-12, see Latest Update below).

- pgvector persistence/search is not yet wired into the active API pipeline.

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

6. PostgreSQL persistence is DONE (2026-09-12); remaining is pgvector search integration only.

7. Implement/verify clustering and conflict detection against approved relationships.

8. Optional: LLM-assisted attribute extraction fallback (stretch only).

9. Do not add actual model training unless it improves validated performance and can be evaluated properly.

## Current Project Principle

**Similarity finds the candidate. Specifications decide whether it is safe. Humans control the final mapping.**

Evaluation principle:

**Evaluate against held-out ground truth, not against data used to design the matcher.**

Product principle:

**Preserve CPSE source codes and create a traceable common material representation/code rather than replacing the source master.**


## Latest Update — 2026-09-11

### Ingestion / LLM Work Completed

The ingestion architecture and optional LLM fallback have now been implemented and targeted-tested.

#### Ingestion architecture

- Added `MaterialRecord` canonical model.
- Added `ParsedDocument`, adapter base and registry.
- Added weighted `DocumentInspector`.
- Added generic fallback extraction for unfamiliar/new report structures.
- Added enrichment and validation flow.
- Added labeled-field extraction and robust identifier/part-number extraction.
- Pipeline order is now:
  `PDF extraction → document inspection → adapter selection → deterministic enrichment → optional LLM escalation → validation`.
- Specialized adapters remain preferred, but generic fallback is used when a specialized adapter produces no records.
- No separate parser should be created for every CPSE; adapters should represent recurring document structures.

#### Deterministic specification parsing

The deterministic parser remains authoritative.

Verified extraction includes:

- voltage ranges
- frequency
- power ranges
- CCT
- CRI
- beam angle
- IP rating
- luminous efficiency
- material grade and existing technical fields

The HCL real document produced one valid record and correctly extracted:

- 80–140 V
- 50 Hz
- 18–20 W
- CCT 5700–6500 K
- CRI 70
- beam angle 120 DEG
- IP 66
- >=130 LM/W

The HCL record did **not** invoke the LLM because its unmapped evidence was technical rather than evidence of missing identity fields.

#### LLM fallback

Implemented under `backend/app/services/ingestion/llm/`:

- provider abstraction
- Ollama/local provider
- Groq provider
- JSON parser
- prompts
- resolver
- extraction service

Current providers:

- `none`
- `local` / Ollama
- `groq`

Current Groq model used for testing:

`openai/gpt-oss-20b`

Current strict LLM schema:

- `material_grade`
- `manufacturer`
- `manufacturer_part_number`
- `model`
- `dimensions`

`other_specifications` was intentionally removed because the model could return description-like text as a supposed specification.

Observed performance:

- local Phi-4-mini: roughly 11–15 seconds for small extraction tests
- Groq GPT-OSS 20B: roughly 1.1 seconds wall time for a comparable small extraction

LLM recovery test succeeded:

- grade → `AISI 410`
- manufacturer → `ABC Industries`
- part → `FL-120-ABC`
- model → `X200`

Resolver rules:

- deterministic values remain authoritative
- LLM only fills missing fields
- deterministic/LLM conflicts are recorded in `raw_attributes["llm_conflicts"]`
- LLM cannot directly approve equivalence
- LLM failure must not break ingestion
- missing fields alone do not trigger the LLM
- low/medium extraction confidence can trigger escalation
- explicit ambiguity can trigger escalation
- explicit labels such as `MOC:`, `MANUFACTURER:`, `MAKE:`, `MODEL:`, `PART NO:` and dimension labels can trigger escalation
- generic unmapped technical lines alone do not trigger escalation
- evidence construction is separated into `build_evidence_text(record)`

Targeted policy tests all pass:

- missing manufacturer with no evidence → no LLM
- unmapped `MAKE:` evidence → LLM
- low confidence → LLM
- complete deterministic record → no LLM

Integrated HCL test:

- 1 record
- valid
- LLM enabled when configured with Groq
- LLM not used
- deterministic technical parsing preserved

Synthetic integrated LLM recovery test:

- grade, manufacturer, part number and model successfully recovered
- no conflicts

Current conclusion:

**LLM extraction is functional and should remain optional fallback/stretch functionality. Deterministic extraction and matching remain the core path.**

### Real-data ingestion status

Observed:

- NTPC: 16,772 enriched records
- BHEL: 7
- NALCO: 6
- combined tested set: 16,785
- HCL: 1/1 valid through generic fallback
- NALCO: 6/6 valid
- BHEL/GAIL-style sample: 7/7 valid
- BPCL generic component extraction successfully tested

Still requiring focused end-to-end testing:

- APGENCO
- CPCL
- MDL
- full BPCL document

### Current Git state

Latest source changes have been staged selectively for a dedicated commit.

Intended commit contents:

- ingestion adapter architecture
- generic adapter
- document inspector
- enrichment
- extraction helpers
- LLM fallback
- ingestion pipeline
- MaterialRecord changes
- parsing service changes

Intentionally excluded:

- all local `data/` files
- `backend/app/services/parsing/service.py.bak`

`git diff --cached --check` initially found trailing whitespace in `resolver.py` and `pipeline.py`; those files were cleaned and re-staged.

Recommended commit message:

`Add robust document ingestion and LLM fallback`

Do not use `git add .` because local `data/` must remain outside the commit.

### Immediate continuation point

1. Finish the clean ingestion/LLM Git commit and push.
2. Add/verify `run-batch` integration tests.
3. Test APGENCO, CPCL and MDL real documents.
4. Complete Dataset A DEV/HELD-OUT evaluation.
5. Align evaluator scoring with production scoring.
6. Continue frontend API wiring.
7. PostgreSQL persistence completed 2026-09-12 (PR #1); remaining here is pgvector integration and clustering verification.

## Latest Update — 2026-09-12

### Postgres persistence completed (PR #1)

All runtime state moved from in-memory Python lists to PostgreSQL. Data now
survives server restarts with **zero logic changes** to any route.

#### Files (branch `arena/01a095f9-mira` → PR #1 into `main`)

- `backend/mira_full_schema.sql` — NEW, 9 tables mirroring the exact dict
  shapes the routes already produce (`cpses`, `users`, `upload_batches`,
  `materials`, `match_suggestions`, `cnmc`, `mappings`, `feedback`,
  `audit_logs`).
- `backend/app/db_adapter.py` — NEW persistence engine: `PersistentList`
  (`.append()`/`.extend()`/`.clear()`/iteration/`len()`, DB-backed),
  `DBRow` (dict subclass with write-through `UPDATE` on key assignment),
  `next_id()` (max-id + 1, restart-safe), ISO-string → `TIMESTAMP`
  auto-coercion.
- `backend/app/store.py` — rewritten: `MATERIALS`/`CANDIDATES` are now
  `PersistentList`s; `next_candidate_id()` uses a self-reseeding in-memory
  cache (batch-safe: `matching.py` mints all IDs before one `.extend()`);
  `reset_stores()` clears candidates BEFORE materials (FK-safe order).
- `backend/app/api/routes/mappings.py` — `MAPPINGS` now DB-backed.
- `backend/app/api/routes/audit.py` — `AUDIT_EVENTS` now DB-backed.
- `backend/app/main.py` — added landing page at `GET /` (was 404).
- `LOCAL_SETUP.md` — NEW simple local run guide (Windows-first).
- `README.md` — rewritten (was a 2-line stub): quickstart, API table,
  persistence notes, repo layout, docs index.
- `materials.py`, `matching.py`, `review.py`, `analytics.py` — zero changes.

#### Bugs found and fixed during verification (live Postgres)

1. `reset_stores()` cleared `materials` before `match_suggestions` →
   `ForeignKeyViolation`. Fixed deletion order.
2. `GET /api/audit/export` returned raw `PersistentList` → not
   JSON-serializable. Wrapped in `list()` (same response shape).

#### Verification evidence

- Schema applies cleanly; upload → match → approve → mappings → audit →
  analytics all pass over HTTP against real Postgres.
- Restart test: 5 materials, 5 candidates, APPROVED status with reviewer +
  comments + timestamp, audit events, mappings — all survive restart.
- Post-restart inserts continue IDs with zero collisions
  (materials 6, 7…; candidates 6–12).
- Existing pytest suite: 38 passed; 8 failures are pre-existing and
  environmental only (sandbox could not reach huggingface.co to download
  `all-MiniLM-L6-v2`); no test touches `store`.
- Matching's semantic step was stubbed (difflib) in the sandbox ONLY
  (`/tmp`, never committed) due to no HuggingFace access; production
  machines load the real local model normally.

#### Local-run gotchas documented (in `LOCAL_SETUP.md`)

- `torch==2.14.0+cpu` is not on PyPI → install from the PyTorch CPU index
  first, then `pip install -r requirements.txt`.
- `DATABASE_URL` passwords containing `@` must be URL-encoded (`%40`).
- `.env` belongs in `backend/` (where uvicorn runs), never committed.

### Continuation point after this update

1. Merge PR #1 into `main`.
2. Frontend API wiring (Person 4) can now rely on persistent data.
3. Remaining backend: `run-batch` integration tests, pgvector search,
   clustering/conflict verification, Dataset A DEV/HELD-OUT evaluation.

## EOF
