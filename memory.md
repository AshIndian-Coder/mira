# MIRA — Project Memory

## Project

**SIH26099 — AI-Driven Standardization and Harmonization of Material Codes Across CPSEs**

**Deadline:** 18 days hard freeze.

## Team Roles

* Person 1 — Data & Evaluation
* Person 2 — Matching Engine
* Person 3 — Backend & Database
* Person 4 — Frontend & Review + frontend-facing API integration
* Person 5 — Integration, Clustering & Demo
* Person 6 — Coordination, documentation, testing and presentation

## Frozen Architecture

CPSE Material Master → Ingestion → Normalization/Units → Parser/Attribute Extraction → Category/Blocking → Candidate Generation → Hybrid Scoring → Critical Gates → HIGH_CONFIDENCE/REVIEW/DIFFERENT → Human Review → Approved Relationships → Clustering/Conflict Detection → Common Material Record → Common National Material Code → CPSE Code Mapping → Audit/Export/API.

## AI Architecture

MIRA uses a layered AI approach.

### Core AI

* Local `all-MiniLM-L6-v2` sentence-transformer for semantic similarity.
* Embeddings run locally/on-premises.
* Semantic similarity is one component of the frozen hybrid score.
* AI similarity never directly approves a material.

### AI-Assisted Attribute Extraction

* Deterministic normalization, regex parsing, technical dictionaries and unit handling are the first extraction layer.
* An LLM may be used as an optional fallback for messy or ambiguous procurement descriptions.
* LLM output must be structured before entering matching.
* Uncertain or missing critical attributes remain UNKNOWN.
* LLM output cannot override critical conflicts or directly approve equivalence.
* The provider must remain replaceable.

### Intelligent Classification

* Material categorization is part of the AI-assisted pipeline.
* MVP classification may combine deterministic rules, normalized attributes and embedding/category similarity.
* A trained classifier may be added if sufficient reliable labels exist.
* Classification does not override critical technical gates.

## Frozen Decisions

* Preserve every original CPSE material code.
* Never overwrite source records with a common code.
* `final_score = 0.20 text + 0.20 semantic + 0.35 specification + 0.15 material/grade + 0.10 other attributes`.
* Only numeric weights may be tuned on DEV; formula shape is frozen.
* Score is calculated before gates.
* Missing applicable critical fields = UNKNOWN → REVIEW.
* Conflicting critical fields → REVIEW.
* No fixed 0.92 auto-accept rule.
* Text/semantic similarity alone cannot safely approve a material.
* AI/LLM output cannot directly approve equivalence.
* Critical canonical specifications are never invented, averaged or majority-voted.
* LLM extraction is optional enhancement, not a core dependency.
* Core matching must function without a cloud LLM.
* UNSPSC is optional supporting classification/blocking/analytics, not a dependency.
* Common National Material Code is an explicit SIH capability; exact syntax is our design decision.
* Common Material approval requires safe canonical fields; critical UNKNOWN blocks APPROVED.
* SAP/ERP integration is represented by integration-ready REST/CSV interfaces; no live SAP claim without an actual integration.
* Matching logic is treated as frozen pending proper DEV/HELD-OUT evaluation.
* Do not create a separate parser for every CPSE. Generic ingestion should handle unfamiliar document structures unless a recurring structural need is demonstrated.

## SIH Requirement Coverage

The implementation covers AI matching, duplicate/near-duplicate/equivalent identification, standardization, intelligent classification, Common National Material Code generation/recommendation, CPSE mapping, legacy rationalization/migration, human validation, dashboard analytics, audit/governance, SAP/ERP integration capability and One Nation — One Material Code traceability.

## Evaluation

Dataset A consists of:

* DEV
* blind HELD-OUT
* blind HARD-NEGATIVES

Dataset B is separate.

B1 requires positive evidence via:

* matching manufacturer part number, OR
* matching industry/standard designation, OR
* complete structured specifications without critical conflict.

If fewer than 50 qualifying agreed B1 pairs exist by end of Day 4, switch to B2.

Report:

* precision
* recall
* F1
* automation rate
* aggregate false-positive rate
* hard-negative false-HIGH_CONFIDENCE rate

**Day 17:** genuine blind held-out result.

**Day 18:** post-correction result; never present it as an independent blind test.

### Current Evaluation Implementation

* Dataset A feature extraction and evaluation pipeline exists.
* The current Dataset A evaluator is a **score-only benchmark** because the Dataset A records currently do not contain sufficient category/critical-field information for the production critical-gate logic.
* DEV is used for threshold selection.
* The selected threshold is then evaluated on HELD-OUT.
* Hard negatives are evaluated separately for false-HIGH_CONFIDENCE rate.
* Production scoring includes `other_attributes_similarity = 1.0` when both sides have no other attributes; the Dataset A evaluator must be kept aligned with production scoring before final reported results.
* Weak labels are not ground truth and must not be presented as verified training labels.
* Final dataset-level production-style evaluation is still pending.

## Dataset / Tender Data

The useful unit from tender/BOQ sources is the material/item record, not the tender itself.

* Retain material/item descriptions and technical specifications.
* Strip rate/price information.
* Preserve source/CPSE provenance where appropriate.
* Extract material codes where available.
* Preserve manufacturer, part number, grade, dimensions, unit and other technical attributes where available.
* Do not assume public accessibility implies redistribution rights.
* Raw tender documents do not automatically constitute final Dataset B.
* Actual samples must be inspected before finalizing ingestion assumptions.
* Public-source collection must respect access controls and applicable terms.
* Large local datasets must not be casually committed to Git.

## Backend Status

### Core matching implementation

Implemented:

* FastAPI foundation
* normalization
* rule-based technical parsing
* local `all-MiniLM-L6-v2`
* candidate blocking
* frozen weighted hybrid scoring
* category-aware specification similarity
* critical gates
* HIGH_CONFIDENCE/REVIEW/DIFFERENT classifier
* `POST /api/matching/compare`
* regression tests

Verified:

* equivalent valve descriptions → HIGH_CONFIDENCE, observed final score 0.9148
* conflicting pressure rating → REVIEW
* missing critical pressure rating → REVIEW

### Ingestion Architecture — Current State

The ingestion system has been simplified to a **generic-first architecture**.

Completed cleanup:

* Removed CPSE-specific BHEL adapter.
* Removed BHEL technical adapter.
* Removed NALCO adapter.
* Removed BHEL parser.
* Removed NALCO parser.
* Removed NTPC parser.
* Removed adapter registry.
* Removed old ingestion service.
* Removed old record-combination/export/enrichment modules that were part of the previous CPSE-specific pipeline.
* Removed CPSE-specific detection rules from `document_inspector.py`.
* Removed hardcoded CPSE inference from the generic adapter.
* Removed `cpse_hint` from the generic ingestion pipeline.
* `GenericAdapter` now operates without CPSE-specific constructor hints.
* Generic records use `cpse="UNKNOWN"` when CPSE information is not available.
* `document_inspector.py` now performs generic document inspection rather than identifying documents by hardcoded CPSE rules.
* `pipeline.py` now uses the generic adapter without CPSE-specific imports or dynamic parser loading.
* Pipeline report type is now `generic`.
* No deleted ingestion module should be reintroduced unless a concrete recurring document structure requires it.

Current principle:

**Do not encode CPSE identity as parser logic. Extract the material record generically and preserve CPSE provenance as data when available.**

### Deterministic Specification Parsing

The deterministic parser remains authoritative.

Verified extraction includes:

* voltage ranges
* frequency
* power ranges
* CCT
* CRI
* beam angle
* IP rating
* luminous efficiency
* material grade and existing technical fields

The HCL real document produced one valid record and correctly extracted:

* 80–140 V
* 50 Hz
* 18–20 W
* CCT 5700–6500 K
* CRI 70
* beam angle 120 DEG
* IP 66
* > =130 LM/W

The HCL record did **not** invoke the LLM because its unmapped evidence was technical rather than evidence of missing identity fields.

### Parser Regression Fix — 2026-09-13

A pre-existing parser test failure was found:

```text
tests/test_parsing.py::test_multiple_dimension_tokens
PIPE OD60.3 X 5.54THK MM
```

The parser previously represented the OD/thickness expression as one combined `OD_THICKNESS` token.

It was changed so the expression produces separate tokens:

* OD → 60.3 MM
* THICKNESS → 5.54 MM

Result:

**48/48 pytest tests pass.**

This parser change is included in the current staged work.

### LLM Fallback

Implemented under `backend/app/services/ingestion/llm/`:

* provider abstraction
* Ollama/local provider
* Groq provider
* JSON parser
* prompts
* resolver
* extraction service

Current providers:

* `none`
* `local` / Ollama
* `groq`

Current Groq model used for testing:

`openai/gpt-oss-20b`

Current strict LLM schema:

* `material_grade`
* `manufacturer`
* `manufacturer_part_number`
* `model`
* `dimensions`

`other_specifications` was intentionally removed because the model could return description-like text as a supposed specification.

Observed performance:

* local Phi-4-mini: roughly 11–15 seconds for small extraction tests
* Groq GPT-OSS 20B: roughly 1.1 seconds wall time for a comparable small extraction

Resolver rules:

* deterministic values remain authoritative
* LLM only fills missing fields
* deterministic/LLM conflicts are recorded in `raw_attributes["llm_conflicts"]`
* LLM cannot directly approve equivalence
* LLM failure must not break ingestion
* missing fields alone do not trigger the LLM
* low/medium extraction confidence can trigger escalation
* explicit ambiguity can trigger escalation
* explicit labels such as `MOC:`, `MANUFACTURER:`, `MAKE:`, `MODEL:`, `PART NO:` and dimension labels can trigger escalation
* generic unmapped technical lines alone do not trigger escalation
* evidence construction is separated into `build_evidence_text(record)`

Targeted policy tests passed:

* missing manufacturer with no evidence → no LLM
* unmapped `MAKE:` evidence → LLM
* low confidence → LLM
* complete deterministic record → no LLM

Integrated HCL test:

* 1 record
* valid
* LLM enabled when configured with Groq
* LLM not used
* deterministic technical parsing preserved

Synthetic integrated LLM recovery test:

* grade, manufacturer, part number and model successfully recovered
* no conflicts

Current conclusion:

**LLM extraction is functional and remains optional fallback/stretch functionality. Deterministic extraction and matching remain the core path.**

### Real-data ingestion status

Observed:

* NTPC: 16,772 enriched records
* BHEL: 7
* NALCO: 6
* combined tested set: 16,785
* HCL: 1/1 valid through generic fallback
* NALCO: 6/6 valid
* BHEL/GAIL-style sample: 7/7 valid
* BPCL generic component extraction successfully tested

Still requiring focused end-to-end testing:

* APGENCO
* CPCL
* MDL
* full BPCL document

Note: Previous CPSE-specific parser implementations for BHEL/NALCO/NTPC have now been removed. The above figures are historical validation observations, not evidence that those specialized parsers remain in the current source.

## Phase 5/6 API Surface

Implemented:

* `app/store.py` — Postgres-backed MATERIALS + CANDIDATES via `app/db_adapter.py` (`PersistentList`/`DBRow`; list-compatible interface, write-through mutation)
* `POST /api/materials/upload` — CSV ingestion → store
* `GET /api/materials` — list with query/CPSE/category filters + pagination
* `GET /api/materials/stats` — summary counts
* `GET /api/materials/{id}`
* `POST /api/matching/run-batch` — blocking + scoring across ingested materials
* `GET /api/matching/candidates` — filtered candidate list
* `GET /api/matching/candidates/{id}`
* `GET /api/matching/stats` — automation rate, blocking reduction, score percentiles
* `GET /api/review/queue` — real REVIEW-decision candidates
* `POST /api/review/queue/{id}/action` — APPROVE/REJECT with audit emission
* `GET /api/review/summary`
* `GET /api/audit`
* `GET /api/audit/export`
* `GET /api/analytics/overview`
* `GET /api/analytics/by-cpse`
* `GET /api/analytics/categories`
* `GET /api/analytics/scores`
* `POST /api/mappings/generate` — Union-Find based NMC generation from APPROVED pairs
* `GET /api/mappings`
* `GET /api/mappings/{id}`
* `GET /api/mappings/export/flat`
* `GET /` — landing page
* `GET /health` unchanged

### PostgreSQL Persistence

PostgreSQL persistence is active.

Runtime state moved from in-memory Python lists to PostgreSQL.

Implemented:

* `backend/mira_full_schema.sql`
* `backend/app/db_adapter.py`
* `backend/app/store.py`
* DB-backed mappings
* DB-backed audit events
* landing page
* local setup documentation
* README/API documentation

Important behavior:

* `PersistentList` provides list-compatible DB-backed operations.
* `DBRow` performs write-through updates.
* IDs remain restart-safe.
* `reset_stores()` clears dependent candidate rows before materials to preserve foreign-key integrity.
* Audit export converts the persistent collection to a JSON-serializable list.

Verified:

* upload → match → approve → mappings → audit → analytics over real PostgreSQL
* data survives backend restart
* post-restart IDs continue without collisions
* PostgreSQL is the active runtime store

### Backend Limitations Still Remaining

* pgvector persistence/search is not yet wired into the active API pipeline.
* SAP integration is not a live connection; current architecture is integration-ready.
* End-to-end integration tests for `run-batch` should still be added.
* Real tender/BOQ data may require parser and blocking adjustments.
* Dataset-level production-style evaluation still needs to be completed.
* Clustering and conflict detection still need verification against approved relationships.

## Frontend Status

Completed screens:

* Dashboard
* Materials
* Match Review
* Common Materials
* Mappings
* ERP Integration
* Analytics
* Audit Trail
* Settings

Frontend architecture:

* React
* Vite
* TypeScript
* modular pages/components/services/types
* enterprise/master-data-management style UI

Current state:

* Frontend screens are implemented.
* API wiring is the next major frontend task.
* Person 4 owns frontend-facing API integration.
* Match Review remains the most important workflow screen.

Primary workflow:

Upload → Materials → Matching → HIGH_CONFIDENCE/REVIEW/DIFFERENT → Human Review → Approved → Common Material → CPSE→NMC Mapping.

## Repository / Git / Data Handling

Repository:

* GitHub remote: `https://github.com/AshIndian-Coder/MIRA.git`
* Local branch: `main`

Current staged cleanup work:

* Qwen experiment renamed:

  * `backend/app/ml_pipeline/test_qwen.py`
  * → `backend/app/ml_pipeline/qwen_experiment.py`
* CPSE-specific ingestion modules removed.
* Generic ingestion modules updated.
* Parser regression fixed.
* `git diff --cached --check` is clean.
* Full staged test suite: **48 passed, 0 failed**.

The Qwen rename was required because `test_qwen.py` was being collected by pytest and attempted to download `Qwen/Qwen3-Embedding-0.6B` during test collection.

The Qwen model was not present in the Hugging Face cache; only `all-MiniLM-L6-v2` was substantially cached.

The Qwen experiment remains available as `qwen_experiment.py` but is no longer automatically collected as a pytest test module.

### Current Git Status

Intended staged changes currently include:

* Qwen experiment rename
* ingestion adapter cleanup
* generic adapter changes
* document inspector cleanup
* ingestion pipeline cleanup
* removal of obsolete CPSE-specific parsers/adapters/services
* parser regression fix

Unrelated local artifacts remain intentionally **unstaged**:

* `backend/app/services/evaluation/synthetic/`
* `data/evaluation/dataset_a_dev.csv`
* `data/evaluation/dataset_a_hard_negatives.csv`
* `data/evaluation/dataset_a_heldout.csv`
* `data/evaluation/features/`
* `data/evaluation/synthetic/`
* `data/processed/`
* `data/raw/`
* `data/training/`
* `makt.csv`
* `mara.csv`
* `mard.csv`

Do **not** use `git add .`.

`service.py.bak` was explicitly deleted and should not be restored.

### Test Command

Because of the repository/backend import layout, run pytest from the backend directory:

```bash
cd ~/Desktop/mira/backend && PYTHONPATH=. pytest -q
```

Current result:

```text
48 passed
```

## Immediate Next Action

### Git

The cleanup changes are staged and verified.

Commit command:

```bash
cd ~/Desktop/mira && git commit -m "Clean up ingestion pipeline and parser"
```

Do not commit unrelated untracked data/evaluation artifacts.

After commit, verify the commit and push only after confirming the commit succeeded.

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
3. Complete Dataset A DEV/HELD-OUT evaluation.
4. Align evaluator scoring exactly with production scoring.
5. Consolidate duplicate candidate-generation implementations and avoid unnecessary O(n²) cross-CPSE loops.
6. PostgreSQL persistence is DONE; remaining database-side work is pgvector search integration.
7. Implement/verify clustering and conflict detection against approved relationships.
8. Optional: LLM-assisted attribute extraction fallback.
9. Do not add actual model training unless it improves validated performance and can be evaluated properly.

## Current Project Principle

**Similarity finds the candidate. Specifications decide whether it is safe. Humans control the final mapping.**

Evaluation principle:

**Evaluate against held-out ground truth, not against data used to design the matcher.**

Product principle:

**Preserve CPSE source codes and create a traceable common material representation/code rather than replacing the source master.**
