# MIRA --- Project Memory

> Persistent project state. **Mandatory:** update this file
> automatically whenever meaningful project state changes, in the same
> development workflow/commit.

## Project

**SIH26099 --- AI-Driven Standardization and Harmonization of Material
Codes Across CPSEs**

**Deadline:** 18 days hard freeze.

## Team Roles

-   Person 1 --- Data & Evaluation
-   Person 2 --- Matching Engine
-   Person 3 --- Backend & Database
-   Person 4 --- Frontend & Review + frontend-facing API integration
-   Person 5 --- Integration, Clustering & Demo
-   Person 6 --- Coordination, documentation, testing and presentation

## Frozen Architecture

CPSE Material Master → Ingestion → Normalization/Units →
Parser/Attribute Extraction → Category/Blocking → Candidate Generation →
Hybrid Scoring → Critical Gates → HIGH_CONFIDENCE/REVIEW/DIFFERENT →
Human Review → Approved Relationships → Clustering/Conflict Detection →
Common Material Record → Common National Material Code → CPSE Code
Mapping → Audit/Export/API.

## Frozen Decisions

-   Preserve every original CPSE material code.
-   Never overwrite source records with a common code.
-   `final_score = 0.20 text + 0.20 semantic + 0.35 specification + 0.15 material/grade + 0.10 other attributes`.
-   Only numeric weights may be tuned on DEV; formula shape is frozen.
-   Score is calculated before gates.
-   Missing applicable critical fields = UNKNOWN → REVIEW.
-   Conflicting critical fields → REVIEW.
-   No fixed 0.92 auto-accept rule.
-   Text/semantic similarity alone cannot safely approve a material.
-   Critical canonical specifications are never invented, averaged or
    majority-voted.
-   LLM extraction is optional stretch, not a core dependency.
-   UNSPSC is optional supporting classification/blocking/analytics, not
    a dependency.
-   Common National Material Code is an explicit SIH capability; exact
    syntax is our design decision.
-   Common Material approval requires safe canonical fields; critical
    UNKNOWN blocks APPROVED.
-   SAP/ERP integration is represented by integration-ready REST/CSV
    interfaces; no live SAP claim without an actual integration.

## SIH Requirement Coverage

The implementation explicitly covers AI description/specification
matching; duplicate, near-duplicate and equivalent identification;
standardization; classification; Common National Material Code; CPSE
mapping; legacy rationalization/migration support; human
validation/approval; dashboard/analytics; audit/governance; SAP/ERP
integration capability; and One Nation -- One Material Code
traceability.

## Evaluation

Dataset A = DEV + blind HELD-OUT + blind HARD-NEGATIVES.

Dataset B is separate. B1 requires positive evidence via matching part
number, standard designation, or complete structured specifications
without critical conflict. If fewer than 50 qualifying agreed B1 pairs
exist by end of Day 4, switch to B2.

Report precision, recall, F1, automation rate, aggregate false-positive
rate and hard-negative false-HIGH_CONFIDENCE rate.

**Day 17:** genuine blind held-out result.\
**Day 18:** post-correction result; never present it as an independent
blind test.

## Current Next Action

Start implementation in `/home/shikhar/Desktop/mira`.

Person 4 should begin the frontend skeleton, API contracts and
frontend-facing integration immediately, using mock responses until real
backend endpoints are ready.

## Change Log --- 2026-09-06

-   Reconciled documentation against the full SIH26099 problem
    statement.
-   Confirmed Common National Material Code as an explicit required
    capability.
-   Added explicit coverage for standardization, classification, legacy
    rationalization/migration, governance/audit, analytics and ERP
    integration capability.
-   Corrected execution planning to an 18-day hard deadline.
-   Assigned Person 4 explicit frontend-facing API/integration
    responsibility without moving core backend ownership from Person 3.
