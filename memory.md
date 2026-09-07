# MIRA --- Project Memory

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
The implementation covers AI matching, duplicate/near-duplicate/equivalent identification, standardization, intelligent classification, Common National Material Code generation/recommendation, CPSE mapping, legacy rationalization/migration, human validation, dashboard analytics, audit/governance, SAP/ERP integration capability and One Nation -- One Material Code traceability.

## Evaluation
Dataset A = DEV + blind HELD-OUT + blind HARD-NEGATIVES.

Dataset B is separate. B1 requires positive evidence via matching part number, standard designation, or complete structured specifications without critical conflict. If fewer than 50 qualifying agreed B1 pairs exist by end of Day 4, switch to B2.

Report precision, recall, F1, automation rate, aggregate false-positive rate and hard-negative false-HIGH_CONFIDENCE rate.

**Day 17:** genuine blind held-out result.  
**Day 18:** post-correction result; never present it as an independent blind test.

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

## Backend Status
Implemented:
- FastAPI foundation
- PostgreSQL/SQLAlchemy configuration
- material and match schemas
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

**28 tests passing.**

Verified:
- equivalent valve descriptions → HIGH_CONFIDENCE, observed final score 0.9148
- conflicting pressure rating → REVIEW
- missing critical pressure rating → REVIEW

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

Frontend currently uses mock/demo data where backend endpoints are not connected. Build succeeds with only a non-blocking bundle-size warning.

## Current Next Action
First vertical slice:

`Materials → GET /api/materials → PostgreSQL → real frontend records`

Then connect Match Review, Common Materials, Mappings, ERP Integration, Analytics and Audit Trail.

In parallel, inspect teammate tender/BOQ samples and finalize ingestion around the real data.

After persistence/ingestion:
- dataset-level candidate generation
- common-material creation and NMC
- CPSE-to-NMC mapping/migration
- clustering/conflict detection
- audit/analytics backend
- optional LLM-assisted extraction/classification where justified
- DEV tuning followed by blind evaluation
