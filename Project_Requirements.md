# SIH26099 — Project Requirements

## 1. Project

**AI-Driven Standardization and Harmonization of Material Codes Across CPSEs**

The system standardizes and harmonizes material records from different CPSEs while preserving each organization's original material code and source information.

### Direct PS Alignment

The SIH26099 problem statement explicitly expects:
- AI-based matching of material descriptions and specifications;
- identification of duplicate, near-duplicate and functionally equivalent materials;
- automated standardization of descriptions and technical attributes;
- classification/categorization;
- recommendation/generation of a Common National Material Code;
- mapping of existing CPSE material codes to the common national code;
- legacy-code rationalization/migration support;
- user validation and approval;
- dashboard/analytics;
- audit trail/governance;
- SAP/ERP integration capability.

The **concept of a Common National Material Code is therefore a PS requirement**. Its exact identifier format is a project design decision and is not prescribed by the PS.

The MVP must:
- ingest material records from different organizations;
- normalize inconsistent descriptions and attributes;
- extract technical attributes;
- generate likely candidate equivalents/duplicates;
- compare candidates using hybrid evidence;
- prevent unsafe matches through critical-attribute gates;
- route uncertain cases to human review;
- group approved equivalent records into common-material records;
- preserve CPSE-specific source-code mappings;
- provide measurable evaluation results.

## 2. Primary Users

- Material/master-data teams
- Procurement teams
- Inventory/material-management teams
- Engineers/technical reviewers
- Data-governance teams
- Cross-CPSE standardization teams
- ERP/SAP administrators

## 3. Core Input

CSV records containing, where available:
- source organization / CPSE;
- source material code;
- material description;
- category;
- material;
- dimensions;
- grade;
- rating / pressure / voltage;
- unit;
- other attributes.

Missing fields are allowed.

The ingestion layer must not assume that all CPSEs use the same schema.

## 4. Core Processing

### Normalization

Normalize:
- casing;
- whitespace;
- punctuation;
- common abbreviations;
- unit representations;
- formatting variations;
- equivalent textual representations.

Normalization must not destroy the original record.

### Attribute Extraction

For the MVP, extraction is **parser/rule based**, using:
- regex;
- technical dictionaries;
- abbreviation mappings;
- unit normalization/conversion;
- category-specific parsing rules.

Example:

```text
SS304 GATE VALVE 2" 150# FLG
        ↓
material = SS304
type = gate valve
size = 2 in
pressure_rating = 150
connection = flanged
```

LLM-based extraction is optional enhancement only. The core MVP must work without an LLM.

### Blocking / Candidate Generation

Use category and available identifying attributes to reduce unnecessary pairwise comparisons before expensive matching.

Blocking is a candidate-generation optimization, not an equivalence decision.

### Matching

Use:
- lexical/text similarity;
- local semantic similarity;
- structured specification comparison;
- material/grade comparison;
- other attribute comparison.

Frozen MVP formula:

```text
final_score =
    0.20 × text_similarity
  + 0.20 × semantic_similarity
  + 0.35 × specification_similarity
  + 0.15 × material_grade_similarity
  + 0.10 × other_attributes_similarity
```

The formula shape is frozen. Only numeric weights may be tuned on the development set.

**Similarity score alone must never establish material equivalence.**

### Critical Gates

Minimum MVP mapping:

| Category | Critical fields |
|---|---|
| Fasteners (bolts, nuts) | grade, dimensions |
| Valves/pipes | pressure rating, dimensions |
| Electrical connectors | voltage class, dimensions |

Rules:
- applicable + matching → continue;
- applicable + conflicting → REVIEW;
- applicable + missing → UNKNOWN → REVIEW;
- not applicable → ignore;
- gates never prevent score calculation; they affect classification afterward.

There is **no fixed 0.92 auto-accept rule**.

### Classification

Every pair receives:
- `HIGH_CONFIDENCE`
- `REVIEW`
- `DIFFERENT`

`HIGH_CONFIDENCE` requires strong evidence **and no applicable critical-field conflict or UNKNOWN**.

### Human Review

Review should show:
- source material codes;
- descriptions;
- category;
- final score;
- component scores;
- critical-attribute comparison;
- gate status;
- conflicting/missing fields;
- approve/reject action;
- audit information.

Human review is a safety mechanism, not an exception to the architecture.

### Common Material / Common National Material Code

Approved equivalent relationships can form clusters.

A Common Material Record contains:
- common material ID;
- canonical fields;
- source CPSE;
- original source material code;
- mapping relationship;
- status.

The exact Common National Material Code format is **not frozen yet**.

Canonical safety:
- disagreement → UNKNOWN;
- missing from all sources → UNKNOWN;
- never infer, average, or majority-vote a critical specification;
- critical UNKNOWN prevents APPROVED status.

### Mapping

Example:

```text
COMMON-00421
├── CPSE-A → MAT-00182
├── CPSE-B → M-7742
└── CPSE-C → 4500-BLT-16
```

Original source codes are never overwritten.

### Classification Standards

UNSPSC may be evaluated as a supporting classification/blocking aid.

It is **not an architectural dependency** and is not a prerequisite for the MVP. The project should remain functional if UNSPSC is unavailable or only partially mapped.

### Integration

The architecture should expose integration-ready APIs/data exports for SAP/ERP mapping and migration. A live SAP installation is not required for the MVP.

## 5. Evaluation

### Dataset A

Dataset A contains:
- development set;
- blind held-out set;
- hard-negative set.

The matcher is tuned only on development data.

### Dataset B

Dataset B is a separate real-world public-data sanity check:
- outside Dataset A's three-way split;
- blind from matcher developers until Day 17.

Dataset B is not the official CPSE dataset.

### B1 Evidence

A B1 pair requires positive evidence:
- matching manufacturer part number;
- matching industry/standard designation; or
- matching full structured specification set with no conflicting critical field.

Description similarity alone is insufficient.

At the end of Day 4, Person 2 makes the B1/B2 decision. If fewer than 50 qualifying, independently agreed B1 pairs exist, use B2. The 50 is a quality threshold, not a fill target.

### Metrics

Report:
- precision;
- recall;
- F1;
- automation rate;
- aggregate false-positive rate;
- hard-negative false-HIGH_CONFIDENCE rate.

Day 18 is the genuine blind held-out result. Day 19 corrections may use its findings; Day 20 results are post-correction, not a new independent blind test.

## 6. Data Availability

The SIH main-page PS lists:

> **CPSE Material Master Data / Sample Material Master Dataset — To be provided by participating CPSEs**

Therefore, the official CPSE dataset is **not assumed to be available to the team yet**.

Development must proceed with:
- synthetic controlled Dataset A;
- permitted public-data Dataset B;
- an ingestion layer that can adapt when the official CPSE dataset is provided.

Synthetic data must never be presented as real CPSE data.

## 7. Data Sources

Investigate:
1. CPPP;
2. relevant PSU procurement portals;
3. manufacturer/OEM catalogues;
4. GeM as supplementary source;
5. permitted B2B sources if needed.

Public accessibility does not automatically grant scraping or redistribution rights.

## 8. Public-Data Handling

- collect only permitted/publicly viewable content;
- never bypass access controls;
- do not assume bulk scraping is permitted;
- strip BOQ rates/prices;
- remove non-redistributable seller-identifying information;
- do not publish proprietary full catalogue text;
- paraphrase uncertain non-redistributable descriptions;
- credit source categories appropriately.

## 9. Scope

### Floor — Must Ship
- CSV upload;
- normalization;
- parser-based attribute extraction;
- exact matching;
- fuzzy matching;
- basic candidate generation/blocking;
- critical gates;
- review table;
- source-code mapping;
- basic metrics.

### Target
Floor +:
- local semantic embeddings;
- frozen hybrid scoring;
- clustering;
- common-material records;
- analytics.

### Stretch
Only after Target is stable:
- advanced analytics;
- advanced conflict visualization;
- additional categories;
- optional LLM extraction;
- deeper SAP/ERP integration adapters.

## 10. Non-Functional Requirements

- local-first embeddings;
- explainable match decisions;
- source traceability;
- reproducible evaluation;
- candidate blocking for scale;
- safe abstention through REVIEW;
- no production-scale claims from MVP.
