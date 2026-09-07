# MIRA --- Project Memory

> Persistent project state. **Mandatory:** update this file automatically whenever meaningful project state changes, in the same development workflow/commit.

## Project

**SIH26099 --- AI-Driven Standardization and Harmonization of Material Codes Across CPSEs**

**Deadline:** 18 days hard freeze.

## Team Roles

- Person 1 --- Data & Evaluation
- Person 2 --- Matching Engine
- Person 3 --- Backend & Database
- Person 4 --- Frontend & Review + frontend-facing API integration
- Person 5 --- Integration, Clustering & Demo
- Person 6 --- Coordination, documentation, testing and presentation

## Frozen Architecture

CPSE Material Master → Ingestion → Normalization/Units →
Parser/Attribute Extraction → Category/Blocking → Candidate Generation →
Hybrid Scoring → Critical Gates → HIGH_CONFIDENCE/REVIEW/DIFFERENT →
Human Review → Approved Relationships → Clustering/Conflict Detection →
Common Material Record → Common National Material Code → CPSE Code
Mapping → Audit/Export/API.

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
- Critical canonical specifications are never invented, averaged or majority-voted.
- LLM extraction is optional stretch, not a core dependency.
- UNSPSC is optional supporting classification/blocking/analytics, not a dependency.
- Common National Material Code is an explicit SIH capability; exact syntax is our design decision.
- Common Material approval requires safe canonical fields; critical UNKNOWN blocks APPROVED.
- SAP/ERP integration is represented by integration-ready REST/CSV interfaces; no live SAP claim without an actual integration.
- Matching logic is treated as frozen pending proper DEV/HELD-OUT evaluation; do not tune thresholds based only on demo examples.

## SIH Requirement Coverage

The implementation explicitly covers AI description/specification matching; duplicate, near-duplicate and equivalent identification; standardization; classification; Common National Material Code; CPSE mapping; legacy rationalization/migration support; human validation/approval; dashboard/analytics; audit/governance; SAP/ERP integration capability; and One Nation -- One Material Code traceability.

## Evaluation

Dataset A = DEV + blind HELD-OUT + blind HARD-NEGATIVES.

Dataset B is separate. B1 requires positive evidence via matching part number, standard designation, or complete structured specifications without critical conflict. If fewer than 50 qualifying agreed B1 pairs exist by end of Day 4, switch to B2.

Report precision, recall, F1, automation rate, aggregate false-positive rate and hard-negative false-HIGH_CONFIDENCE rate.

**Day 17:** genuine blind held-out result.

**Day 18:** post-correction result; never present it as an independent blind test.

## Backend Status

The core FastAPI matching backend is now implemented.

### Backend foundation

- FastAPI application initialized.
- Application configuration implemented using `pydantic-settings`.
- SQLAlchemy database configuration added for PostgreSQL.
- `/health` endpoint implemented.
- API router structure established.
- Backend package `__init__.py` files added.
- Backend dependencies recorded in `backend/requirements.txt`.

### Matching pipeline implemented

- Material description normalization implemented.
- Rule-based technical specification parsing implemented.
- Local semantic similarity implemented using `all-MiniLM-L6-v2`.
- Sentence-transformer embeddings run locally on CPU; no cloud embedding API is required by the core matcher.
- Candidate blocking implemented.
- Weighted hybrid matching score implemented.
- Category-aware specification similarity implemented.
- Critical specification gates implemented.
- Match classifier implemented with:
  - `HIGH_CONFIDENCE`
  - `REVIEW`
  - `DIFFERENT`
- Critical `UNKNOWN` and `CONFLICT` states prevent `HIGH_CONFIDENCE`.
- Matching API implemented at:
  `POST /api/matching/compare`

### Category-aware critical fields

- FASTENER:
  - material_grade
  - dimensions
- VALVE:
  - pressure_rating
  - dimensions
- PIPE:
  - pressure_rating
  - dimensions
- ELECTRICAL CONNECTOR:
  - voltage_class
  - dimensions

### Parser coverage

Current rule-based parser recognizes:

- Stainless-steel grades such as `SS304`, `SS316`, `SS321`.
- Equivalent `STAINLESS STEEL 304` style descriptions.
- AISI/IS grade patterns currently supported.
- Pressure notation such as `LB`, `LBS`, `POUND`, `POUNDS`, `PSI`, `BAR` and `#`.
- Dimensions using `IN` and `MM`.
- Voltage using `V` and `KV`.

### Backend tests

**28 tests passing.**

Validated behaviors:

1. Equivalent material descriptions:
   - `SS304 GATE VALVE 2 IN 150 LB`
   - `STAINLESS STEEL 304 GATE VALVE 2 IN 150 POUND`
   - Result: `HIGH_CONFIDENCE`
   - Final score observed: `0.9148`
   - Critical gates: PASS

2. Conflicting critical specification:
   - Same valve characteristics but `150 LB` vs `300 LB`
   - Result: `REVIEW`
   - Pressure gate: `CONFLICT`

3. Missing critical specification:
   - Target valve missing pressure rating
   - Result: `REVIEW`
   - Pressure gate: `UNKNOWN`

These tests confirm that high text/semantic similarity cannot override conflicting or missing critical technical specifications.

## Frontend Status

The React/Vite/TypeScript frontend skeleton and primary application screens are implemented.

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

Current frontend details:

- Materials supports selecting a material and displaying its details in a right-side panel.
- Match Review is implemented as the primary human-review workflow.
- Analytics includes bar charts, doughnut/pie charts and trend charts.
- Audit Trail includes searchable/filterable governance activity records.
- Settings includes governance/application preferences and system information.
- Frontend currently uses mock/demo data where backend endpoints are not connected.
- Frontend build succeeds; the Vite/Rolldown bundle-size message is a non-blocking warning.

## Current Next Action

Major frontend screen implementation is complete.

The next implementation phase is the **frontend-facing API integration pass**.

First vertical slice:

`Materials → GET /api/materials → PostgreSQL → real frontend records`

Then:

`Match Review → match API/review endpoints → approve/reject decision`

Then connect:

- Common Materials
- Mappings
- ERP Integration
- Analytics
- Audit Trail

to their respective backend API contracts.

The frontend should remain independent of the backend implementation language and communicate through agreed REST APIs.

Before building the full persistence layer, the team should also inspect the tender/BOQ datasets being collected by teammates and define the material-level ingestion schema around the actual data available.

For tender/BOQ-derived data:

- Keep material/item descriptions and technical specifications.
- Strip rate/price information from the harmonization dataset.
- Preserve CPSE/source provenance where appropriate.
- Do not assume public accessibility implies redistribution rights.
- Raw tender documents do not automatically constitute the final Dataset B.
- Dataset B must follow the separate evaluation and evidence rules defined above.

## Change Log --- 2026-09-06

- Reconciled documentation against the full SIH26099 problem statement.
- Confirmed Common National Material Code as an explicit required capability.
- Added explicit coverage for standardization, classification, legacy rationalization/migration, governance/audit, analytics and ERP integration capability.
- Corrected execution planning to an 18-day hard deadline.
- Assigned Person 4 explicit frontend-facing API/integration responsibility without moving core backend ownership from Person 3.
- Completed Dashboard, Materials, Match Review, Common Materials, Mappings, ERP Integration, Analytics, Audit Trail and Settings frontend screens.
- Added working right-side material details panel.
- Added Analytics visualizations using bar, doughnut/pie and trend charts.
- Added governance-focused Audit Trail interface with search and filters.
- Added Settings interface with application and governance controls.
- Confirmed frontend build succeeds with only a non-blocking bundle-size warning.
- Frontend development moved from screen construction toward API contracts and backend integration.

## Change Log --- 2026-09-07

- Implemented FastAPI backend foundation and API router structure.
- Added PostgreSQL/SQLAlchemy configuration.
- Added material and match Pydantic schemas.
- Implemented material normalization.
- Implemented rule-based technical specification parsing.
- Added local `all-MiniLM-L6-v2` semantic similarity.
- Implemented candidate blocking.
- Implemented frozen weighted hybrid scoring formula.
- Implemented category-aware specification comparison.
- Implemented critical specification gates and match classification.
- Added regression tests for normalization, parsing, blocking, scoring, gates and classification.
- Backend test suite reached **28 passing tests**.
- Verified equivalent valve descriptions produce `HIGH_CONFIDENCE`.
- Verified conflicting pressure ratings produce `REVIEW`.
- Verified missing critical pressure ratings produce `REVIEW`.
- Implemented `POST /api/matching/compare` and verified it through Swagger.
- Matching core is now considered stable pending proper DEV/HELD-OUT evaluation.
- Team is collecting tender/BOQ data from CPSE/company sources; actual sample formats need to be inspected before finalizing ingestion/persistence assumptions.
- Next backend milestone is persistent Material storage and `GET /api/materials`.
- Next frontend milestone is connecting the Materials screen to real backend records.
