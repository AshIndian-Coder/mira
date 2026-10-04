# MIRA — System Architecture

> **Document status (updated 2026-10-05).** Sections 1–24 describe the design intent,
> corrected where the implementation had drifted. Section 25 states what is actually
> implemented and measured. Section 26 covers deployment and the resource profile.
>
> Corrections in this revision: the semantic model is no longer MiniLM (it is the
> fine-tuned Qwen3 INT8 checkpoint, 1024-D); vector search runs in **Milvus**, not
> pgvector; the hybrid-score weights and the classification thresholds are the
> values in the code; the engine no longer approves matches — every non-DIFFERENT
> outcome requires human action.

## 1. Purpose
MIRA is an AI-driven cross-CPSE material harmonization platform for SIH26099. It analyzes
heterogeneous material masters, identifies duplicate/near-duplicate/equivalent materials,
standardizes material information, recommends common material representations and Common
National Material Codes, preserves original CPSE codes, and provides human-controlled
approval, mapping, governance and integration workflows.

MIRA is a harmonization layer, not an ERP/SAP replacement.

## 2. Design Principles
1. Preserve source truth.
2. Separate similarity from technical safety.
3. Use AI where semantic ambiguity exists.
4. Use deterministic rules where exact technical correctness is required.
5. Never let an LLM directly approve equivalence.
6. Humans control uncertain/technically ambiguous cases.
7. Preserve source traceability.
8. Keep model providers replaceable.
9. Keep frontend independent of backend language.
10. Evaluate against held-out ground truth.
11. **Never silently degrade.** If the semantic model or the vector store is
    unavailable, the system either provisions it or fails loudly — it does not
    quietly fall back to a weaker matcher.
12. **The engine recommends; humans decide.** No code path may set a match to
    an approved state.

## 3. High-Level Architecture
```text
CPSE MATERIAL SOURCES
        |
     INGESTION                 (CSV / TXT / XML / JSON / XLS / XLSX)
        |
NORMALIZATION / UNITS
        |
ATTRIBUTE EXTRACTION
   /              RULES          OPTIONAL LLM
   \              /
        |
CLASSIFICATION               (category + parsed specs)
        |
        +-------------------------------+
        |                               |
   BLOCKING                       MILVUS VECTOR SEARCH
   (deterministic keys,           (semantic nearest neighbours,
    cross-CPSE, capped)            additive only, uncapped top_k)
        |                               |
        +---------------+---------------+
                        |
              CANDIDATE PAIRS (deduplicated)
                        |
        +---------------+----------------+
        |                                |
  TEXT SIMILARITY                 SEMANTIC SIMILARITY
  (lexical)                       (Qwen3 INT8, 1024-D, local CPU)
        +---------------+----------------+
                        |
             SPECIFICATION COMPARISON
                        |
              HYBRID SCORE ENGINE
                        |
                CRITICAL GATES
          /            |            \
   HIGH_CONFIDENCE   REVIEW      DIFFERENT
   (recommendation)  (queued)    (excluded from queue)
          \            /
        HUMAN REVIEW  ← the only approval path
                        |
              APPROVED RELATIONSHIPS
                        |
           CLUSTERING / CONFLICT CHECK
                        |
            COMMON MATERIAL RECORD
                        |
         COMMON NATIONAL MATERIAL CODE
                        |
            CPSE CODE → NMC MAPPING
                        |
      +-----------------+-----------------+
      |                 |                 |
    AUDIT           ANALYTICS        EXPORT / API
                                          |
                                       ERP/SAP
```

Two things the diagram deliberately shows:

* **Vector search sits beside blocking, not above it.** It can only *add*
  candidate pairs. Blocking results are never modified or withdrawn by it.
* **HIGH_CONFIDENCE is a recommendation, not an approval.** It joins REVIEW in
  the human queue. Only DIFFERENT is excluded.

## 4. Technology Stack

### Frontend
- React + Vite + TypeScript
- REST API
- Recharts

### Backend
- Python 3.13
- FastAPI, Pydantic
- SQLAlchemy
- PostgreSQL (system of record)
- Milvus (vector search) — three containers: `milvus-etcd`, `milvus-minio`,
  `milvus-standalone` (`docker-compose.milvus.yml`)

pgvector is **not** used. Postgres full-text search (`to_tsvector`) provides the
lexical index; all approximate nearest-neighbour search lives in Milvus.

### AI / ML
- `sentence-transformers` 6.0.1
- `transformers` (Qwen3 architecture support)
- `torch` (CPU build — no GPU required)
- `bitsandbytes` + `accelerate` (INT8 loading)
- The fine-tuned MIRA checkpoint on Hugging Face: `AshIndian/Mira.ai`
- `all-MiniLM-L6-v2` — legacy baseline only; used by historical evaluation
  scripts, never by production matching

## 5. AI Architecture

### 5.1 Semantic Model
The production semantic model is the fine-tuned **Qwen3 INT8** checkpoint hosted
at `AshIndian/Mira.ai` (Epoch-2, quantised).

| Property | Value |
|---|---|
| Embedding dimension | **1024** |
| Size on disk | ~753 MB (`model.safetensors`) |
| Quantisation | INT8 via bitsandbytes (`load_in_8bit`) |
| Device | CPU |
| Module layout | Transformer → Pooling → Normalize (`modules.json`) |

The dimension is not cosmetic: it must match the Milvus collection
(`FLOAT_VECTOR, dim=1024`). A checkpoint with a different dimension is rejected
rather than accepted as a drop-in replacement.

MiniLM (384-D) survives only as an explicit, opt-in baseline
(`MIRA_EMBEDDING_MODEL=minilm`) for the historical evaluation harnesses. It is
not reachable from the default production path.

### 5.2 Model Provisioning (auto-download)
A fresh clone contains no model — `models/` is gitignored. Provisioning rules:

1. **Search local paths first**, in order: `MIRA_QWEN_MODEL_PATH`,
   `MIRA_MODEL_PATH`, `MIRA_MODELS_DIR/Mira.ai`, then the standard locations
   (`~/mira-model-test/Mira.ai`, `~/Desktop/mira-model-test/Mira.ai`,
   `~/.mira/models/Mira.ai`, `~/models/Mira.ai`, `<project>/models/Mira.ai`,
   `<project>/models/trained/Mira.ai`, `<project>/models/trained/qwen`,
   `<project>/models/qwen`).
2. **A directory only counts as a model if it holds weights as well as
   `config.json`** (`model.safetensors`, `pytorch_model.bin`, an index file, or
   a `.onnx`). This prevents a half-written download from being mistaken for a
   usable model on the next run.
3. If nothing valid is found and `model_auto_download` is true (default), the
   checkpoint is fetched from Hugging Face **once per process**.
4. The download lands in a **staging directory** (`Mira.ai.download`), is
   verified by loading it back through the same call production uses, and the
   dimension is checked against 1024. Only then is it moved into place
   atomically — so an interrupted download cannot leave a broken model behind.
5. The Hub files are **copied as-is**. The loaded model is never re-serialised:
   a bitsandbytes INT8 model cannot be re-saved (`save_pretrained` raises an
   empty-message `NotImplementedError`), so re-saving would silently fail to
   install anything.
6. A successful install writes `MIRA_MODEL_PROVENANCE.txt` next to the weights
   recording the source and the verified dimension.
7. **If provisioning fails, matching stops** with a `FileNotFoundError` listing
   every searched path and the reason the download failed. There is no silent
   fallback to a smaller model.

Environment switches:

| Variable | Default | Effect |
|---|---|---|
| `MIRA_MODEL_AUTO_DOWNLOAD` | `true` | `false` = strict local-only mode |
| `MIRA_MODELS_DIR` | — | override the install/search directory |
| `MIRA_EMBEDDING_MODEL` | — | explicit model path or alias (`minilm`, `base-minilm`) |

Measured on the demo machine: first run (model absent) 34 s including download
and verification; subsequent runs 4.3 s from disk with no network access.

### 5.3 Deterministic Attribute Extraction
The first extraction layer uses:
- text normalization
- abbreviation mappings
- unit normalization
- regex
- technical dictionaries
- category-specific patterns

Examples:
```text
SS-304 / SS304 / STAINLESS STEEL 304 → SS304
150# / 150 POUND → 150 LB
```

### 5.4 Optional LLM Attribute Extraction
An LLM may convert difficult descriptions into structured attributes.

Example:
```text
"SS GATE V/V 50NB CL150 RF ENDS"
```

Possible structured result:
```json
{
  "type": "GATE VALVE",
  "material": "SS",
  "size": "50 MM",
  "pressure_class": "150",
  "connection": "RF"
}
```

The LLM is an extraction assistant, not the final equivalence judge.

Rules:
- output must be structured
- uncertainty remains UNKNOWN
- critical conflicts remain conflicts
- LLM output cannot create HIGH_CONFIDENCE directly
- core matching works without a cloud LLM
- provider is replaceable

Potential boundary:
```text
LLMProvider
  ├── GeminiProvider
  ├── LocalLLMProvider
  └── OtherProvider
```

## 6. Intelligent Classification
Classification can combine:
- deterministic category rules
- normalized attributes
- parsed specifications
- embedding/category similarity

If sufficient reliable labels exist, a supervised classifier can be introduced.

Classification supports category-specific critical fields and does not override critical gates.

## 7. Normalization
Normalize safe variations in:
- case
- punctuation
- separators
- abbreviations
- units
- technical aliases

Never erase technically meaningful distinctions.

## 8. Specification Parsing
Extract:
- material grade
- pressure rating
- dimensions
- voltage class
- category-specific attributes

Parser output is separate from the original description.

## 9. Critical Fields
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

Categories outside this table have no critical fields, so their gates are
trivially PASS. A category mismatch between source and target is itself a
CONFLICT.

## 10. Candidate Generation

### 10.1 Deterministic Blocking
Candidate keys include:
- manufacturer part number (`MPN:`)
- category (`CAT:`)
- category + grade (`CAT_GRADE:`)
- category + technical anchor (`TYPE:`)
- distinctive description tokens (`DESC:`)

Blocking runs **cross-CPSE only** — same-CPSE pairs are not candidates.
Candidates are ordered by number of shared keys, then document order, and the
per-source list is **capped** (`max_candidates_per_material`, default 50,
maximum 500) so a single generic token cannot explode the pair count.

Blocking is candidate generation, not equivalence proof. Measure both reduction
and candidate recall — and remember that a cap is a recall limit: pairs ranked
below the cap are never compared.

### 10.2 Milvus Vector Search (additive)
After the blocking pass, every material is queried against the Milvus collection
by embedding similarity (`top_k=50`, COSINE, same-category filter, cross-CPSE
only). Hits are deduplicated against pairs already evaluated and **added** to
the candidate set.

Properties:
- It can only **add** pairs; it never removes or alters a blocking result.
- It is **not capped** by `max_candidates_per_material`.
- If Milvus is unavailable the run continues with blocking-only results — the
  vector step is the only part that degrades, and it does so quietly by design
  (see §18 for the operational warning).

Measured contribution (see §24 for the full A/B).

## 11. Hybrid Matching
```text
final_score =
    0.175 × text_similarity
  + 0.400 × semantic_similarity
  + 0.250 × specification_similarity
  + 0.125 × material_grade_similarity
  + 0.050 × other_attributes_similarity
```

Constraints: weights are non-negative, sum to 1.0, `specification ≥ 0.25`,
`grade ≥ 0.10`. The formula structure is frozen; only the numeric weights may be
tuned on DEV.

Note that **60% of the weight is model-independent** (text + specification +
grade + other). A semantic-model change cannot by itself move a pair from
DIFFERENT to HIGH_CONFIDENCE.

## 12. Critical Gates
Possible states:
- PASS
- UNKNOWN
- CONFLICT

Rules:
```text
Critical UNKNOWN  → cannot be HIGH_CONFIDENCE   (→ REVIEW)
Critical CONFLICT → cannot be HIGH_CONFIDENCE   (→ DIFFERENT)
Strong score + all applicable fields PASS → HIGH_CONFIDENCE (recommendation only)
```

## 13. Match Classification

| Decision | Condition |
|---|---|
| `HIGH_CONFIDENCE` | `final_score ≥ 0.85` **and** every applicable critical gate PASS |
| `REVIEW` | any gate UNKNOWN, or `final_score > 0.45` |
| `DIFFERENT` | otherwise (including any CONFLICT) |

The two thresholds are environment-overridable
(`MIRA_HIGH_CONFIDENCE_SCORE`, `MIRA_DIFFERENT_SCORE`). No 0.92 auto-accept rule
is used.

## 14. Human Review
Reviewers see:
- source/target materials
- original/normalized descriptions
- extracted specifications
- similarity scores
- critical checks
- AI recommendation
- reasons for uncertainty/conflict

Actions:
- Approve
- Reject
- Override where governance permits

Every decision is auditable.

### 14.1 Approval Governance (enforced in code)
- The engine **never** writes an approved state. There is no `AUTO_APPROVED`
  candidate status in the pipeline.
- `HIGH_CONFIDENCE` and `REVIEW` both enter the queue as **PENDING**;
  `HIGH_CONFIDENCE` is simply presented first.
- Only `DIFFERENT` candidates are excluded from the queue.
- A mapping (Common Material Code) is created **only** from a human `APPROVED`
  decision.
- A review action on an already-decided candidate (APPROVED / REJECTED /
  DIFFERENT) is rejected with HTTP 409. A pending `HIGH_CONFIDENCE` match can
  always be actioned — the earlier 409-on-high-confidence defect is closed.

Analytics may still **read** legacy `AUTO_APPROVED` rows from earlier demo data;
no code path writes new ones, so the automation rate is 0 by construction.

## 15. Common Material Record
Contains:
- canonical description
- canonical category
- canonical technical attributes
- source CPSE materials
- original CPSE material codes
- approval state
- provenance

If sources disagree or a critical field is unavailable:
`canonical field = UNKNOWN`

Never average, majority-vote or invent critical technical values.

## 16. Common National Material Code
The SIH problem statement requires recommendation/generation of a Common National Material Code.

Exact syntax is a MIRA design decision.

The code must:
- uniquely identify the common representation
- remain traceable to source records
- not replace original CPSE codes
- support mapping and migration/export

## 17. Clustering
High-confidence relationships form candidate clusters. Internal conflicts trigger
review or cluster splitting rather than blind merging.

## 18. Database and Vector Store

### PostgreSQL — system of record
Tables: `cpses`, `users`, `upload_batches`, `materials`, `match_suggestions`,
`cnmc`, `mappings`, `feedback`, `audit_logs` (`mira_full_schema.sql`).
A GIN full-text index supports lexical search.

The application talks to it through SQLAlchemy; the `store` module exposes
`MATERIALS` / `CANDIDATES` / `CNMC_REGISTRY` as list-like persistent
collections, so routes behave as if everything were in memory.

**Ingestion is the only writer of vectors.** `POST /api/materials/upload`
inserts each record's embedding into Milvus. Nothing else writes there.

### Milvus — vector search
| Property | Value |
|---|---|
| Collection | `material_embeddings` |
| Primary key | mirrors `materials.id` (so hits join straight back) |
| Vector | `FLOAT_VECTOR`, dim 1024 |
| Index / metric | `IVF_FLAT` / `COSINE` |
| Write mode | `upsert` |
| Search | `top_k = 50`, `nprobe = 16` |

**Operational warning — the one fail-soft that matters.** If Milvus is down or
disabled, the vector write is skipped and the search returns nothing, without
raising: uploads succeed, matching still runs, and the only symptom is *fewer
candidates*. For this reason, **verify the three containers are `Up` before any
demonstration**, and treat a pair count equal to the blocking-only prediction as
a Milvus failure signal.

Creation: `create_milvus_collection.py` (dimension is derived from the active
model, so it stays in step with §5.1). `--recreate` drops and rebuilds the
collection — never run it after an upload unless you intend to discard the
vectors.

## 19. API Boundary
Current (all live, Postgres-backed):
```text
GET  /
GET  /health
POST /api/materials/upload
GET  /api/materials
GET  /api/materials/stats
GET  /api/materials/{id}
POST /api/matching/compare
POST /api/matching/run-batch
GET  /api/matching/candidates
GET  /api/matching/candidates/{id}
GET  /api/matching/stats
GET  /api/review/queue
GET  /api/review/queue/{id}
POST /api/review/queue/{id}/action
GET  /api/review/summary
GET  /api/audit
GET  /api/audit/export
GET  /api/analytics/overview
GET  /api/analytics/by-cpse
GET  /api/analytics/categories
GET  /api/analytics/scores
GET  /api/mappings
GET  /api/mappings/{id}
POST /api/mappings/generate
GET  /api/mappings/export/flat
```

`POST /api/matching/run-batch` body:
```json
{ "max_candidates_per_material": 50, "overwrite": false,
  "source_cpse": null, "target_cpse": null }
```
`overwrite: true` clears stored candidates first; the frontend sends `false`.

Planned:
```text
GET  /api/common-materials
POST /api/common-materials
GET  /api/integrations
POST /api/integrations/{id}/sync
```

## 20. ERP / SAP Integration
MIRA exposes integration-ready boundaries rather than claiming a live SAP connection.

```text
MIRA API
   |
ERP Integration Adapter
   ├── Mock ERP
   ├── SAP Adapter
   └── Future ERP adapters
```

## 21. Governance
Audit events cover:
- MATCH_CREATED
- MATCH_REVIEWED
- MATCH_APPROVED
- MATCH_REJECTED
- COMMON_MATERIAL_CREATED
- MAPPING_CREATED
- EXPORT_GENERATED
- MATERIAL_UPDATED

`MATCH_AUTO_APPROVED` is **no longer emitted** — the engine has no approval path
(§14.1). Legacy events from earlier data may still appear when reading history.

## 22. Analytics
Metrics include:
- materials by CPSE
- materials by category
- match decisions
- review backlog
- harmonization progress
- duplicate/near-duplicate counts
- confidence distribution
- blocking reduction
- mapping progress

## 23. Evaluation
Dataset A:
- DEV
- HELD-OUT
- HARD-NEGATIVES

Dataset B is separate and follows its own collection/evidence rules.

Evaluation harnesses (`data/evaluation/`, `tests/test_*.py`) may reference the
MiniLM baseline explicitly. Those references are historical comparisons, not
production configuration.

## 24. Scale and Measured Behaviour
```text
reduction_ratio =
1 - candidate_pairs / all_possible_pairs
```

A single-server PostgreSQL prototype is not proof of production-scale performance
for millions of records.

What has been **measured** (not estimated):

| Dataset | Blocking only | With Milvus | Ceiling (all cross-CPSE pairs) |
|---|---|---|---|
| 20-material mixed set, cap 5 | 80 | **150** | 150 |
| 150 real valve records, cap 50 | ~4,800 | **5,500+** | 6,425 |

Reading: at cap 5 the blocking cap hides 70 of the 150 true pairs; the vector
pass recovers them. At cap 50 the cap still hides ~1,600 pairs, and the vector
pass closes part of that gap. **Milvus can only add pairs** — a run that returns
the blocking-only number exactly means the vector step did not contribute.

The 150-row run was also validated through the UI: 153 materials processed
(150 uploaded + 3 pre-existing rows), 5,500+ candidates, 450 queued for review,
**0 auto-approved**.

## 25. Current Implementation

Implemented:
- frontend screens (Materials, Match Review, Common Materials, Mappings, ERP
  Integration, Analytics, Audit Trail, User Directory, Settings)
- FastAPI foundation, JWT auth + RBAC, seeded CPSEs and demo users
- normalization, rule-based specification parser
- deterministic blocking + Milvus vector search
- hybrid scoring, category-aware specification comparison, critical gates,
  match classifier
- full matching / materials / review / audit / analytics / mappings API
- PostgreSQL persistence for materials, candidates, mappings, audit
- CSV ingestion, dataset-level matching, human review with audit trail
- provisional NMC mapping generation
- **model auto-provisioning** (§5.2) with verification and loud failure
- **approval governance** (§14.1): the engine never approves

Verification status:
- `tests/test_matching_run_batch.py` + `tests/test_synthetic_material_master_manifest.py`
  — **14 passed** (measured after the governance change; the suite starts and ends
  with a clean test database, asserting HC/REVIEW land as PENDING and that no
  `MATCH_AUTO_APPROVED` event is written).
- Auto-download: first-run download + install + dimension verification observed
  end-to-end through the UI; second run loads from disk with no network access.
- Milvus: 20/20 vectors written and read back; 15 cross-CPSE neighbours returned
  for a single query, against a cap that would have surfaced 5.

Known gaps (deliberate, not defects):
- The full pytest suite has not been re-run since the Qwen migration; the older
  "38 tests" figure predates it.
- A few libraries used by optional features (pandas, pymupdf, groq) are not
  pinned in `requirements.txt`.
- Re-uploading an identical file is not idempotent (reset the batch first).
- Legacy `AUTO_APPROVED` rows remain readable in analytics.

Next:
1. Blind evaluation against held-out ground truth.
2. Common Material Record (canonical form beyond provisional NMC).
3. Clustering/conflict detection verification.
4. Idempotent re-upload endpoint.
5. Optional LLM extraction/classification if justified.
6. Deployment hardening (§26).

## 26. Deployment and Resource Profile

### What must run
| Component | Notes | Memory |
|---|---|---|
| PostgreSQL | system of record; **no pgvector** | ~200–500 MB |
| Milvus (`etcd` + `minio` + `standalone`) | vector search | **4–8 GB** |
| Backend (uvicorn + torch CPU + model) | model resident in RAM | 2–3 GB |
| Frontend | static build behind a reverse proxy | negligible |
| Model artefacts | 753 MB weights (~1.5 GB with Hub cache) | ~2 GB disk |

**Practical floor: 4 vCPU / 16 GB RAM / 20 GB disk.** 8 GB works but is tight.

### Repository state
`docker-compose.milvus.yml` ships for the vector store. There is **no
Dockerfile and no compose file for the application** — a deployment needs:
`Dockerfile.backend`, `Dockerfile.frontend` (build stage → nginx), and a
top-level `docker-compose.yml` joining Postgres, Milvus, backend and frontend,
plus a reverse-proxy rule for `/api` and `/health`. The frontend already calls
`/api` same-origin, so no application code needs to change.

Startup order matters: the schema must exist and Milvus must be healthy before
the first upload, otherwise the vector write is skipped silently (§18).

### Cold-start behaviour
The first upload after a fresh deployment triggers the 753 MB model download
(~30–60 s on a good connection). For demonstrations, pre-stage `models/Mira.ai`
into the container volume so the first upload is fast.

### Free hosting — what actually fits
| Component | Free tier possible? |
|---|---|
| PostgreSQL (Neon/Supabase) | yes |
| Frontend (Cloudflare Pages/Vercel) | yes |
| Backend on 1 GB (Render/Fly free) | likely OOM with torch + model |
| Milvus (3 containers) | **no** — no free tier offers 4–8 GB |

Therefore:
- **Free + hosted** requires `MILVUS_ENABLED=false` — the app runs, but returns
  blocking-only candidate counts (~80 instead of ~150 on the small set). The
  Milvus contribution is lost.
- **Free + complete** is possible only on a provider that grants a large
  always-free VM (e.g. Oracle Cloud Always Free, 4 ARM cores / 24 GB) — with
  caveats around signup approval and ARM compatibility.
- **Cheapest robust** option is a small paid VM (~$5–6/month class) with swap
  enabled and Milvus memory-capped.
- **Local demonstration remains the primary, lowest-risk deployment target.**

### Security checklist before any public exposure
1. Change `secret_key` (dev default is committed in `config.py`).
2. Change the seeded admin password (`Admin@123`).
3. Restrict CORS — the current policy is `allow_origins=["*"]`.
4. Terminate TLS at the proxy; add backups (`pg_dump`) and log rotation.
5. Keep the database off the public interface; only the proxy should be exposed.
