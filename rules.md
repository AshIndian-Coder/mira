# SIH26099 — Rules

## 1. Non-Negotiable

1. Preserve every original CPSE material code.
2. Never overwrite source records with a common code.
3. Every match must be explainable.
4. REVIEW is a valid and intentional outcome.
5. Missing critical information is not equivalent to matching information.
6. Inapplicable critical fields do not trigger REVIEW.
7. Conflicting critical fields force REVIEW.
8. Calculate `final_score` before applying gates.
9. Formula shape is frozen for the MVP.
10. Only numeric weights may be tuned on the development set.
11. Similarity score alone must never establish material equivalence.
12. There is no fixed `0.92 → auto-accept` rule.
13. The core MVP must not depend on an LLM for attribute extraction.
14. The exact Common National Material Code format is not yet frozen.
15. UNSPSC is optional/supporting classification, not an architectural dependency.

## 2. Frozen Matching Formula

```text
final_score =
    0.20 × text_similarity
  + 0.20 × semantic_similarity
  + 0.35 × specification_similarity
  + 0.15 × material_grade_similarity
  + 0.10 × other_attributes_similarity
```

Only the numeric weights may be tuned on development data. The weighted-linear structure is frozen unless a formally recorded project decision changes it.

## 3. Attribute Extraction

MVP extraction uses:
- regex;
- technical dictionaries;
- abbreviation mappings;
- unit normalization/conversion;
- category-specific rules/parsers.

LLM extraction is a stretch enhancement only.

## 4. Critical Gates

| Category | Critical fields |
|---|---|
| Fasteners | grade, dimensions |
| Valves/pipes | pressure rating, dimensions |
| Electrical connectors | voltage class, dimensions |

- applicable + equal → continue;
- applicable + conflict → REVIEW;
- applicable + missing → UNKNOWN → REVIEW;
- not applicable → ignore.

A gate never skips score calculation. It controls classification after scoring.

## 5. Classification

### HIGH_CONFIDENCE
Allowed only when:
- the score is sufficiently strong under the configured development-set threshold; and
- no applicable critical field is UNKNOWN; and
- no applicable critical field conflicts.

### REVIEW
Use when:
- critical information is missing;
- critical information conflicts;
- evidence is ambiguous;
- the candidate may be equivalent but cannot be safely auto-resolved.

### DIFFERENT
Use when evidence indicates that the materials are different and no safety gate requires REVIEW.

The system should prefer REVIEW over an unsafe automatic match.

## 6. Canonical Data

- disagreement → UNKNOWN;
- absent from all sources → UNKNOWN;
- never invent specifications;
- never average specifications;
- never majority-vote critical specifications;
- APPROVED is prohibited if a critical canonical field is UNKNOWN.

## 7. Common National Material Code

The PS explicitly expects recommendation/generation of a Common National Material Code and mapping of CPSE codes to it.

Rules:
- preserve every source CPSE code;
- map source codes to a common record;
- do not overwrite source codes;
- exact code syntax is a design decision and is not frozen yet.

## 8. UNSPSC

UNSPSC may support:
- classification;
- blocking;
- analytics.

Do not make the matcher, database model, or end-to-end pipeline dependent on complete UNSPSC coverage.

## 9. Dataset Rules

Dataset A = development + blind held-out + hard negatives.

Dataset B = separate fourth dataset and not part of Dataset A's three-way split.

Person 1 and Person 3 do not see Dataset B content or labels before Day 17. A label-free format-check sample may be shared earlier.

The official CPSE dataset is not assumed to be available yet; synthetic and permitted public data are used until it is provided.

## 10. Ground Truth

For hard negatives and B1 pairs:
- use independent second-annotator checks on a sample;
- measure agreement;
- investigate disagreements;
- do not silently force uncertain items into a class.

## 11. Dataset B

B1 requires positive evidence:
- matching part number;
- matching standard designation; or
- matching full structured specifications with no critical conflict.

Text similarity alone is insufficient.

Person 2 makes the B1/B2 decision at end of Day 4, no exceptions.

Fewer than 50 qualifying agreed-genuine B1 pairs → switch to B2.

The 50 is a quality threshold, not a target.

## 12. Evaluation

Report:
- Precision
- Recall
- F1
- Automation rate
- Aggregate false-positive rate
- Hard-negative false-HIGH_CONFIDENCE rate

Ground-truth table:

| Truth | Output | Result |
|---|---|---|
| duplicate | HIGH_CONFIDENCE | TP |
| duplicate | REVIEW | missed automation opportunity |
| duplicate | DIFFERENT | FN |
| different | HIGH_CONFIDENCE | FP |
| different | REVIEW | safe abstention |
| different | DIFFERENT | TN |

REVIEW is excluded from committed-decision Precision/Recall/F1 and counted in automation-rate analysis.

Day 18 held-out numbers are the genuine blind result. Day 20 post-correction numbers must not be described as an independent blind test.

## 13. Hard Negatives

Include:
- same bolt, different grade;
- same valve, different pressure rating;
- same connector, different voltage class;
- similar dimensions with a critical technical difference;
- one record missing a critical field while the other provides it.

Report hard-negative false-HIGH_CONFIDENCE rate separately.

## 14. Data Sources and Access

Investigation order:
1. CPPP;
2. relevant PSU portals;
3. manufacturer/OEM catalogues;
4. GeM supplementary;
5. permitted B2B sources.

Rules:
- public access does not imply redistribution permission;
- no bypassing access controls;
- no assumption that bulk scraping is permitted;
- use permitted/manual collection by default.

For government portals, collect only publicly viewable content. Do not register as a vendor or bypass controls to reach gated documents.

BOQ-derived data must have rate/price columns stripped before storage for the public project dataset.

## 15. Redistribution

Before public repo/demo:
- remove prices/rates;
- remove non-redistributable seller-identifying data;
- do not publish proprietary full catalogue text;
- do not publish restricted documents;
- paraphrase uncertain descriptions;
- credit source categories.

## 16. Security

- local sentence-transformer embeddings;
- no cloud embeddings in MVP;
- no external LLM processing of source material data in MVP;
- no secrets in Git;
- private evaluation labels.

## 17. Scope Discipline

### Floor first
If Target is delayed, ship:
- exact;
- fuzzy;
- CSV;
- parser-based extraction;
- gates;
- review;
- mapping;
- basic metrics.

Do not sacrifice the Floor for advanced features.

### Target
Add local semantic embeddings, hybrid scoring, clustering, common-material records, analytics.

### Stretch
Only after Target is stable:
- advanced analytics;
- advanced conflict visualization;
- optional LLM extraction;
- extra categories;
- deeper SAP/ERP adapters.

## 18. Do Not

- claim production readiness;
- claim CPSE integration without an actual integration;
- claim real savings without evidence;
- present synthetic data as real CPSE data;
- call B2 genuine duplicate data;
- tune against held-out data;
- present post-correction results as independent blind results;
- hide REVIEW cases;
- approve using text similarity alone;
- invent canonical specifications;
- publish non-redistributable source content;
- build Stretch before Floor/Target stability.

## 19. Demo

Show:
1. near-identical records;
2. high similarity;
3. critical mismatch;
4. gate → REVIEW;
5. missing critical field → REVIEW;
6. genuinely equivalent pair → HIGH_CONFIDENCE;
7. Common Material mapping;
8. original CPSE codes retained.

Any consolidated-demand chart must be labeled directly:

**Illustrative — based on synthetic dataset**
