# SIH26099 --- 18-Day Execution Plan

## Workstreams

-   **Person 1 --- Data & Evaluation:** Dataset A/B, ground truth,
    evaluation, metrics, error analysis, B1/B2 decision.
-   **Person 2 --- Matching Engine:** normalization, parser/rules,
    exact/fuzzy matching, blocking, embeddings, specification
    comparison, scoring, critical gates.
-   **Person 3 --- Backend & Database:** FastAPI, PostgreSQL/pgvector,
    models, APIs, ingestion, persistence, review actions, Common
    Material persistence and mappings.
-   **Person 4 --- Frontend & Review:** React UI, upload, results,
    review, score/gate visualization, approve/reject, mapping,
    analytics, audit display, frontend-facing API integration.
-   **Person 5 --- Integration/Clustering/Demo:** Common Material
    schema, clustering, conflict detection, mapping, end-to-end
    integration, scale/demo.
-   **Person 6 --- Coordination:** integration, documentation, testing,
    presentation and cross-workstream blockers.

## 18-Day Schedule

### Days 1--6 --- Foundation + Matching Floor

**Day 1:** requirements/schemas, repo, frontend/backend/database
skeleton, Dataset A generator, public-source investigation, API
contracts.\
**Day 2:** normalization, DB tables, parser/rules, synthetic data,
Dataset B collection, frontend skeleton/navigation.\
**Day 3:** exact/fuzzy matching, blocking, evaluation harness, API
skeleton, upload/material UI.\
**Day 4 --- B1/B2 Go/No-Go:** assess B1 evidence; Person 2 decides.
Fewer than 50 qualifying agreed B1 pairs → B2. Freeze Dataset B
strategy.\
**Day 5:** development matcher, persistence, results UI, hard negatives,
critical gates.\
**Day 6 --- Floor Freeze:** CSV → normalize → candidates → matching →
gates → REVIEW/decision; basic metrics and review UI working.

### Days 7--12 --- Target Intelligence + Common Mapping

**Day 7:** local sentence-transformer embeddings + pgvector.\
**Day 8:** semantic, specification and material/grade similarity.\
**Day 9:** frozen hybrid scoring, critical gates, API integration.\
**Day 10 --- Evaluation Checkpoint:** DEV evaluation, hard-negative
checks, freeze scoring configuration.\
**Day 11:** clustering, connected components, conflict detection.\
**Day 12 --- Target Integration:** Common Material Record, Common
National Material Code design, CPSE mapping, audit trail, end-to-end
Target pipeline.

### Days 13--18 --- Validation + Demo Freeze

**Day 13:** frontend refinement, review workflow, mapping view,
analytics, export/API.\
**Day 14:** Dataset B and hard-negative finalization,
source/redistribution checks, demo scenarios.\
**Day 15 --- Pre-Blind Freeze:** freeze matcher/evaluation configuration
and verify Dataset B isolation.\
**Day 16 --- Dataset B Evaluation:** unlock B, run sanity checks,
document B1/B2 result, error analysis.\
**Day 17 --- Genuine Blind Evaluation:** held-out + hard-negative
evaluation; preserve genuine blind metrics.\
**Day 18 --- Final Freeze:** apply Day 17 findings, rerun
post-correction metrics, keep Day 17 blind numbers separate, final
demo/docs/presentation, Floor fallback, repository freeze.

## Definition of Done

CSV ingestion, normalization, extraction, candidate generation,
matching, gates, REVIEW, clustering, Common Material Record, Common
National Material Code recommendation, CPSE mapping, audit trail,
evaluation, honest Dataset B labeling, preserved blind results,
end-to-end demo and Floor fallback all work.

## Emergency Rule

Cut advanced analytics, extra categories, optional LLM extraction,
advanced visualization and deeper SAP integration before cutting
source-code preservation, gates, REVIEW, evaluation, mapping,
explainability or Common Material functionality.
