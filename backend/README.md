# MIRA — National Unified Material Master Framework (Backend)

AI-powered platform that standardizes, harmonizes and rationalizes material
master data across Central Public Sector Enterprises (CPSEs) under
**One Nation – One Material Code**.

This is the **backend** (FastAPI + PostgreSQL + Milvus + Qwen-1B-Embedding).
The scope of this repository is backend-only: no blockchain, no federated
learning, no knowledge graph — only what the file structure defines.

## Architecture

```
CPSE upload / SAP sync
        │
        ▼
ingestion ──► text_cleaner ──► abbreviation_expander ──► uom_normalizer
        │
        ▼
attribute_extractor (NER stage: type/size/grade/pressure/voltage/seal/standard)
        │
        ▼
Qwen-1B-Embedding (1536-dim, INT8) ──► Milvus material_embeddings
        │
        ▼
Hybrid matching  =  0.20·text + 0.20·semantic + 0.35·specification
                   + 0.15·material_grade + 0.10·other_attributes
        │  + deterministic critical gates (dimensions / pressure / voltage / grade)
        ▼
HIGH_CONFIDENCE (≥0.85, gates PASS) | REVIEW (0.45–0.85 or gate issue) | DIFFERENT (<0.45)
        │
        ▼
Human review (approve/reject + reason) ──► feedback table (active learning)
        │
        ▼
CNMC generation (CNMC-000001…) + UNSPSC/NIC taxonomy ──► mappings
        │
        ▼
Dashboard · ROI/savings calculator · Audit trail (SHA-256 hash chain) · SAP push
```

**Safety rule:** the AI model is a semantic component, never the final
authority. Equivalence is only established through human review; every
decision carries an Explainable AI payload and an audit entry.

## Quick start

```bash
# 1. Configure
cp .env.example .env            # then edit DATABASE_URL etc.

# 2. Create the database
createdb material_master        # or: psql -c "CREATE DATABASE material_master;"

# 3. Install
pip install -r requirements.txt

# 4. Run (tables auto-created, demo CPSEs + admin user auto-seeded)
uvicorn app.main:app --reload --port 8000
```

Open **http://localhost:8000/docs** for the Swagger UI.

Default login (change it in `.env`): `admin@mira.gov.in` / `Admin@123`

Docker:

```bash
docker build -t mira-backend .
docker run -p 8000:8000 --env-file .env mira-backend
```

## API overview (all under `/api/v1`)

| Area | Endpoints |
|---|---|
| **Auth** | `POST /auth/login` · `POST /auth/refresh` · `GET /auth/me` · `POST /auth/logout` |
| **Ingestion** | `POST /ingestion/upload` (CSV/Excel) · `GET /ingestion/history` · `GET /ingestion/quality-report/{id}` · `GET /ingestion/materials` |
| **Matching** | `POST /matching/run` · `POST /matching/bulk-match` · `GET /matching/suggestions` · `GET /matching/suggestions/{id}` |
| **Review** | `POST /review/approve/{id}` · `POST /review/reject/{id}` · `GET /review/queue` · `POST /review/bulk-approve` |
| **CNMC** | `GET /cnmc` · `GET /cnmc/{id}` · `POST /cnmc/generate` · `PUT /cnmc/{id}` |
| **Mapping** | `GET /mapping/cpse/{id}` · `GET /mapping/material/{id}` · `POST /mapping/create` · `GET /mapping/migration-status` |
| **Dashboard** | `GET /dashboard/stats` · `GET /dashboard/trends` · `GET /dashboard/category-heatmap` · `GET /dashboard/cpse-comparison` |
| **ROI** | `GET /roi/savings?cpse_ids=&category=&mode=` · `GET /roi/summary` |
| **Audit** | `GET /audit/trail` · `GET /audit/verify` (hash-chain integrity) |
| **SAP** | `GET /sap/status` · `POST /sap/sync` · `POST /sap/push-cnmc` |
| **Users** | `GET/POST /users` · `PUT/DELETE /users/{id}` (admin) |

### Roles (RBAC)

| Role | Can do |
|---|---|
| `admin` | everything, including user management |
| `data_steward` | upload data, run matching, generate CNMC, mappings, SAP sync |
| `reviewer` | approve/reject matches (review workflow) |
| `auditor` | view audit trail + integrity verification |

All roles can view dashboard / ROI / materials.

## Matching engine (MIRA spec)

Frozen weighted score (formula shape is frozen; weights tunable on DEV):

```
final = 0.20·text + 0.20·semantic + 0.35·specification
      + 0.15·material_grade + 0.10·other_attributes
```

Decision thresholds: `≥ 0.85` → HIGH_CONFIDENCE, `≥ 0.45` → REVIEW,
`< 0.45` → DIFFERENT. Critical gates override the score:

* FASTENER → material_grade + dimensions
* VALVE → pressure_rating + dimensions
* PIPE → pressure_rating + dimensions
* ELECTRICAL CONNECTOR → voltage_class + dimensions
* category mismatch / missing or conflicting critical field → REVIEW

Every suggestion stores the full Explainable AI payload
(`match_suggestions.explanation`) rendered by the frontend MatchCard.

## Vector store

Milvus collection `material_embeddings` (dim **1536**, locked to
Qwen-1B-Embedding). When Milvus is not reachable the backend
transparently falls back to an in-memory cosine store, and when
`torch/transformers` are not installed it falls back to a deterministic
hashing embedder — so the whole pipeline (and the test suite) runs on any
laptop. Set `EMBEDDING_BACKEND=auto|qwen|hashing` to control this.

## ML pipeline (offline)

```
app/ml_pipeline/
├── generate_synthetic_data.py   # Step 1: positive pairs (safe transforms only)
├── hard_negative_miner.py       # Step 2: same category, different critical spec
├── export_feedback.py           # Step 2b: DB feedback -> feedback_pairs.csv
├── train_qwen.py                # Step 3: contrastive fine-tune (dim 1536)
├── quantize_model.py            # Step 4: INT8 (~500MB -> ~125MB)
└── evaluate_model.py            # Step 5: baseline vs FT vs INT8, frozen split
```

Pair CSV format: `material_1_desc,material_2_desc,label` (1 = same material).

Accuracy rules enforced by `evaluate_model.py`:
1. fine-tuned full precision beats the untrained Qwen-1B-Embedding baseline;
2. INT8 retains ≥ 95% of the full-precision metric **and** still beats the
   baseline (the accuracy gain must survive quantization).

## Database

PostgreSQL tables: `users`, `cpses`, `materials`, `cnmc`, `mappings`,
`match_suggestions`, `feedback`, `audit_logs`, `upload_batches`.
Tables are auto-created on startup (`Base.metadata.create_all`) for
dev/demo; use Alembic for production migrations.

## Tests

```bash
python -m pytest tests/ -v
```

`tests/test_matching.py` covers the full matching stack (preprocessing,
NER extraction, fuzzy, attribute comparison, ensemble ranker + gates,
explainability, clustering, CNMC code generation, ROI math) without
requiring PostgreSQL, Milvus, or GPU — the engine's deterministic fallbacks
make it fully reproducible.

An end-to-end API smoke test (login → upload → matching → review → CNMC →
mapping → ROI → audit → SAP → RBAC checks) is available at
`scripts_e2e_demo.py` and runs against a scratch SQLite DB:

```bash
python3 scripts_e2e_demo.py
```

## Configuration

See `.env.example` — key settings:

* `DATABASE_URL`, `MILVUS_URI`, `EMBEDDING_BACKEND`, `QWEN_MODEL_PATH`
* matching weights & thresholds (frozen MIRA parameters)
* ROI assumptions (`BULK_DISCOUNT_RATE`, `CARRYING_COST_RATE`, `SAFETY_STOCK_DAYS`)
* `SAP_SIMULATE=true` for demo mode (deterministic sample data per CPSE)

