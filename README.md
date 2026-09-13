# MIRA

**Material Identity & Resolution Architecture — SIH26099: AI-Driven Standardization and Harmonization of Material Codes Across CPSEs.**

MIRA ingests heterogeneous CPSE material masters, finds duplicate / near-duplicate / equivalent materials with a hybrid AI + rules matcher, routes uncertain pairs to human reviewers, and produces traceable **Common National Material Codes (NMC)** with full audit and analytics. Source CPSE codes are always preserved — MIRA is a harmonization layer, never an ERP replacement.

> **Similarity finds the candidate. Specifications decide whether it is safe. Humans control the final mapping.**

## Quickstart (local run)

Full step-by-step guide: **[LOCAL_SETUP.md](LOCAL_SETUP.md)** (Windows-first, beginner-friendly).

Short version:

```bash
git clone https://github.com/Lakshya-arch29/Mira.git
cd Mira
# apply backend/mira_full_schema.sql to your Postgres database
cd backend
python -m venv .venv && .venv\Scripts\activate   # Windows (see guide for Mac/Linux)
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
# create backend/.env with DATABASE_URL if your postgres password isn't "postgres"
uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000 (landing page) and http://127.0.0.1:8000/docs (interactive API).

## API surface

| Area | Endpoints |
|---|---|
| Materials | `POST /api/materials/upload` · `GET /api/materials` · `GET /api/materials/stats` · `GET /api/materials/{id}` |
| Matching | `POST /api/matching/compare` · `POST /api/matching/run-batch` · `GET /api/matching/candidates` · `GET /api/matching/candidates/{id}` · `GET /api/matching/stats` |
| Review | `GET /api/review/queue` · `GET /api/review/queue/{id}` · `POST /api/review/queue/{id}/action` · `GET /api/review/summary` |
| Audit | `GET /api/audit` · `GET /api/audit/export` |
| Analytics | `GET /api/analytics/overview` · `/by-cpse` · `/categories` · `/scores` |
| Mappings | `GET /api/mappings` · `GET /api/mappings/{id}` · `POST /api/mappings/generate` · `GET /api/mappings/export/flat` |
| Meta | `GET /` (landing page) · `GET /health` |

## Persistence (PostgreSQL)

All runtime data is **Postgres-backed** — uploads, candidates, review decisions, mappings, and audit events survive server restarts.

- Schema: `backend/mira_full_schema.sql` (9 tables, mirrors the exact dict shapes the routes produce)
- Engine: `backend/app/db_adapter.py` — `PersistentList` (drop-in list replacement) + `DBRow` (dict with write-through on in-place mutation, so `candidate["review_status"] = "APPROVED"` persists)
- Stores: `backend/app/store.py` (`MATERIALS`, `CANDIDATES`), `MAPPINGS` in `mappings.py`, `AUDIT_EVENTS` in `audit.py`
- Route files needed **zero logic changes**; `materials.py`, `matching.py`, `review.py`, `analytics.py` are untouched by persistence
- Proof test: upload → restart → data still there; approve → restart → still approved

## Repository layout

```text
Mira/
├── backend/
│   ├── mira_full_schema.sql      # Postgres schema (9 tables)
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py               # FastAPI app + landing page
│   │   ├── store.py              # DB-backed shared stores
│   │   ├── db_adapter.py         # PersistentList / DBRow persistence engine
│   │   ├── core/                 # config, database engine
│   │   ├── api/routes/           # materials, matching, review, audit, analytics, mappings
│   │   ├── models/ · schemas/    # SQLAlchemy models + Pydantic schemas
│   │   └── services/             # normalization, parsing, blocking, matching,
│   │                             # ingestion (+adapters, LLM fallback), training, ...
│   └── tests/
├── frontend/                     # React + Vite + TypeScript
├── data/ · notebooks/ · scripts/ # datasets (mostly local-only), notebooks, helpers
├── LOCAL_SETUP.md                # local run guide
├── memory.md                     # project memory (decisions, status, latest updates)
├── Architecture.md               # system architecture (stack, AI design, API boundary)
├── Phases.md                     # 18-day implementation plan + current state
├── Project_Requirements.md · rules.md
└── README.md                     # this file
```

## Documentation index

- **[LOCAL_SETUP.md](LOCAL_SETUP.md)** — run the backend on your machine
- **[memory.md](memory.md)** — frozen decisions, team roles, backend/frontend status, latest updates
- **[Architecture.md](Architecture.md)** — system architecture (stack, AI design, API boundary)
- **[Phases.md](Phases.md)** — 18-day phased plan + current state
- **[Project_Requirements.md](Project_Requirements.md)** — SIH requirements · **[rules.md](rules.md)** — repo rules

## Status & contributing

- Working branch for persistence: `arena/01a095f9-mira` → PR #1 into `main`
- 18-day hard freeze — see the plan file for the day-by-day schedule
- Keep large/local datasets under `data/` out of Git; never commit `.env`
