# MIRA --- Engineering Rules and Frozen Decisions

## 1. Source-of-Truth Rule
The SIH26099 problem statement is the source of truth for required capabilities.

Distinguish:
1. SIH requirement
2. verified external fact
3. project design decision
4. implemented feature
5. future/optional feature

Do not present a project design choice as an SIH-mandated specification.

## 2. Source Material Identity
- Preserve every original CPSE material code.
- Never overwrite source records with a common code.
- Every common-material relationship retains CPSE and source material-code traceability.
- Legacy migration is a mapping, not destructive replacement.

## 3. Matching Formula
```text
final_score =
    0.20 × text_similarity
  + 0.20 × semantic_similarity
  + 0.35 × specification_similarity
  + 0.15 × material_grade_similarity
  + 0.10 × other_attributes_similarity
```

- Formula structure is frozen.
- Only numeric weights may be tuned on DEV.
- Never tune using held-out/demo data.
- Score is calculated before critical gates.

## 4. Decision States
- HIGH_CONFIDENCE
- REVIEW
- DIFFERENT

Rules:
- HIGH_CONFIDENCE requires strong score and passing applicable critical gates.
- Critical UNKNOWN prevents HIGH_CONFIDENCE.
- Critical CONFLICT prevents HIGH_CONFIDENCE.
- REVIEW is a valid safety/abstention state.
- No fixed 0.92 auto-accept rule.

## 5. Similarity Safety
- Text similarity is not technical equivalence.
- Semantic similarity is not technical equivalence.
- High similarity cannot override critical conflicts.
- Missing critical specifications cannot be treated as matching.
- Prefer REVIEW over unsafe approval.

## 6. AI Rules

### Core AI
- `all-MiniLM-L6-v2` is the current semantic model.
- Embeddings run locally/on-premises.
- Core matching must not require cloud inference.

### LLM Usage
An LLM may assist with:
- difficult attribute extraction
- messy description interpretation
- classification assistance
- reviewer explanation assistance

An LLM must not:
- directly approve equivalence
- override critical gates
- invent missing technical specifications
- convert uncertainty into certainty
- silently modify source data

LLM output must be structured before entering matching.

If a critical attribute cannot be reliably determined:
```text
UNKNOWN
```

### Provider Abstraction
If an LLM is introduced, isolate it behind a provider interface. Possible providers include Gemini, a local LLM or another compatible provider.

## 7. Deterministic Parsing
Use deterministic methods first where reliable:
- regex
- dictionaries
- abbreviation mappings
- unit normalization
- category-specific rules

Do not globally expand technical abbreviations without verifying safety.

## 8. Critical Fields
### FASTENER
- material_grade
- dimensions

### VALVE
- pressure_rating
- dimensions

### PIPE
- pressure_rating
- dimensions

### ELECTRICAL CONNECTOR
- voltage_class
- dimensions

Only applicable fields are evaluated. Inapplicable fields must not create false conflicts.

## 9. Canonical Material Safety
- Preserve source values.
- Do not invent missing values.
- Do not average technical specifications.
- Do not majority-vote conflicts.
- Conflicting source values become UNKNOWN unless explicitly resolved through governed review.
- Critical UNKNOWN blocks APPROVED.

## 10. Category Classification
Classification may use:
- deterministic rules
- embeddings
- category prototypes
- supervised models if sufficient labels exist

Uncertainty remains visible. Classification determines applicable critical fields.

## 11. Blocking
Blocking is candidate generation, not proof of equivalence.

Evaluate:
- candidate-pair reduction
- candidate recall

A blocking strategy that misses genuine matches is unacceptable.

## 12. Clustering
Use high-confidence relationships to form candidate clusters. Conflicting internal relationships trigger review or cluster splitting.

## 13. Human Review
Review must expose:
- source/target descriptions
- normalized descriptions
- extracted specifications
- similarity components
- final score
- critical gate results
- reasons for UNKNOWN/CONFLICT

Reviewer decisions must be persisted and audited.

## 14. Common National Material Code
NMC is an explicit SIH capability. Exact syntax is a project design decision.

NMC must:
- identify a common material representation
- remain traceable to source CPSE materials
- not replace original CPSE codes
- support mapping and migration/export

## 15. Standardization
- normalize text
- normalize units
- normalize common abbreviations
- preserve original descriptions
- preserve technical meaning
- expose uncertainty

Never normalize away a technically meaningful distinction.

## 16. Tender / BOQ Data
- retain material/item descriptions
- retain technical specifications
- strip rates/prices
- preserve relevant provenance
- avoid unnecessary personal/vendor information
- respect access and redistribution restrictions
- never bypass access controls

Public availability does not automatically imply redistribution permission.

## 17. Dataset B
B1 genuine positive evidence requires:
- matching manufacturer part number, OR
- matching industry/standard designation, OR
- matching complete structured specification set with no conflicting critical field

Text similarity alone never qualifies as ground truth.

If fewer than 50 qualifying agreed B1 pairs exist by Day 4, switch to B2.

B2 description:
> Real-world description sanity check — synthetically paired.

## 18. Evaluation Integrity
Dataset A:
- DEV
- HELD-OUT
- HARD-NEGATIVES

Rules:
- tune only on DEV
- held-out labels remain blind until evaluation
- hard-negative labels remain blind until evaluation
- avoid synthetic-label leakage
- separate generator/ground-truth ownership from matcher development where possible

Day 17 = genuine blind result.  
Day 18 = post-correction rerun, not independent blind testing.

## 19. Metrics
Report:
- Precision
- Recall
- F1
- Automation rate
- Aggregate false-positive rate
- Hard-negative false-HIGH_CONFIDENCE rate
- Candidate reduction ratio

REVIEW is excluded from committed-decision Precision/Recall/F1 and counted through automation rate.

## 20. On-Premises / Sovereignty
Core functionality should work without sending material-master data to external services.

Core local pipeline:
```text
Normalization → Parsing → Embedding → Matching → Critical Gates → Review
```

External LLM use is optional and explicitly governed.

## 21. ERP / SAP Claims
- SAP/ERP integration capability is required by SIH.
- MIRA provides integration-ready interfaces/adapters.
- Never claim live SAP integration without an actual demonstrated connection.
- MIRA is a cross-CPSE harmonization layer, not an SAP MDG replacement.

## 22. Public Claims
Avoid unsupported claims such as:
- “first”
- “industry-wide”
- “all CPSEs use SAP”
- guaranteed procurement savings
- guaranteed inventory reduction
- guaranteed production-scale performance

Distinguish measured results from expected impact.

## 23. Testing
Every meaningful parser/matcher rule change should add/update regression tests.

Current baseline: **28 tests passing.**

Before changing frozen matching logic:
1. run tests
2. inspect controlled examples
3. update DEV evaluation
4. never tune using held-out data

## 24. Verified Matcher Behaviors
Positive:
```text
SS304 GATE VALVE 2 IN 150 LB
STAINLESS STEEL 304 GATE VALVE 2 IN 150 POUND
→ HIGH_CONFIDENCE
```

Critical conflict:
```text
150 LB vs 300 LB
→ REVIEW
```

Critical unknown:
```text
missing target pressure rating
→ REVIEW
```

## 25. Implementation Priority
1. Inspect real dataset.
2. Persist materials.
3. Build material APIs.
4. Connect frontend Materials.
5. Dataset-level candidates.
6. Persist match results.
7. Review workflow.
8. Common Material Record.
9. NMC.
10. Mapping/migration.
11. Clustering/conflict detection.
12. Audit backend.
13. Analytics backend.
14. ERP adapter.
15. Optional AI extraction/classification.
16. Blind evaluation.
17. Demo/presentation.

## 26. Central Principle
> **Similarity finds the candidate. Specifications decide whether it is safe. Humans control the final mapping.**
