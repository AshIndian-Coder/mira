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

### Parser Fix — Nominal Bore + Schedule — 2026-09-17

A real nominal-bore parsing bug was identified during a production-faithful DEV audit.

Problem:
- `PIPE SS 304 NB 80 ...` was incorrectly parsed as `nominal_bore = 304 NB`.
- `PIPE SS 316 NB 200 ...` was incorrectly parsed as `316 NB`.
- `PIPE SS 304 NB 600 ...` was incorrectly parsed as `304 NB`.

Root cause:
- The existing suffix-form `NB_PATTERN` could match the material-grade number before the `NB` token.

Fix:
- Added `NB_PREFIX_PATTERN`.
- Prefix form (`NB 80`, `NB 200`, `NB: 25`, `NB-600`, `NB80`) is now checked before the existing suffix form.
- Existing suffix forms such as `50NB`, `50 NB`, `25MMNB` remain supported.

Schedule extraction was also added:
- `SCH40`, `SCH 40`, `SCHEDULE 40` → `SCH40`
- `SCH80`, `SCH 80`, `SCHEDULE 80` → `SCH80`
- `SCH XS`, `SCHEDULE XS` → `SCHXS`

Regression validation:
- Parsing tests: 27 passed.
- Full backend tests: 72 passed.
- Direct verification confirmed correct nominal bore and schedule extraction for representative SS304/SS316 pipe descriptions.

No scoring, critical-gate, Qwen/model, CNMC or mapping logic was changed as part of this fix.

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
- Production-faithful DEV auditing has now been performed on the exact 5,228 DEV pairs; however, final blind held-out evaluation of the production pipeline remains pending.
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

### Frontend Completion & UI Polish

Completed, polished, and verified:
- Materials API integration
- CSV upload
- batch matching trigger
- Match Review queue & AI score progress meters
- approve/reject actions
- Dashboard analytics
- Common Materials/mappings & inspection modal
- mapping generation/export
- ERP export preparation
- Analytics & Audit Trail decluttering
- truthful Settings/capability display
- loading/error/empty states
- removal of unused legacy services/types
- removal of Vite starter assets.

### Frontend Design System & Layout Architecture (2026-09-13)

- **Typography & Motion**: Plus Jakarta Sans headers, Inter data surfaces, JetBrains Mono codes; physics spring curve `cubic-bezier(0.16, 1, 0.3, 1)`.
- **Floating Island Frame Architecture**:
  - **Non-Scrolling Sidebar Frame**: `.sidebar` has fixed dimensions (`width: 252px; height: 100%; flex-shrink: 0;`), `overflow: hidden;`, and `border-radius: var(--radius-xl)` (16px), maintaining constant dimensions across all views with zero scrolling.
  - **Scroll-Contained Main Content Frame**: `.main-content` enclosed in a rounded frame (`border-radius: 16px; overflow: hidden;`), Topbar locked at top (`58px`), with independent `.page` vertical scrolling.
  - **Uniform Separation**: `.app-shell` applies uniform `12px` outer padding and `12px` gap across frames over `#ebf0f5`.
- **Analytics & Chart Motion**:
  - `maxBarSize={44}` and `allowDecimals={false}` on Recharts bar charts.
  - Smooth hardware-accelerated tooltip cursor glide (`transition: transform 120ms`) with spring pop entrance and subtle rounded cursor highlight replacing harsh rectangular block cursors.
- **Audit Trail Formatting**:
  - 3-column summary cards, single-line `white-space: nowrap` on long mapping identifiers and timestamps.

Frontend production build passed cleanly.

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
- Production-faithful DEV auditing has now been performed on the exact 5,228 DEV pairs, but final blind held-out evaluation of the production pipeline remains pending.

### Production-Faithful DEV Audit — 2026-09-17

The exact 5,228 DEV pairs from `Training_Pairs_MIRA_FINAL.csv` were evaluated through the production normalization + parsing + matching path.

After the nominal-bore parser fix:
- DEV pairs: 5,228
- Decisions: REVIEW 3,109 / DIFFERENT 2,119
- Exact `HN_*` subset: 915 pairs
- HN-FHC @ 0.85: 5 / 915 = 0.55%
- Negative DEV pairs scoring ≥0.85: 5 / 1,567 = 0.32%

The previously observed high-score negative cases were substantially reduced after correcting nominal-bore extraction.

The remaining five ≥0.85 negatives were inspected individually. Several have descriptions that normalize and parse to effectively identical technical specifications despite being labelled negative, so no production scoring/gate change was made based on these cases.

Important:
- This production audit is distinct from direct embedding-model evaluation.
- Do not compare production-classifier HN-FHC directly with embedding-only HN-FHC unless the metric definition and evaluated subset are identical.

### Direct Embedding Baseline — 2026-09-17

`all-MiniLM-L6-v2` was evaluated directly on the exact 5,228 DEV pairs.

Results:
- DEV threshold: 0.461
- Precision: 0.8006
- Recall: 0.9956
- F1: 0.8875
- Exact HN-FHC @ 0.85: 28.74% (263 / 915)

This is an embedding-only evaluation and is separate from the production hybrid matcher.

Earlier MiniLM HN-FP figures based on all 1,567 negative DEV pairs should not be treated as the exact HN-FHC metric. The correct HN-FHC calculation uses the 915 `HN_*` DEV pairs.

### Qwen Training / Evaluation — 2026-09-17

Abhishek's Qwen semantic-model training is still running.

Latest reported DEV checkpoint:
- DEV pairs: 5,228
- DEV threshold: 0.767
- DEV F1: 0.9259
- DEV precision: 0.8673
- DEV recall: 0.9929
- HN-FHC @ 0.85: 59.13%

This is a training-time Qwen result reported by the teammate and is not yet the final run.

Do not treat the current checkpoint as final model performance until training finishes and the final checkpoint is evaluated.

Triplet pairs are used for Qwen training; they are not required for the independent MiniLM baseline evaluation.

### Embedding Model Comparison — Current State

Current reported DEV results:

| Metric | Qwen | MiniLM |
|---|---:|---:|
| DEV pairs | 5,228 | 5,228 |
| DEV threshold | 0.767 | 0.461 |
| Precision | 0.8673 | 0.8006 |
| Recall | 0.9929 | 0.9956 |
| F1 | 0.9259 | 0.8875 |
| HN-FHC @ 0.85 | 59.13% | 28.74% |

Caution:
- Qwen and MiniLM use the same DEV pair population, but HN-FHC should only be compared if both evaluations use exactly the same `HN_*` subset and metric implementation.
- Qwen training is not finished.
- No decision has been made to replace MiniLM with Qwen.
- A future ensemble of Qwen + MiniLM may be investigated only after final Qwen evaluation.

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

## Git / Repository Status — 2026-09-18

Repository:
- GitHub remote: `https://github.com/AshIndian-Coder/MIRA.git`
- branch: `main`

Recent commits:
- `eb77c34` — `Fix nominal bore parsing with material grades`
- Previous commits remain in history.

Current intentional unstaged/untracked local evaluation/data artifacts include:
- `backend/app/services/evaluation/feature_extraction.py`
- `Training_Pairs_MIRA_FINAL.csv`
- `backend/app/services/evaluation/synthetic/`
- `data/evaluation/`
- `data/processed/`
- `data/raw/`
- `data/training/`
- `makt.csv`
- `mara.csv`
- `mard.csv`

Do NOT use `git add .`.

`feature_extraction.py` currently contains a separate evaluation-correctness change that applies production normalization before parsing during evaluation. It should be committed separately from the nominal-bore parser fix after its focused tests are verified.

The generated datasets and evaluation CSVs are local working artifacts and should not be committed unless repository policy explicitly requires them.

## Master Training Dataset — 2026-09-15

Built the final master training dataset (`Final_Master_Material_Records.csv`, repo root, ~240 MB, 832,516 rows).

Generator: `backend/app/ml_pipeline/generate_master_dataset.py` (stdlib only, deterministic, per-company RNG seeds).
Regenerate with: `python backend/app/ml_pipeline/generate_master_dataset.py --per-company 5000 --seed 42`

Composition:
- 164 CPSEs across all 11 sectors (Oil & Gas, Petrochemical, Heavy Engineering, Electrical, Steel, Power, Railways, Defence, Ports, EPC, Research) + 18 diversity CPSEs (MSTC, MMTC, PEC, STC, Balmer Lawrie, ITI, KIOCL, Yantra India, Munitions India, FSNL, ECL/SECL/CCL/MCL/WCL, Andrew Yule, NRDC).
- ORIGINAL records from `Original_company_records_no_synthetic.csv` kept verbatim and de-duplicated: 23,717 kept (raw 25,370; 1,653 exact dups removed). NTPC kept fully (17,516) with zero synthetic. OIL 4,701+299; BPCL 968+4,032; IOCL 484+4,516; BHEL/NALCO/WBPDCL/SAIL/HCL topped to 5,000. Every empty cell filled (5,810 codes generated in company format; repeated source codes suffixed `-R2`, `-R3` like revisions).
- SYNTHETIC: 5,000 per remaining company from a 1,437-item sector-gated catalog (bearings, fasteners, valves, pipes, fittings, flanges, gaskets, pumps, motors, transformers, switchgear, cables, instruments, safety, welding, lubricants, chemicals, steel, tools, IT, office, furniture, filters, lifting, boiler, refinery, refractory, rail, marine, fertilizer) with per-company abbreviation/spacing/case personalities, UOM variants + honest KG↔MT conflicts, SAP 40-char truncation for ~35% of companies, typos, and WRONG_SPEC hard negatives.

Columns (16, exact order, zero empty cells): cpse_code, material_code, description, cleaned_description, category, attributes, uom, last_purchase_price, avg_annual_quantity, data_quality_score, status, created_at, true_match_key, canonical_description, quality_flag, noise_tags.

Quality flags: CLEAN 641,801 / TYPO 56,680 / WRONG_SPEC 55,613 / MISSING_ATTR 78,422.
Cross-CPSE duplicate groups (≥5 companies): 1,437; popular groups (BRG 6204/6205/6206/6305 2RS, BOLT HEX M12/M16) span 162–163 of 164 companies.

Validation: empty_cells=0, bad_json=0, dup_keys=0, unknown_cpse=0, cross_material_key=0 (see `generation_report.json`).
PPT demo groups: `sample_groups.txt` (25 groups, e.g. BRG BALL 6205 2RS across 162 companies with rendered variants).

GROUND-TRUTH RULES (do not violate):
- `true_match_key` (format `SIG-<md12>`), `canonical_description`, `quality_flag`, `noise_tags` are LABEL/SPLIT columns only — strip before any model input (AI-Model-Training PDF §5/§9).
- WRONG_SPEC rows carry `true_match_key` suffixed `#CORRUPT` — never a positive pair; they are the hard-negative supply.
- Split by `true_match_key` group, never by row.
- Original `description` text is never modified; synthetic descriptions must not have critical values mutated (typos only hit non-critical alpha tokens).

## Training Pair Manifest — 2026-09-15

Built `Training_Pairs_Final.csv` (repo root, ~26 MB, 170,000 pairs) via `backend/app/ml_pipeline/build_pair_manifest.py` (deterministic, `--seed 42`, 17s runtime).
Regenerate: `python backend/app/ml_pipeline/build_pair_manifest.py --seed 42`

Pair mix: POS 85,000 (label 1, same base true_match_key group; all 1,884 multi-row groups; ≤60/group) · HN_CORRUPT 45,000 (label 0, WRONG_SPEC #CORRUPT row vs clean sibling, text-identical pairs filtered out) · HN_SIBLING 25,000 (label 0, same category + same digit-template, different group: 6205↔6305, CL150↔CL300) · NEG_EASY 15,000 (label 0, cross-category).

Frozen group-level split 90/5/5: 21,860/1,202/1,202 groups → 156,092 train / 6,677 dev / 7,231 heldout pairs. Both members of every pair are in the SAME split. Split is by group hash, stable across regenerations with same seed.

Columns: pair_id, split, pair_type, label, desc_a, desc_b, tmk_a, tmk_b, cpse_a, cpse_b, category. Model input = desc_a/desc_b ONLY; split/tmk/cpse/category are metadata.

Known limitation (honest note for PPT): HN_SIBLING dev/heldout are thin (147/105) because sibling buckets require both groups in the same 5% slice — structural, not a bug. Report sibling-hard-negative metrics primarily on train, and treat dev/heldout sibling numbers as indicative.

Validation (all zero): pair_spans_splits, corrupt_as_positive, identical_desc_pos, same_group_negative, corrupt_text_identical. Details in `pairs_report.json`.

## Inter-CPSE Material Discovery Flow — 2026-09-15

The business payoff of matching is collaborative procurement. Agreed flow:

1. CPSE needs a material → search by description (or pick from own catalog).
2. Matcher resolves it to a CNMC (gates + human approval on new matches).
3. Discovery query: `mappings` (status=approved) → `materials` → `cpses` — every CPSE holding that material with its local code, last_purchase_price, avg_annual_quantity.
4. Demand aggregation: sum(avg_annual_quantity) across CPSEs → pooled-negotiation savings estimate (feeds the ROI Calculator).
5. CPSEs proceed to direct dealing.

Prototype features from this flow (no new tables required):
- "Where else does this exist?" panel on Common Material detail (CPSEs + codes + price + annual qty).
- Demand-aggregation card (combined annual demand + savings estimate).
- Reverse lookup: which materials are held by CPSEs facing shortage.

Honesty rule for PPT and demo: avg_annual_quantity is procurement history, NOT live stock-on-hand. The prototype demonstrates discovery + demand aggregation; live inventory arrives via the SAP connector in deployment.

Matching decision-ladder (implement consistently):
- Descriptions available → full matching engine (embeddings + specs + gates).
- Same CPSE, both have codes → material_code is authoritative within that namespace (intra-CPSE dedup).
- Code present, description missing, different CPSE → resolve only via existing approved mappings (code-registry lookup through CNMC); no mapping → UNKNOWN → human attaches description (REVIEW).
- Neither → manual entry.
- Material codes are NEVER a similarity/matching feature (PDF §5); they are the payload of the mapping layer.
- INTRA-CPSE dedup is a first-class case: candidate generation (vector search) must NOT exclude same-CPSE candidates. Same CPSE + same material_code = identity (no matching). Same CPSE + different codes + similar descriptions = internal duplicate → matcher finds it; it is the easiest, highest-scored case and the most concrete ROI (avoid re-purchasing items already in stores). The NTPC real-records slice is the honest intra-CPSE demo (real duplicates across tenders).

## National Positioning — One Nation One Portal — 2026-09-15

Existing systems (name them in Q&A): SAP MDG / per-CPSE MDM (governs master inside ONE company), GeM/IREPS/CPPP (procurement marketplaces, not identity unification), UNSPSC/e-class (category codes, no mapping from messy descriptions), per-CPSE dedup scripts (one-time, isolated).

The gap MIRA fills: no existing system sees two companies' data at once or governs cross-company equivalence. MIRA is the missing federation layer ABOVE existing ERPs — it does not replace SAP MDG; it federates across instances.

Key sentence: "SAP MDG governs a master inside one company; MIRA governs equivalence across the nation."

Cooperation model (answer to "why will CPSEs agree?"): CPSEs share MAPPINGS, not masters. Data stays in-company; only human-approved, audit-trailed equivalence decisions become national. Per-material adoption is possible; any single joiner gets intra-CPSE dedup value from day one. Minimum-cooperation design, trust engineered into architecture.

PS capability → evidence table (all 11 expected-solution bullets map to built artifacts): matching = hybrid score + 170K pair manifest; duplicate detection = gates + hard negatives; standardization = canonical_description + expander; classification = category taxonomy + UNSPSC; CNMC = schema + generator design; mapping = mappings table + real cross-CPSE code pairs in Training_Pairs_Final.csv; legacy migration = code-registry ladder; review workflow = Match Review Queue; dashboard/analytics = built; audit = audit_logs; SAP = integration-ready connector (honest, not live).

## Testing

Backend:

```bash
cd ~/Desktop/mira/backend && PYTHONPATH=. pytest -q
```

Frontend:

```bash
cd ~/Desktop/mira/frontend && npm run build
```

## Admin User Management Vertical Slice — 2026-09-18

Successfully implemented and verified the complete Admin User Management vertical slice:

- **Backend User API & RBAC:**
  - Standard REST endpoints: `GET /api/users`, `POST /api/users`, `GET /api/users/{id}`, `PUT /api/users/{id}`, `DELETE /api/users/{id}` in [`backend/app/api/v1/users.py`](file:///home/shikhar/Desktop/mira/backend/app/api/v1/users.py).
  - RBAC enforcement: Admin-only access controlled via `@require_permission("manage_users")`.
  - Full Pydantic validation: `UserCreate`, `UserUpdate`, `UserOut`, `UserListResponse` in [`backend/app/schemas/user.py`](file:///home/shikhar/Desktop/mira/backend/app/schemas/user.py).
- **Frontend Admin User Management UI:**
  - Created [`frontend/src/pages/UserManagement/UserManagement.tsx`](file:///home/shikhar/Desktop/mira/frontend/src/pages/UserManagement/UserManagement.tsx) matching the application's clean design system.
  - Role management (`ADMIN`, `REVIEWER`, `OPERATOR`) and dynamic CPSE dropdowns loaded from `/api/cpses`.
  - Create User & Edit User dialogs with auto-contained internal scrollbars.
  - Quick role & status toggles, inline search, and non-admin route shielding.
  - Integrated into Navigation Sidebar (Admin only) and Settings quick links.
- **Verification:** All 84 backend unit tests pass (`pytest`); frontend TypeScript build passes with zero errors (`npm run build`).

## SIH26099 Comprehensive PS Coverage Audit — 2026-09-18

Conducted a thorough, code-level audit of the current working tree against the official SIH26099 problem statement requirements (26 dimensions):

- **Key Findings:** All 26 core functional requirements are implemented in the working tree, including CPSE ingestion, deterministic normalization, unit standardization, multi-attribute parsing, sentence-transformer semantic matching, multi-key blocking, weighted composite scoring, critical safety gates, tri-state classification, human review queue with audit trail, Common Material Record (CMR) synthesis, National Material Code (NMC) generation, and integration-ready ERP boundaries.
- **ROI Work Scope Decision:** ROI & financial savings calculator exploration was completed and formally halted per project instructions to prioritize core SIH26099 material standardization and harmonization deliverables.

## Deterministic Common National Material Code (CNMC) System — 2026-09-18 / 2026-09-19

Implemented and verified the production-grade deterministic CNMC generation and registry system adhering to `MIRA-<TYPE>-<CATEGORY>-<GLOBAL_ID>`:

- **Format & Standards:**
  - Structure: `MIRA-<TYPE>-<CATEGORY>-<GLOBAL_ID>` (e.g. `MIRA-VLV-17-1`, `MIRA-PIP-23-2`, `MIRA-BRG-08-3`).
  - No artificial fixed-width zero padding on global sequence numbers.
- **Deterministic Taxonomy & Type Resolution:**
  - Package: [`backend/app/services/cnmc/taxonomy.py`](file:///home/shikhar/Desktop/mira/backend/app/services/cnmc/taxonomy.py).
  - Short deterministic type codes (`VLV`, `PIP`, `BRG`, `FST`, `ELC`, `GSK`, `CBL`, `FLG`, `PMP`, `GEN`) with stable category numbers and regex inference fallback.
- **Category-Specific Canonicalization & SHA-256 Fingerprinting:**
  - Package: [`backend/app/services/cnmc/canonicalization.py`](file:///home/shikhar/Desktop/mira/backend/app/services/cnmc/canonicalization.py).
  - Technical attribute selection, unit normalization, explicit missing-value (`UNKNOWN`) handling, and SHA-256 machine identity hashing.
- **Registry & Monotonic Global Sequence Allocation:**
  - Package: [`backend/app/services/cnmc/service.py`](file:///home/shikhar/Desktop/mira/backend/app/services/cnmc/service.py).
  - Backed by Postgres `cnmc` table with database sequence `cnmc_global_id_seq` in [`backend/app/db_adapter.py`](file:///home/shikhar/Desktop/mira/backend/app/db_adapter.py) and [`backend/app/store.py`](file:///home/shikhar/Desktop/mira/backend/app/store.py).
  - Single monotonic sequence across all categories with concurrency/race-condition safety and deduplication of matching canonical identities.
- **Workflow & Frontend Integration:**
  - Integrated into [`backend/app/api/v1/mappings.py`](file:///home/shikhar/Desktop/mira/backend/app/api/v1/mappings.py) `POST /api/mappings/generate` and `GET /api/mappings/export/flat`.
  - Frontend views ([`frontend/src/pages/Mappings/Mappings.tsx`](file:///home/shikhar/Desktop/mira/frontend/src/pages/Mappings/Mappings.tsx), [`frontend/src/pages/CommonMaterials/CommonMaterials.tsx`](file:///home/shikhar/Desktop/mira/frontend/src/pages/CommonMaterials/CommonMaterials.tsx), [`frontend/src/pages/ERPIntegration/ERPIntegration.tsx`](file:///home/shikhar/Desktop/mira/frontend/src/pages/ERPIntegration/ERPIntegration.tsx)) clearly display CNMC with explicit headers, search placeholders, and null-safe fallbacks.
- **Testing & Verification:**
  - Added [`backend/tests/test_cnmc.py`](file:///home/shikhar/Desktop/mira/backend/tests/test_cnmc.py) (9 unit/concurrency tests) and [`backend/tests/test_e2e_cnmc_workflow.py`](file:///home/shikhar/Desktop/mira/backend/tests/test_e2e_cnmc_workflow.py) (cross-CPSE end-to-end integration test).
  - All 94 backend tests pass; frontend TypeScript build passes with zero errors.

## Performance & Scalability Benchmark Audit — 2026-09-19

Conducted comprehensive multi-stage performance benchmarks across dataset sizes (10, 100, 1,000, and 5,000 records) measuring precision wall-clock timings, record throughput, candidate counts, and memory allocations via `tracemalloc`:

- **High-Throughput Stages:**
  - Ingestion: ~400,000 records/sec ($< 1\text{ MB}$ RAM).
  - Normalization: ~40,000 records/sec ($< 1\text{ MB}$ RAM).
  - Specification Extraction & Parsing: ~4,800 records/sec ($5.5\text{ MB}$ at 5k records).
  - CMR Synthesis: ~5,000–11,000 records/sec ($< 100\text{ KB}$ RAM).
  - CNMC Deterministic Allocation & DB Storage: ~330 codes/sec ($< 350\text{ KB}$ RAM).
- **Identified Scaling Bottlenecks:**
  - *Candidate Generation:* $O(N^2)$ pairwise loop in `generate_candidates` due to on-the-fly regex key re-computation. Recommended fix: reuse the pre-computed inverted block index.
  - *PyTorch Embeddings:* Per-pair unbatched MiniLM forward passes cap CPU throughput at ~38–40 pairs/sec. Recommended fix: pre-compute embeddings once per material description during ingestion and compute similarity via vector dot products.

## Failure-Mode & Resilience Audit — 2026-09-19

Audited and verified MIRA against bad inputs and operational edge cases across 6 domains:

- **Test Suite:** Added [`backend/tests/test_failure_modes.py`](file:///home/shikhar/Desktop/mira/backend/tests/test_failure_modes.py) containing 27 automated tests covering:
  1. *DATA:* Empty CSV, missing columns, missing/whitespace description, missing CPSE, duplicate material codes, UTF-8 BOM, unknown categories/units, malformed specs.
  2. *MATCHING:* Same-CPSE candidate isolation, zero candidates, missing specifications, conflicting specifications, identical descriptions with conflicting critical attributes.
  3. *REVIEW:* Nonexistent candidate actions (404), repeated approval/rejection conflict handling (409), unauthorized review actions (403).
  4. *CNMC:* Identical canonical identity reuse, differing identity allocation, missing attributes as `UNKNOWN`, multi-threaded concurrent allocation.
  5. *AUTH:* Missing/invalid JWT (401), deactivated user rejection (403), role permission enforcement (403), protected route shielding.
  6. *EXPORT:* Empty mapping exports, null optional field handling, large dataset streaming.
- **Defects Fixed:**
  - Ingestion: Added `.strip()` to CSV raw description handling in [`backend/app/api/v1/materials.py`](file:///home/shikhar/Desktop/mira/backend/app/api/v1/materials.py) so whitespace-only cells are ignored safely.
- **Verification:** All 128 backend tests pass (`PYTHONPATH=. pytest -q`); frontend build passes with 0 errors.

## Final SIH26099 Implementation Audit — 2026-09-19

Performed final repository audit against SIH26099 functional areas:
- 25 of 26 areas are **FULLY IMPLEMENTED** and covered by live code and unit/integration tests.
- 1 area (ERP/SAP Integration Boundary) is **INTEGRATION-READY**, featuring standard REST contracts, flat JSON/CSV export, and clear frontend boundary disclaimers.
- Zero required features are missing.

## Candidate-Generation Scalability & Inverted Block Index — 2026-09-19 / 2026-09-20

Eliminated the $O(N^2)$ candidate generation bottleneck across the matching pipeline:
- **Inverted Block Index:** Target block keys are computed once per material ($O(N)$) using `generate_block_keys()` and indexed in `dict[str, list[int]]` via `build_block_index()` in [`backend/app/services/blocking/service.py`](file:///home/shikhar/Desktop/mira/backend/app/services/blocking/service.py).
- **Candidate Retrieval:** Enhanced `generate_candidates()` to query the inverted block index with `source_keys`, `target_map`, and `target_order`, preserving exact original dataset ordering and full backward compatibility.
- **Batch Pipeline Integration:** Updated [`backend/app/api/v1/matching.py`](file:///home/shikhar/Desktop/mira/backend/app/api/v1/matching.py) and [`backend/benchmark_pipeline.py`](file:///home/shikhar/Desktop/mira/backend/benchmark_pipeline.py) to precompute keys once and reuse the inverted index.
- **Benchmarks & Parity:** Candidate generation runtime at 5,000 materials dropped from 123.1s to 2.55s (48.2x speedup) with 100% bit-exact candidate pair output.
- **Verification:** Added comprehensive tests in [`backend/tests/test_blocking.py`](file:///home/shikhar/Desktop/mira/backend/tests/test_blocking.py); all 132 backend tests passed.

## MiniLM Semantic Embedding Caching & Semantic-Equivalence Audit — 2026-09-20

Optimized Stage 5 (Matching & Scoring) semantic similarity and audited mathematical equivalence:
- **Scoped Embedding Cache:** Implemented `EmbeddingCache` and `precompute_embeddings()` in [`backend/app/services/matching/embeddings.py`](file:///home/shikhar/Desktop/mira/backend/app/services/matching/embeddings.py) to batch-encode unique normalized descriptions once per matching run.
- **Vector Dot Product:** Computed semantic similarity via vector dot products `float(vec_a @ vec_b)` on normalized unit vectors, replacing repetitive pairwise Transformer forward passes.
- **Call-Chain Forwarding:** Updated [`backend/app/services/matching/similarity.py`](file:///home/shikhar/Desktop/mira/backend/app/services/matching/similarity.py), [`backend/app/services/matching/scoring.py`](file:///home/shikhar/Desktop/mira/backend/app/services/matching/scoring.py), [`backend/app/services/matching/classifier.py`](file:///home/shikhar/Desktop/mira/backend/app/services/matching/classifier.py), and [`backend/app/api/v1/matching.py`](file:///home/shikhar/Desktop/mira/backend/app/api/v1/matching.py) to pass `embedding_cache` while defaulting to `None` for un-cached single-pair fallback.
- **Semantic Equivalence Audit:** Verified that `semantic_similarity()` canonical behavior has always clamped values to $[0.0, 1.0]$ via `max(0.0, min(1.0, similarity))`; confirmed identical mathematical range and numerical parity ($\Delta \le 1.19 \times 10^{-7}$) across identical, similar, moderate, unrelated, and negative dot-product vector pairs.
- **Benchmarks:** Scoring throughput increased from ~38 pairs/sec to >2,100 pairs/sec (52–55x speedup) on datasets up to 5,000 records.
- **Verification:** Added [`backend/tests/test_semantic_embedding_cache.py`](file:///home/shikhar/Desktop/mira/backend/tests/test_semantic_embedding_cache.py); all 141 backend tests passed.

## Legacy Material File Ingestion Pipeline — 2026-09-20

Integrated full legacy file format support into MIRA's established ingestion architecture:
- **Supported Formats:** `.csv`, `.txt` (pipe-delimited and header-based), `.xml`, `.json` (arrays and object-wrapped lists), `.xls` (legacy Excel via `xlrd`), `.xlsx` (modern Excel via `openpyxl`).
- **Ingestion & Schema Normalization:**
  - Implemented [`backend/app/services/ingestion/normalizer.py`](file:///home/shikhar/Desktop/mira/backend/app/services/ingestion/normalizer.py) with canonical alias sets for `material_code`, `description`, `unit`, `category`, `manufacturer`, `manufacturer_part_number`, `material_grade`, `cpse`, and `quantity`. Supports case-insensitivity, snake_case, kebab-case, camelCase, and space/underscore/hyphen stripping.
  - Implemented [`backend/app/services/ingestion/detector.py`](file:///home/shikhar/Desktop/mira/backend/app/services/ingestion/detector.py) for clean extension-to-format routing.
  - Implemented format parsers in [`backend/app/services/ingestion/parsers/`](file:///home/shikhar/Desktop/mira/backend/app/services/ingestion/parsers/) (`csv_parser.py`, `txt_parser.py`, `json_parser.py`, `xml_parser.py`, `excel_parser.py`) and central service in [`backend/app/services/ingestion/service.py`](file:///home/shikhar/Desktop/mira/backend/app/services/ingestion/service.py).
- **API Integration:** Updated `POST /api/materials/upload` in [`backend/app/api/v1/materials.py`](file:///home/shikhar/Desktop/mira/backend/app/api/v1/materials.py) to parse all supported formats while preserving existing RBAC, database persistence, normalization, and specification extraction.
- **Frontend File Accept:** Updated [`frontend/src/pages/Materials/Materials.tsx`](file:///home/shikhar/Desktop/mira/frontend/src/pages/Materials/Materials.tsx) file input filter to `.csv,.txt,.xml,.json,.xls,.xlsx`.
- **Cross-Format Equivalence & Testing:** Added [`backend/tests/test_legacy_ingestion.py`](file:///home/shikhar/Desktop/mira/backend/tests/test_legacy_ingestion.py) verifying deterministic output parity across all 5 formats and robust failure mode handling (empty files, malformed rows, invalid schemas, missing optional fields). Full test suite now passes with 157 passed tests.

## Existing-CNMC Matching & Proposal System — 2026-09-20

Implemented existing-CNMC matching and proposal workflow enabling new materials to find, score, and attach to established CNMCs:
- **Architecture & Retrieval:**
  - Inverted CNMC Block Index ([`backend/app/services/matching/cnmc_matcher.py`](file:///home/shikhar/Desktop/mira/backend/app/services/matching/cnmc_matcher.py)) indexing both the canonical Common Material Record (CMR) profile and all approved member materials across block keys.
  - Plausible candidate CNMCs retrieved via $O(1)$ key lookup, bounded to a top-K candidate set.
- **Evidence Aggregation & Critical Gates:**
  - Evaluates new materials against both the virtual canonical profile and individual approved members using existing `classify_match()` scoring and `evaluate_critical_gates()`.
  - Reconciles canonical evidence with strongest member evidence. Critical conflicts (e.g. conflicting pressure rating or material grade) block automatic assignment and force human review (`REVIEW`), preserving safety.
- **Review & Attachment Workflow:**
  - Preserves source CPSE codes and existing CNMC identity hashes without unapproved mutation.
  - Added `POST /api/matching/cnmc/candidates` and `POST /api/matching/cnmc/run-batch` to [`backend/app/api/v1/matching.py`](file:///home/shikhar/Desktop/mira/backend/app/api/v1/matching.py).
  - Added `POST /api/mappings/{mapping_id}/attach` to [`backend/app/api/v1/mappings.py`](file:///home/shikhar/Desktop/mira/backend/app/api/v1/mappings.py) with audit logging (`CNMC_MEMBER_ATTACHED`) and CMR re-synthesis.
- **Verification:** Added [`backend/tests/test_existing_cnmc_matching.py`](file:///home/shikhar/Desktop/mira/backend/tests/test_existing_cnmc_matching.py) (12 tests covering member matching, canonical profile matching, multi-member aggregation, critical conflict shielding, deterministic ranking, RBAC, and performance benchmark). Full test suite now passes with 169 passed tests.

## Best-vs-Second-Best CNMC Candidate Margin Observability — 2026-09-20

Added observability and structured evidence for the best-vs-second-best CNMC candidate margin:
- **Observability Semantics:**
  - `best_score`: Highest valid candidate proposal score (`float(proposals[0]["final_score"])` rounded to 4 decimals), or `None` if zero candidates.
  - `second_best_score`: Second highest candidate proposal score (`float(proposals[1]["final_score"])` rounded to 4 decimals), or `None` if zero or one candidate.
  - `score_margin`: Difference between best and second best (`round(best_score - second_best_score, 4)`), or `None` if fewer than two candidates.
  - Exactly one candidate yields `score_margin = None` (not 0.0 or 1.0).
  - Deterministic tie-breaking orders candidates by `(-final_score, cnmc_code)`.
- **Pure Observability (No Thresholding / Decision Rule):**
  - Margin is returned purely as structured evidence. No margin threshold was introduced, and classifier thresholds (`HIGH_CONFIDENCE`, `REVIEW`, `DIFFERENT`) and critical safety gate behaviors remain 100% unchanged.
- **API & Type Exposure:**
  - `compute_cnmc_candidate_margin` added in [`backend/app/services/matching/cnmc_matcher.py`](file:///home/shikhar/Desktop/mira/backend/app/services/matching/cnmc_matcher.py).
  - `POST /api/matching/cnmc/candidates` in [`backend/app/api/v1/matching.py`](file:///home/shikhar/Desktop/mira/backend/app/api/v1/matching.py) returns `best_score`, `second_best_score`, `score_margin` in the response envelope alongside all existing fields.
  - `POST /api/matching/cnmc/run-batch` populates `best_score`, `second_best_score`, `score_margin` on proposal items and candidate `explanation` metadata.
  - TypeScript interfaces updated in [`frontend/src/lib/api.ts`](file:///home/shikhar/Desktop/mira/frontend/src/lib/api.ts).
- **Verification:** Added 6 focused tests covering multiple candidates, single candidate, zero candidates, deterministic ties, decision preservation, and API compatibility. Full test suite passes with 175 tests; frontend build clean.

## CNMC Candidate Margin Empirical Evaluation — 2026-09-20

Conducted empirical evaluation of best-vs-second-best margins on held-out CNMC clusters and hard negatives:
- **Evaluation Framework:**
  - Implemented [`backend/app/services/evaluation/cnmc_margin_analysis.py`](file:///home/shikhar/Desktop/mira/backend/app/services/evaluation/cnmc_margin_analysis.py).
  - Evaluated on the held-out split of 83 distinct True Match Key (TMK) clusters from `Final_Master_Material_Records.csv` and `Training_Pairs_MIRA_FINAL.csv`.
  - 83 established CNMCs (166 seed members), 712 positive held-out queries, and 841 hard-negative queries (`HN_CORRUPT`, `HN_SIBLING`).
- **Empirical Findings:**
  - Candidate distribution on positive queries: 0 candidates: 1 (0.14%), 1 candidate: 163 (22.89%), $\ge 2$ candidates: 548 (76.97%).
  - Top-1 candidate accuracy: 99.44% overall, 99.58% on queries with $\ge 1$ candidate.
  - Correct top-1 queries have wide mean margin: $0.2829$ (median $0.2755$, P90 $0.4671$).
  - Incorrect top-1 queries (3 queries) had tight mean margin: $0.0118$ (median $0.0093$, max $0.0184$).
  - Margin bucket $[0.00, 0.01)$ had 60.0% accuracy (2/5 incorrect); $[0.01, 0.02)$ had 85.7% accuracy; $\ge 0.02$ had 100.0% accuracy (536/536).
  - Hard negatives: mean margin $0.0932$ (median $0.0355$); 0 false `HIGH_CONFIDENCE` classifications (683 `DIFFERENT`, 140 `REVIEW`, 18 `NO_CANDIDATE`).
- **Artifacts Generated:** `data/evaluation/cnmc_margin_query_results.csv`, `data/evaluation/cnmc_margin_summary.csv`, `data/evaluation/cnmc_margin_report.json`.
- **Verification:** Added [`backend/tests/test_cnmc_margin_analysis.py`](file:///home/shikhar/Desktop/mira/backend/tests/test_cnmc_margin_analysis.py) (7 unit tests); full backend test suite passes with 182 tests. No production decision logic modified.

## Frontend Match Review Filters & Field-Level Difference Explanation — 2026-09-20

Enhanced the Match Review interface with review filters, structured field-level comparison tables, and candidate separation margin observability:
- **Match Review Filters:**
  - Decision filter pills in [`frontend/src/components/Matching/MatchList.tsx`](file:///home/shikhar/Desktop/mira/frontend/src/components/Matching/MatchList.tsx): `All`, `Review`, `High Conf`, `Different` with dynamic count badges.
  - Multi-field text search filter (matching code, description, and CPSE).
  - CPSE dropdown selector for filtering pairs involving specific CPSEs.
  - Conflict warning tags (`⚠️ CONFLICT`) and score meters on candidate items.
- **Field-Level Difference Explanation:**
  - Implemented [`frontend/src/components/Matching/FieldDifferenceTable.tsx`](file:///home/shikhar/Desktop/mira/frontend/src/components/Matching/FieldDifferenceTable.tsx) inside [`MatchComparison.tsx`](file:///home/shikhar/Desktop/mira/frontend/src/components/Matching/MatchComparison.tsx).
  - Explicitly compares: Description text (identical vs similar vs different with % semantic similarity), Category, Material Grade, Dimensions / Size, Pressure Rating, Voltage Class, and any active critical safety gates.
  - Standardized status badges: `SAME` (match), `DIFFERENT`, `CONFLICT` (prominent red badge with alert banner), `MISSING` (missing in source vs missing in target), and `UNKNOWN` (not specified).
- **Candidate Separation Observability Card:**
  - Displays Top Candidate Score, Runner-Up Score, and Separation Margin ($\Delta$) as supplementary evidence without affecting decision rules.
- **Verification:** Frontend build (`npm run build`) passed with zero errors; full backend test suite passes with 182 tests. Zero backend matching changes.

## Production Matching Profile & Text Similarity C-Acceleration — 2026-09-20

Profiled the production matching path (`POST /api/matching/run-batch`) and accelerated `text_similarity` with native C SequenceMatcher:
- **Performance Profiling Findings (Baseline on 206 Materials, 6,469 Candidate Pairs):**
  - Total matching run time: $5.60\text{ s}$
  - Batch embedding precomputation (`EmbeddingCache`, batch=64): $2.67\text{ s}$ (14.59 ms/desc)
  - Candidate pair scoring loop: $1.03\text{ s}$
  - Dominant loop bottleneck: Pure-Python `difflib.SequenceMatcher.ratio()` accounted for $91.7\%$ ($942.5\text{ ms}$) of candidate scoring CPU time.
  - Spec / Grade / Semantic dot product: $< 90\text{ ms}$ total.
- **Root Cause of Historical "~4s / description":**
  - Uncached pairwise calls to `SentenceTransformer.encode([left, right])` require $\sim 18.8\text{ ms}$ per pair. For 200 candidates per material, this was $200 \times 18.8\text{ ms} \approx 3.76\text{ s}$ per description.
  - The upfront batch `EmbeddingCache` resolved this multiplicative model encoding overhead ($2.67\text{ s}$ total for 183 unique descriptions).
- **Text Similarity C-Acceleration:**
  - Replaced pure-Python `difflib.SequenceMatcher` loop inside [`backend/app/services/matching/similarity.py`](file:///home/shikhar/Desktop/mira/backend/app/services/matching/similarity.py) with dynamic-programming C-accelerated `_fast_sequence_matcher.so` with graceful fallback to pure Python `difflib`.
  - Statistical Equivalence on 624 Regression Pairs: $99.84\%$ exact equality, mean difference $0.000006$, max difference $0.0039$, 0 ranking or classification decision changes.
  - Speedup: $15.2\text{x}$ faster on text similarity ($942.5\text{ ms} \rightarrow 61.9\text{ ms}$ for 6,469 pairs; 10,000 call microbenchmark: $1,215\text{ ms} \rightarrow 81.8\text{ ms}$, $14.7\text{x}$ speedup).
  - Total candidate pair scoring dropped from $1,027\text{ ms} \rightarrow 104.5\text{ ms}$ ($9.8\text{x}$ speedup).
  - Total matching runtime for 206 materials dropped from $5.60\text{ s} \rightarrow 3.86\text{ s}$.
- **Verification:** Added [`backend/tests/test_text_similarity.py`](file:///home/shikhar/Desktop/mira/backend/tests/test_text_similarity.py) (6 focused unit/regression tests); full backend test suite passes with 188 tests (100% passing). No scoring weights, thresholds, or matching decisions modified.

## Production Embedding-Cache Audit & Single-Material CNMC Cache Fix — 2026-09-20

Audited embedding cache coverage across all production matching paths and eliminated redundant encoding in the single-material CNMC candidate query:
- **Audit Findings:**
  - `POST /api/matching/run-batch`: 100% request-scoped `EmbeddingCache` coverage (1 batched precompute call, 0 in-loop encode calls, 100% cache hits across 7,717 evaluated pairs).
  - `POST /api/matching/cnmc/run-batch`: 100% batch `EmbeddingCache` coverage across all query materials, canonical profiles, and approved members.
  - `POST /api/matching/cnmc/candidates`: Identified redundant pairwise encoding. `find_cnmc_candidates_for_material()` was called with `embedding_cache=None`, causing `classify_match()` to invoke pairwise `SentenceTransformer.encode([left, right])` sequentially on CPU for every candidate canonical profile and member comparison.
- **Single-Material CNMC Cache Optimization:**
  - In [`backend/app/services/matching/cnmc_matcher.py`](file:///home/shikhar/Desktop/mira/backend/app/services/matching/cnmc_matcher.py), immediately after candidate retrieval via inverted blocking keys (`matching_cnmc_codes`) and before entering the candidate scoring loop:
  - If `embedding_cache is None`, collects the normalized descriptions for the query material, candidate CNMC canonical profiles, and approved member materials.
  - Deduplicates all descriptions and executes a single batched `precompute_embeddings(needed_descriptions)`.
  - Passes the resulting request-scoped `EmbeddingCache` to every downstream `classify_match()` invocation.
- **Parity & Performance Verification:**
  - `model.encode()` calls on single candidate query dropped from 9 separate pairwise calls to 1 single batched call (-88.9%).
  - Total texts encoded dropped from 18 (redundant pairwise re-encodings of query text) to 8 unique texts (-55.6%).
  - In-loop cache misses during scoring dropped from 9 to 0 (100% in-loop cache hit rate).
  - Embedding computation latency dropped from $219.35\text{ ms} \rightarrow 86.98\text{ ms}$ ($2.52\text{x}$ speedup).
  - Total single-query latency dropped from $231.57\text{ ms} \rightarrow 93.55\text{ ms}$ ($2.48\text{x}$ speedup).
  - Exact semantic parity: 100% identical candidate IDs, codes, ranking, scores, engine decisions, and critical gate evaluations.
- **Testing:**
  - Added regression test `test_single_cnmc_candidate_embedding_cache_coverage` in [`backend/tests/test_existing_cnmc_matching.py`](file:///home/shikhar/Desktop/mira/backend/tests/test_existing_cnmc_matching.py).
  - Full backend pytest suite: 189 passed (100% passing).
  - No scoring formulas, classifier thresholds, critical gates, or CNMC canonicalization rules modified.

## Domain Semantic Fine-Tuning & Evaluation on CPSE Pairs — 2026-09-21

Successfully trained and evaluated a domain-adapted sentence-transformer model on CPSE material descriptions and integrated it into the matching pipeline:
- **Dataset Policy & Integrity:**
  - Strictly trained on balanced CPSE training pairs from `Training_Pairs_MIRA_FINAL.csv`.
  - Excluded multi-tenant raw SAP dumps (`mara.csv`, `makt.csv`) to prevent label corruption and noise leakage.
  - Prioritized hard-negative pairs (`HN_CORRUPT`, `HN_SIBLING`) with balanced positive pairs.
- **Training Configuration:**
  - Script: [`backend/app/ml_pipeline/train_minilm_cpse.py`](file:///home/shikhar/Desktop/mira/backend/app/ml_pipeline/train_minilm_cpse.py).
  - Base architecture: `sentence-transformers/all-MiniLM-L6-v2`.
  - Loss: `CosineSimilarityLoss` with AdamW optimizer, warmup, cosine decay, and `model.max_seq_length = 48` (optimized for industrial descriptions).
  - Saved checkpoint: `models/trained/minilm_cpse_v1/`.
- **Comparative Benchmark Results:**
  - Evaluated on DEV (5,228 pairs), blind HELDOUT (5,284 pairs), and 300 Hard Negatives benchmark:

  | Metric | Baseline MiniLM | Fine-Tuned CPSE MiniLM | Improvement |
  |---|---:|---:|---:|
  | **DEV ROC-AUC** | 0.7663 | **0.8627** | +0.0964 |
  | **DEV PR-AUC** | 0.8557 | **0.9177** | +0.0620 |
  | **DEV Score Margin** | 0.3019 | **0.4995** | +0.1976 |
  | **HELDOUT ROC-AUC** | 0.7728 | **0.8775** | +0.1047 |
  | **HELDOUT PR-AUC** | 0.8712 | **0.9304** | +0.0592 |
  | **HELDOUT Score Margin** | 0.3079 | **0.5410** | +0.2331 |
  | **HN 300 Mean Similarity** | 0.9757 | **0.3524** | -0.6233 (false sim eliminated) |
  | **HN 300 FHC Rate (>0.85)** | 100.0% (300/300) | **16.0% (48/300)** | **-84.0% false high-confidence** |

- **Integration:**
  - Updated [`backend/app/services/matching/embeddings.py`](file:///home/shikhar/Desktop/mira/backend/app/services/matching/embeddings.py) to automatically load `models/trained/minilm_cpse_v1` when present on disk or specified via `MIRA_EMBEDDING_MODEL` environment variable, falling back gracefully to `all-MiniLM-L6-v2`.

## Universal Jumbled-File & Multi-Format Provenance Resolution — 2026-09-21

Implemented generic, deterministic provenance resolution across all 6 supported legacy file formats (`CSV`, `TXT`, `XML`, `JSON`, `XLS`, `XLSX`):
- **Deterministic 6-Tier Evidence Hierarchy:**
  - Implemented in [`backend/app/services/ingestion/provenance.py`](file:///home/shikhar/Desktop/mira/backend/app/services/ingestion/provenance.py):
    1. `EXPLICIT_ROW` (confidence 1.0): Direct row fields (`cpse`, `organization`, `source_org`, `company`).
    2. `SHEET_NAME` (confidence 0.95): Worksheet title in multi-sheet Excel workbooks (`.xlsx`, `.xls`).
    3. `FILE_HEADER` (confidence 0.90): Top-level file header text and comments.
    4. `FILENAME_METADATA` (confidence 0.85): CPSE tokens embedded in uploaded file name.
    5. `OBSERVED_CODE_PATTERN` (confidence 0.80): Known material code prefix/regex patterns (e.g., `PO\d+` $\rightarrow$ POLYCAB, `YA\d+` $\rightarrow$ YANTRAIN, `MC\d+` $\rightarrow$ MCL, `SRF-*` $\rightarrow$ SRF).
    6. `UNKNOWN` (confidence 0.0): Safe fallback to `CPSE_GENERIC` with `requires_review = True` and zero hallucinated guessing.
- **Multi-Sheet Extraction & Ingestion Pipeline:**
  - Updated [`backend/app/services/ingestion/parsers/excel_parser.py`](file:///home/shikhar/Desktop/mira/backend/app/services/ingestion/parsers/excel_parser.py) to extract all sheets from multi-worksheet workbooks and preserve `_sheet_name` across all rows.
  - In [`backend/app/api/v1/materials.py`](file:///home/shikhar/Desktop/mira/backend/app/api/v1/materials.py), integrated `resolve_provenance()` to record `provenance_level`, `provenance_confidence`, `provenance_source`, `provenance_conflict`, `requires_review`, and `provenance_details` for full traceability.
  - Cross-source conflict detection automatically flags discrepancies between explicit row data and file/sheet metadata for human review.
- **Verification:**
  - Added [`backend/tests/test_provenance.py`](file:///home/shikhar/Desktop/mira/backend/tests/test_provenance.py) (7 focused tests covering hierarchy levels, multi-sheet resolution, code prefix extraction, conflict detection, and upload integration).
  - Full backend test suite: **201 passed tests (100% passing)**; frontend TypeScript build passed with 0 errors.

## Qwen Learned Weights & Production Scoring Weight Freeze — 2026-09-25

Following systematic Track 1 evaluation across unregularized optimization, regularized constrained grid search (981 candidate vectors), independent stress tests (712 pairs), and controlled 3-arm A/B/C testing against fine-tuned Qwen INT8 embeddings (1024D), the production hybrid scoring weights have been frozen:

### Frozen Production Weights (Arm C / `CAND_0678`):
$$\mathbf{w}_{\text{Production}} = [0.175, 0.400, 0.250, 0.125, 0.050]$$

* `TEXT_WEIGHT = 0.175` (previously `0.200`)
* `SEMANTIC_WEIGHT = 0.400` (previously `0.200`)
* `SPECIFICATION_WEIGHT = 0.250` (previously `0.350`)
* `GRADE_WEIGHT = 0.125` (previously `0.150`)
* `OTHER_ATTRIBUTES_WEIGHT = 0.050` (previously `0.100`)

### Experimental Evidence & Operational Justification:
1. **DEV & HELDOUT Discrimination:**
   * DEV ROC-AUC increased from `0.7456` to **`0.7691`** (+0.0235); Score Separation increased from `+0.2069` to **`+0.2722`** (+0.0653).
   * HELDOUT ROC-AUC increased from `0.7651` to **`0.7891`** (+0.0240); Score Separation increased from `+0.2021` to **`+0.2769`** (+0.0748).
2. **False Positive & Rejection Recovery:**
   * Rescues **~900 legitimate positive pairs** previously misclassified as `DIFFERENT` (DEV Pos DIFFERENT dropped from `359` down to `7`; HELDOUT Pos DIFFERENT dropped from `547` down to `18`).
3. **Hard-Negative Safety & Operator Burden Reduction:**
   * Hard negatives mean score dropped from `0.4201` down to **`0.3760`** (max `0.6127`).
   * **Zero hard negatives reach $\ge 0.80$ and zero receive `HIGH_CONFIDENCE`**.
   * Auto-rejects **250 / 300 hard negatives as `DIFFERENT`** (83.33%), reducing the human review load from 68 pairs down to 50 pairs (**26.5% reduction in operator review workload**).
4. **Preservation of Engineering Invariants:**
   * Critical specification gates and decision thresholds (`HIGH_CONFIDENCE = 0.85`, `DIFFERENT = 0.45`) remain 100% intact.
   * Specification weight is firmly locked at $0.250 \ge 0.25$ and material grade at $0.125 \ge 0.10$.

## Automated Decision Routing & Review Queue Governance — 2026-09-29

Refactored MIRA's match candidate evaluation and review queue governance to automate obvious equivalent matches and hard technical conflicts while focusing human operator attention strictly on genuine technical ambiguities:

- **Core Decision Routing Policy:**
  $$\begin{aligned}
  \text{Hard Technical Conflict} &\longrightarrow \texttt{DIFFERENT} \quad (\texttt{review\_status = DIFFERENT}) \\
  \text{Unknown / Ambiguous Critical Spec} &\longrightarrow \texttt{REVIEW} \quad (\texttt{review\_status = PENDING}) \\
  \text{All Critical Gates Pass} \land \text{Final Score} \ge 0.85 &\longrightarrow \texttt{HIGH\_CONFIDENCE} \quad (\texttt{review\_status = AUTO\_APPROVED})
  \end{aligned}$$
- **Mapping Generation & Review Queue Decoupling:**
  - `POST /api/mappings/generate` consumes both `APPROVED` (human approved) and `AUTO_APPROVED` (system auto-approved) candidates.
  - `GET /api/review/queue` strictly filters for `review_status == "PENDING"`, removing auto-approved items and hard rejections from the queue.
  - Audit logs emit distinct `MATCH_AUTO_APPROVED` events with actor `system:engine` to maintain governance separation from human `MATCH_APPROVED` events.
- **Frontend Badges & UI Integration:**
  - Added visual badges and styles in `Badge.tsx` and `index.css` for `AUTO_APPROVED` (emerald gradient with sparkle icon) and `DIFFERENT` (subtle slate tag).

## Qwen INT8 1024D Semantic Embedding Migration & Cross-Platform Support — 2026-09-29

Migrated MIRA's production semantic embedding pipeline from the legacy 384D MiniLM model (`minilm_cpse_v1`) to the locally available **Qwen INT8 embedding model** (`Mira.ai`):

- **Model Properties & Verification:**
  - Architecture: `Qwen3Model` (28 layers), quantized to INT8 via `bitsandbytes`.
  - Vector Dimension: **1024** (normalized unit vectors, $\|\mathbf{v}\|_2 = 1.0$).
  - Device: CPU execution verified via `SentenceTransformer`.
  - Benchmark Similarity:
    - Equivalent fasteners (`HEX HEAD BOLT M8 X 25 MM SS304` vs `BOLT HEX SS304 M8 X 25`): **0.8366**
    - Unrelated materials (`HEX HEAD BOLT M8 X 25 MM SS304` vs `ROLLER BEARING 50 MM`): **0.1774**
- **Cross-Platform Portable Discovery & Resolution:**
  - In [`backend/app/services/matching/embeddings.py`](file:///home/shikhar/Desktop/mira/backend/app/services/matching/embeddings.py), eliminated hardcoded machine paths in favor of cross-platform path resolution using `Path.home()`, `_get_project_root()`, and standard environment variables:
    1. `MIRA_EMBEDDING_MODEL` / `MIRA_QWEN_MODEL_PATH` / `MIRA_MODEL_PATH` / `MIRA_MODELS_DIR`
    2. `Path.home() / "mira-model-test" / "Mira.ai"`
    3. `Path.home() / "Desktop" / "mira-model-test" / "Mira.ai"`
    4. `Path.home() / ".mira" / "models" / "Mira.ai"`
    5. `<project_root>/models/Mira.ai`
    6. `<project_root>/models/trained/qwen`
- **Dynamic Dimension & Milvus Vector Index Schema:**
  - Added `get_embedding_dimension()` to dynamically query vector width directly from the active SentenceTransformer model.
  - Updated [`backend/create_milvus_collection.py`](file:///home/shikhar/Desktop/mira/backend/create_milvus_collection.py) with `dim=1024` and added `--recreate` CLI support to safely rebuild collections without mixing legacy 384D vectors.
- **Batch Precomputation & Performance Optimization:**
  - Implemented batch embedding precomputation and scoped `EmbeddingCache` in [`backend/app/api/v1/matching.py`](file:///home/shikhar/Desktop/mira/backend/app/api/v1/matching.py) and [`backend/app/services/matching/vector_search.py`](file:///home/shikhar/Desktop/mira/backend/app/services/matching/vector_search.py).
  - Encodes distinct descriptions once per batch, preventing repetitive CPU forward passes across $N \times M$ pairs.
- **End-to-End Validation on Synthetic Material Master (172 items):**
  - Dataset: [`data/sample/synthetic_material_master.csv`](file:///home/shikhar/Desktop/mira/data/sample/synthetic_material_master.csv)
  - Materials ingested: **172**
  - Candidate pairs evaluated: **2,574**
  - Candidate pairs stored: **2,574**
  - `AUTO_APPROVED`: **12**
  - `PENDING` (Review Queue): **676**
  - `DIFFERENT`: **1,886**
  - Mappings generated: **8**
  - Automated audit events: **12**
- **Test Suite Verification:**
  - Dedicated migration test suite [`backend/tests/test_qwen_embedding_migration.py`](file:///home/shikhar/Desktop/mira/backend/tests/test_qwen_embedding_migration.py): **7/7 passed**.
  - Synthetic master manifest test suite [`backend/tests/test_synthetic_material_master_manifest.py`](file:///home/shikhar/Desktop/mira/backend/tests/test_synthetic_material_master_manifest.py): **7/7 passed**.
  - Full backend regression test suite: **270/270 passed** (100% pass rate).
  - Frontend production build: **0 errors** (`dist/` built cleanly).

## Selective MilvusSearch Integration & Production Resolver Hardening — 2026-09-30

Following comparative analysis between `main` and `origin/MilvusSearch`, selectively integrated high-value components while rejecting regressive changes and hardening the production embedding pipeline to be strictly Qwen-only (1024D INT8):

### 1. Selective Integration from `origin/MilvusSearch`
- **Batch Embedding Utility (`backend/app/services/matching/batch_embeddings.py`):**
  - Added `generate_embeddings(texts, batch_size=64, model_name=None)`.
  - Reuses the authoritative SentenceTransformer model loader (`get_embedding_model()`).
  - Implements in-memory deduplication of unique string descriptions to avoid redundant tensor forward passes during candidate batch generation.
  - Normalizes output embeddings ($\|\mathbf{v}\|_2 = 1.0$) and outputs 1024-dimensional vectors.
- **Milvus Batch Insertion Optimization (`backend/app/services/matching/milvus_client.py`):**
  - Refactored `insert_material_embeddings(records)` to batch-encode descriptions via `generate_embeddings()` (`EMBEDDING_BATCH_SIZE = 64`) before calling `collection.upsert()`.
  - Preserves graceful fallback (`_mark_down()`) when Milvus is offline/unreachable and ensures 1024D schema compatibility.

### 2. Explicitly Rejected Remote Invariants
- **Rejected Manual-Only Review Routing (`8655722`):** Retained automated high-confidence auto-approval (`AUTO_APPROVED`) and hard conflict rejection (`DIFFERENT`), ensuring human operators only review genuine ambiguities (`PENDING`).
- **Rejected Reverted Scoring Weights:** Retained calibrated production scoring weights (`[0.175, 0.400, 0.250, 0.125, 0.050]`).
- **Rejected `hybrid_retrieval.py`:** Deliberately rejected adding redundant retrieval logic that introduced a competing 384D baseline model (`all-MiniLM-L6-v2`) in RAM.

### 3. Qwen-Only Production Resolver & Zero Silent Fallbacks (`backend/app/services/matching/embeddings.py`)
- **Strict Qwen Resolution:**
  - `DEFAULT_MODEL_NAME = "Mira.ai"`.
  - `resolve_model_name()` defaults strictly to the local Qwen INT8 model across discovery paths (`MIRA_QWEN_MODEL_PATH`, `MIRA_MODEL_PATH`, `MIRA_MODELS_DIR`, `~/mira-model-test/Mira.ai`, `~/Desktop/mira-model-test/Mira.ai`, etc.).
- **Actionable Error on Missing Model:**
  - Replaced legacy silent fallback to MiniLM with an explicit `FileNotFoundError` detailing all searched candidate directories and configuration options.
  - Production embedding generation and candidate matching can never silently degrade to 384D.
- **Legacy Compatibility Isolation:**
  - Explicit non-default aliases (`"minilm"`, `"base-minilm"`) remain isolated for historical offline training and stability scripts (`learned_weights_stability.py`, `train_minilm_cpse.py`) without affecting production runtime defaults.

### 4. Verification & Terminal E2E Pipeline Results
- **Unit & Regression Testing:**
  - `backend/tests/test_qwen_embedding_migration.py`: **9/9 passed** (including missing model `FileNotFoundError` assertion and batch embeddings utility tests).
  - `backend/tests/test_semantic_embedding_cache.py`: **13/13 passed** (including cross-model cache isolation and normalization tests).
  - Full backend test suite: **273/273 passed** (100% pass rate).
  - Frontend build: **Built cleanly in 724ms with 0 errors**.
  - `git diff --check`: Clean (0 errors / 0 trailing whitespace).
- **Synthetic Material Master E2E Validation (172 items):**
  - **Resolved Model Path:** `/home/shikhar/mira-model-test/Mira.ai`
  - **Vector Dimension:** `1024`
  - **Materials Ingested:** `172`
  - **Candidate Pairs Evaluated:** `2,574`
  - **`AUTO_APPROVED`:** `11`
  - **`PENDING` (Human Review Queue):** `676`
  - **`DIFFERENT`:** `1,887`
  - **Mappings Generated:** `7`
  - **Equivalent Similarity:** `0.8261` (`HEX HEAD BOLT M8 X 25 MM SS304` vs `BOLT HEX SS304 M8 X 25`)
  - **Unrelated Similarity:** `0.1844` (`HEX HEAD BOLT M8 X 25 MM SS304` vs `ROLLER BEARING 50 MM`)
  - **Governance Invariants:** Intact (`Governance Check: PASS`).