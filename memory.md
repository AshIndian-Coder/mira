# MIRA - Project Memory

**Purpose of this file.** Curated working memory: what is frozen, what is true in the
code today, and what has been superseded. Dated entries are append-only and never
rewritten; when a decision changes, the old entry stays and a correction is recorded
here.

**Current authority:** repository commit `747d43a` (fork `main`, 2026-10-05).
Every "verified" line below was read from that commit or produced by running its code.

**History:** the pre-2026-10-05 journal (1,122 lines, 2026-09-13 to 2026-09-30) is kept
in `memory_archive_2026-09.md`. Section 9 lists which of its entries are now stale.

---

## 1. Project

**SIH26099 - AI-Driven Standardization and Harmonization of Material Codes Across CPSEs**

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
- Product goal: **One Nation - One Material Code**, while preserving source CPSE codes.

## 2. Requirements / Design Authority

Use these sources in this order:

1. **Official SIH26099 problem statement** - requirement authority.
2. **Current repository/source code and active backend API** - implementation authority.
3. **Teammate frontend PDF** - proposed product/UI roadmap.

The teammate PDF proposes capabilities beyond the official minimum (JWT auth, role-based
routing, CPSE selector, richer MatchCard/AI reasoning, CNMC registry, ROI calculator, SAP
sync UI, admin/user management). These are **proposed product capabilities**, not official
SIH-mandated folder names or API contracts.

Do not rebuild the existing frontend simply to reproduce the PDF's folder structure.
Never fake unsupported functionality.

## 3. Team Roles

- Person 1 - Data & Evaluation
- Person 2 - Matching Engine
- Person 3 - Backend & Database
- Person 4 - Frontend & Review + frontend-facing API integration
- Person 5 - Integration, Clustering & Demo
- Person 6 - Coordination, documentation, testing and presentation

## 4. Frozen Architecture

CPSE Material Master -> Ingestion -> Normalization/Units -> Parser/Attribute Extraction ->
Category/Blocking -> Candidate Generation -> Hybrid Scoring -> Critical Gates ->
HIGH_CONFIDENCE/REVIEW/DIFFERENT -> Human Review -> Approved Relationships ->
Clustering/Conflict Detection -> Common Material Record -> Common National Material Code ->
CPSE Code Mapping -> Audit/Export/API.

Core principle:

**Similarity finds the candidate. Specifications decide whether it is safe.
Humans control the final mapping.**

## 5. AI Architecture

### Core AI
- Production embedding model: `AshIndian/Mira.ai` - a fine-tuned Qwen3 checkpoint
  published in INT8 form. `Qwen3Model`, 28 layers, hidden size **1024**, ~753 MB.
- Inference is local and CPU-only. No GPU, no cloud call, no token at run time.
- Semantic similarity is **one of five** components of the frozen hybrid score.
- AI similarity never directly approves a material.
- MiniLM (`all-MiniLM-L6-v2`) survives **only** as a non-default alias
  (`minilm`, `base-minilm`) for historical offline training and stability scripts.
  Production resolution never falls back to it silently - a missing Qwen model raises
  `FileNotFoundError` instead.

### AI-Assisted Attribute Extraction
- First layer is deterministic: normalization, regex parsing, technical dictionaries,
  unit handling, category-specific parsing.
- LLM is an optional fallback (`MIRA_LLM_PROVIDER` = `none` | `ollama` | `groq`,
  default `none`), off by default, output must be structured before matching.
- Uncertain or missing critical attributes remain `UNKNOWN`.
- LLM output cannot override critical conflicts or directly approve equivalence.
- Provider must remain replaceable.

### Intelligent Classification
- Deterministic taxonomy plus keyword inference plus normalized attributes.
- A trained classifier may be added only if sufficient reliable labels exist.
- Classification does not override critical technical gates.

## 6. Frozen Decisions (current)

| # | Decision |
|---|---|
| 1 | Preserve every original CPSE material code; never overwrite source records with a common code. |
| 2 | `final_score = 0.175 text + 0.400 semantic + 0.250 specification + 0.125 grade + 0.050 other` |
| 3 | Only numeric weights may be tuned on DEV; the five-component shape is frozen. Asserted in source: sum = 1.0, `w_spec >= 0.25`, `w_grade >= 0.10`. |
| 4 | Score is calculated **before** gates. Gates can only downgrade, never upgrade. |
| 5 | Missing applicable critical field = UNKNOWN -> REVIEW. |
| 6 | Conflicting critical field -> **DIFFERENT** (see correction C3). |
| 7 | No fixed 0.92 auto-accept rule. Thresholds are 0.85 (HIGH_CONFIDENCE) and 0.45 (REVIEW floor), overridable by `MIRA_HIGH_CONFIDENCE_SCORE` / `MIRA_DIFFERENT_SCORE`, calibrated, not to be tuned in the field. |
| 8 | **There is no automated approval path.** HIGH_CONFIDENCE is a recommendation shown to a human; `automation_rate` is 0 by design. |
| 9 | Text/semantic similarity alone cannot safely approve a material. |
| 10 | AI/LLM output cannot directly approve equivalence. |
| 11 | Critical canonical specifications are never invented, averaged or majority-voted. Critical UNKNOWN blocks APPROVED. |
| 12 | Core matching must function without a cloud LLM. LLM extraction is optional enhancement. |
| 13 | UNSPSC is optional supporting classification/blocking/analytics, not a dependency. |
| 14 | Common National Material Code syntax is our design decision: `MIRA-<TYPE>-<CATEGORY>-<global id>`, deterministic per cluster, idempotent on canonical identity hash. |
| 15 | SAP/ERP integration is integration-ready REST/CSV unless an actual live integration exists. |
| 16 | Matching logic is frozen pending proper DEV/HELD-OUT evaluation. |
| 17 | Do not create a separate parser for every CPSE. Generic ingestion handles unfamiliar structures; CPSE identity is **data (provenance)**, never parser logic. |
| 18 | Milvus only ever **adds** candidates. Losing it must degrade candidate count visibly, never silently change decisions. |
| 19 | Provenance is never guessed. Unrecognised CPSE -> `CPSE_GENERIC`. |

## 7. Verified State at `747d43a`

Everything in this section was read from source or measured by running it.

### Counts
| Fact | Value |
|---|---|
| API endpoints under `/api` | **38** (analytics 5, audit 2, auth 4, mappings 6, matching 7, materials 4, review 4, users 6), plus `GET /` and `GET /health` |
| Routers | 8, all under `backend/app/api/v1/` |
| Backend tests | **34 test modules / 278 test functions** (35 `.py` files; the 35th is `__init__.py`) |
| Postgres tables | 9: `cpses`, `users`, `upload_batches`, `materials`, `match_suggestions`, `cnmc`, `mappings`, `feedback`, `audit_logs` |
| Frontend screens | 11: Analytics, AuditTrail, CommonMaterials, Dashboard, ERPIntegration, Login, Mappings, MatchReview, Materials, Settings, UserManagement |
| Frontend stack | React 19.2.8, Vite 8.2.2, TypeScript ~6.0.2 |
| Milvus compose | `milvusdb/milvus:v2.6.23`, `etcd:v3.5.25`, `minio:RELEASE.2024-12-18T13-15-44Z` |

### Matching
- Weights in force: 0.175 / 0.400 / 0.250 / 0.125 / 0.050 (`scoring.py` L14-18).
- Classifier (`classifier.py`): CONFLICT -> DIFFERENT; score >= 0.85 **and** gates pass ->
  HIGH_CONFIDENCE; UNKNOWN critical or score > 0.45 -> REVIEW; otherwise DIFFERENT.
- Caps: `run-batch` `max_candidates_per_material` default **50**, max **500**.
  CNMC single-match default 10 (max 50); CNMC batch default 5 (max 50), `min_score` 0.65.
- CNMC code: `f"MIRA-{type_code}-{category_code}-{global_id}"` (`cnmc/service.py` L68).
- Taxonomy type/category codes: VLV 17, PIP 23, BRG 08, FST 12, ELC 31, GSK 14,
  CBL 26, FLG 19, PMP 45.

### Review and governance
- `review_status` is written as **PENDING** or **DIFFERENT** at candidate creation, and as
  **APPROVED** / **REJECTED** only by a human action on `/api/review/queue/{id}/action`.
- **Nothing in the codebase writes `AUTO_APPROVED`.** It is only *read*, by
  `analytics.py` and `review.py`, to keep legacy rows visible.
- `POST /api/mappings/generate` consumes `review_status == "APPROVED"` **only**.
  Human approval is the only route into a Common Material Code.
- Acting twice on the same candidate returns 409 rather than overwriting the decision.

### Ingestion
- Adapters present: `generic`, `bhel`, `bhel_technical`, `nalco`, plus `registry.py`.
  Parsers present: `bhel_parser.py`, `nalco_parser.py`, `ntpc_parser.py`.
  (This contradicts the 2026-09 cleanup entry - see correction C2.)
- Legacy file parsers: `csv_parser`, `excel_parser`, `json_parser`, `txt_parser`,
  `xml_parser`, plus `pdf_extractor.py` for tender documents, `detector.py`,
  `provenance.py`, `document_inspector.py`, `pipeline.py`.

### Upload formats - all six executed against `parse_legacy_file`
Identical three-row material set (NTPC / IOCL / BPCL), one file per format:

| Format | Result | Notes |
|---|---|---|
| `.csv` | 3/3 rows | also fine with UTF-8 BOM, CRLF, quoted fields |
| `.txt` | 3/3 rows | pipe-delimited, header or positional |
| `.xls` | 3/3 rows | xlrd; `_sheet_name` kept per row |
| `.xlsx` | 3/3 rows | openpyxl; multi-sheet parsed sheet by sheet |
| `.json` | 3/3 rows | bare list or `{"materials": [...]}` wrapper |
| `.xml` | 3/3 rows | child tags or attributes; a literal `&` must be `&amp;` |

Empty and header-only files return 0 rows without raising. Extensions are matched
case-insensitively. `.pdf` is rejected with a clear `ValueError`.
Deps already pinned: `openpyxl>=3.1.5`, `xlrd>=2.0.2`, `xlwt>=1.3.0`.

### CPSE provenance evidence chain (measured)
| Evidence | Confidence |
|---|---|
| `cpse` column on the row | 1.00 `EXPLICIT_ROW` |
| Excel sheet name | `SHEET_NAME` |
| filename token | 0.85 `FILENAME_METADATA` |
| code prefix (`IOCL-V001`) | 0.80 `OBSERVED_CODE_PATTERN` |
| none | `CPSE_GENERIC` / UNKNOWN |

Consequence: one sheet per CPSE in a single `.xlsx` is the most robust multi-CPSE upload,
because the sheet name is itself evidence even when rows carry no `cpse` column.

### Model provisioning
- Resolution order: `MIRA_EMBEDDING_MODEL` / `MIRA_QWEN_MODEL_PATH` / `MIRA_MODEL_PATH` /
  `MIRA_MODELS_DIR`, then the `~/mira-model-test/Mira.ai` style paths, then
  `<project_root>/models/Mira.ai`.
- Auto-download (`_download_qwen_model`): `snapshot_download` into a `.download` staging
  dir -> **load it back to verify** -> assert dim == 1024 -> move into place ->
  write `MIRA_MODEL_PROVENANCE.txt`. Gated by `settings.model_auto_download`
  (env `MODEL_AUTO_DOWNLOAD`). One attempt per process.
- Hub files are **copied, never re-saved**: re-serialising a bitsandbytes INT8 model
  raises `NotImplementedError` inside transformers. That is what PR #11 fixed.
- Missing model + download disabled -> `FileNotFoundError` listing every searched path.
  Never a silent downgrade.

### Measured evaluation numbers still standing
- 150-row real cross-CPSE valve set: blocking candidates at cap 5 / 20 / 50 =
  656 / 2,440 / 4,848; uncapped 6,425.
- 12-row mixed-category demo: 51 possible cross-CPSE pairs -> 17 blocking candidates at
  cap 50, keeping all 12 genuine same-item pairs.
- Live UI run, 153 materials, Milvus on: 5,500+ candidate pairs, 450 at review,
  **0 auto-approved**.
- First model download 34 s, cached re-load 4.3 s, dim 1024.

## 8. Known Defects (confirmed, not yet fixed)

1. **Re-upload is not idempotent** - uploading the same file twice ends in a 500.
2. **Extension/content mismatch answers 500** - a real `.xlsx` saved as `.csv` raises
   `csv.Error`, which is not a `ValueError`, so the upload handler's `except ValueError`
   misses it. Should be a 400 with a clear message.
3. **Error text names a variable that does not exist** - `resolve_model_name()` prints
   `MIRA_MODEL_AUTO_DOWNLOAD=false` / `=true`. The real switch is the pydantic setting
   `model_auto_download`, i.e. env `MODEL_AUTO_DOWNLOAD`. Confusing on an air-gapped box.
4. **No `conftest.py`** - a suite run touches the development database.
5. **Legacy `AUTO_APPROVED` rows** from earlier builds still sit in analytics
   denominators, distorting `automation_rate`.
6. **No deployment packaging** - only `backend/docker-compose.milvus.yml` exists; no
   `Dockerfile.backend`, `Dockerfile.frontend` or top-level compose.
7. `Final_Master_Material_Records.csv` is a **Git-LFS pointer**, not the 239 MB payload.

## 9. Corrections to Superseded Entries

The archive keeps the original wording. These are the entries that no longer describe
the code.

- **C1 - Scoring weights.** The frozen-decision line `0.20 text + 0.20 semantic +
  0.35 specification + 0.15 grade + 0.10 other` is superseded. Production weights since
  the 2026-09-25 freeze are **0.175 / 0.400 / 0.250 / 0.125 / 0.050**. The shape is
  unchanged; only the numbers moved, inside the asserted constraints.
- **C2 - "Removed the CPSE-specific adapters".** The 2026-09 Ingestion Architecture entry
  lists BHEL, BHEL-technical, NALCO adapters, the NTPC parser and `registry.py` as
  removed. **They are present in `747d43a`.** The generic-first *principle* still holds
  and is what the upload path uses; the site-specific files were not deleted.
- **C3 - "Conflicting critical fields -> REVIEW".** `classifier.py` returns **DIFFERENT**
  for a critical CONFLICT, which removes the pair from the review queue. This is
  consistent with "only DIFFERENT candidates may be excluded from review", but it is a
  policy change from the original frozen decision and **still needs explicit sign-off**.
  If sign-off says REVIEW, it is a one-line change.
- **C4 - "Automated Decision Routing & Review Queue Governance - 2026-09-29".** That entry
  describes `AUTO_APPROVED` routing, `MATCH_AUTO_APPROVED` audit events and
  `/api/mappings/generate` consuming auto-approved candidates. **None of that is in the
  current code.** PR #10 ("Fix/human approval") removed the automated path; the test suite
  now asserts that no `MATCH_AUTO_APPROVED` events are emitted. Governance is manual-only.
- **C5 - "Local `all-MiniLM-L6-v2` sentence-transformer".** Superseded by the 1024D Qwen
  INT8 migration (2026-09-29/30). MiniLM is alias-only and is not used for scoring.
- **C6 - Test counts.** Entries quoting 48/48, 270/270 and 273/273 were true at their
  dates. Current source contains **34 test modules / 278 test functions**; the suite has
  not been run end-to-end in the current environment.
- **C7 - "39 endpoints".** The correct count at `747d43a` is **38**.

## 10. Journal

### 2026-10-04 - PR #10, `8ba9914` "Fix/human approval"
Removed the automated approval path. Every candidate now enters the queue as PENDING or
DIFFERENT; only a human action produces APPROVED or REJECTED, and mapping generation
consumes APPROVED only. See correction C4.

### 2026-10-05 - PR #11, `747d43a` "Fix Hugging Face auto-download"
`backend/app/services/matching/embeddings.py`, +82/-24. Auto-download now copies the Hub
files instead of calling `save_pretrained` on a loaded INT8 model, which raised
`NotImplementedError` inside transformers. Download goes to a staging directory, is
verified by loading it back and checking dim == 1024, and only then replaces the target,
so an interrupted download cannot leave a half-installed model. Verified on a machine with
the model hidden: first run downloaded and verified in 34 s (`dim=1024`), re-run loaded
from cache in 4.3 s.

### 2026-10-05 - Documentation refresh and format verification
Rewrote `README.md`, `Architecture.md`, `Project_Requirements.md`, `LOCAL_SETUP.md` and
this file against `747d43a`. Ran the upload path against all six legacy formats with one
identical three-row set - all six parse correctly (section 7). Mapped the CPSE provenance
evidence chain. Recorded the three upload/provisioning defects in section 8 and the seven
documentation corrections in section 9.

## 11. Do Not Regress

- No automated approval path, at any confidence.
- Five-component score shape; weights inside the asserted constraints.
- Score before gates; gates only downgrade.
- Critical canonical specs never invented, averaged or majority-voted.
- Source CPSE codes always preserved; NMC is additive.
- Milvus failure degrades candidate count, never decision quality, and never silently.
- Provenance is evidence-based; no CPSE guessing.
- Large/local-only datasets stay out of Git; `.env` is never committed.

## 12. Open

1. Sign-off on C3 (CONFLICT -> DIFFERENT vs REVIEW).
2. Blind evaluation on HELD-OUT and HARD-NEGATIVES, B1/B2 go/no-go, signed-off metrics.
3. Test isolation (`conftest.py` + a throwaway database).
4. Idempotent re-upload and a 400 instead of 500 on format mismatch.
5. Fix the `MIRA_MODEL_AUTO_DOWNLOAD` string in the error message.
6. Deployment packaging and air-gapped model provisioning guidance.
7. ERP adapter boundary against a real SAP/OData endpoint.
8. Production hardening: `secret_key`, seeded demo passwords, CORS (currently `*`).
9. CNMC namespace policy sign-off - who allocates the global id in a multi-agency
   deployment.
