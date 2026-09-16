# MIRA Backend — API Testing Report

**Date:** 2026-09-16 · **Backend v1.0.0** · **Verified on:** Windows + PostgreSQL (user machine, port 8080) and Linux + PostgreSQL 17 (sandbox, port 8000)

## Summary

| Suite | Scope | Result |
|---|---|---|
| `pytest tests/test_matching.py` | Unit: preprocessing, NER, fuzzy/attribute matching, ranker, gates, CNMC, ROI, clustering, pipeline | **59/59 PASS** |
| `smoke_test_api.py` | All 41 API operations (38 paths) incl. negative cases, on fresh Postgres | **52/52 PASS** |
| `test_advanced_api.py` | RBAC (4 roles), validation, pagination/filters, Excel upload, deactivated-login | **29/29 PASS** |
| Schema verification | `schema_postgres.sql` applied on clean PostgreSQL 17 → 9 tables, 21 indexes, 0 errors; app boots + seeds on it | **PASS** |
| Formula audit | Frozen weighted score recomputed from stored components for all 65+ suggestions | **0 mismatches, 0 policy violations** |
| Dedup audit | SQL checks across multiple matching runs (sequential + concurrent) | **0 duplicate pairs, 0 reversed pairs, 0 duplicate materials** |

## Bugs found & fixed during testing

1. **RBAC gap — `GET /api/v1/sap/status`** ignored the `view_sap` permission (any logged-in role got 200).
   Fix: `routes_sap.py` → `Depends(require_permission("view_sap"))`. Verified: reviewer now 403.
2. **`POST /api/v1/users` invalid role → HTTP 500.** `UserCreate.validate_role` lacked the
   `@field_validator("role")` decorator; the route's manual call raised an uncaught `ValueError`.
   Fix: decorator added in `user_schema.py`; manual `payload.validate_role()` removed from
   `routes_users.py`. Verified: invalid role now returns a clean 422.
3. **(Historical, already fixed in this build)** "Values read twice" — duplicate match suggestions
   for the same pair. Guarded by app-level pair dedup + DB `UNIQUE INDEX uq_match_suggestions_pair`;
   verified a direct duplicate INSERT is rejected by Postgres.

## Environment notes

- `embedding_backend: hashing` (deterministic fallback) in both test environments — scores are
  reproducible; with Qwen active, similarity values will differ (expected).
- `vector_backend: in_memory` (Milvus not installed in either test env). The Milvus code path is
  **untested** — see gaps below.
- `SAP_SIMULATE=true` — simulated pulls/pushes only.

## Known gaps / not yet tested

1. **Milvus path** (`pymilvus`): collection auto-create, ANN search, upsert. Needs Milvus running +
   `pip install pymilvus`.
2. **Qwen embeddings** (torch + model weights): semantic scores will change vs hashing fallback.
3. **Live SAP RFC** (`SAP_SIMULATE=false`, pyrfc + NWRDK).
4. **Concurrent `POST /matching/run`**: second request fails with 500 (unique-index IntegrityError
   uncaught at app level). No data corruption — but consider catching `IntegrityError` in
   `_run_matching` and counting the pair as `suggestions_existing` for a graceful 200.
5. **JWT expiry** (only valid-token refresh tested) and **CORS** with the real frontend origin.
6. `GET /matching/suggestions` `counts` chips are computed per page, not globally (cosmetic UI quirk).

## Reproduction

```powershell
# fresh DB
psql -U postgres -c "DROP DATABASE IF EXISTS material_master;" -c "CREATE DATABASE material_master;"
# start app (auto-creates schema + seeds admin@mira.gov.in / Admin@123)
uvicorn app.main:app --reload --port 8080
# tests
python -m pytest tests/test_matching.py -q
python smoke_test_api.py http://127.0.0.1:8080
python test_advanced_api.py http://127.0.0.1:8080
```

## Files

- `smoke_test_api.py` — 52 checks, self-contained (embedded CSVs), re-runnable
- `test_advanced_api.py` — 29 checks, timestamped throwaway users, re-runnable
- `schema_postgres.sql` — authoritative Postgres DDL (supersedes DATABASE.pdf plan)
- `SWAGGER_TESTING_GUIDE.md` — manual endpoint walkthrough with payloads
