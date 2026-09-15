"""End-to-end API smoke test (run with a scratch SQLite DB; no Postgres needed).

Usage:
    cd backend && python3 tests/test_e2e_api.py
    # or: pytest tests/test_e2e_api.py -v
"""
import os
import sys
from pathlib import Path

# Make `app` importable when running as `python tests/test_e2e_api.py`
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Defaults to a scratch SQLite DB; point MIRA_E2E_DB at real Postgres, e.g.:
#   postgresql+psycopg2://postgres:postgres@localhost:5432/material_master
os.environ["DATABASE_URL"] = os.environ.get(
    "MIRA_E2E_DB", "sqlite:////tmp/mira_e2e.db"
)
os.environ["MILVUS_URI"] = "http://localhost:1"  # unreachable -> in-memory fallback
os.environ["EMBEDDING_BACKEND"] = "hashing"
if os.environ["DATABASE_URL"].startswith("sqlite"):
    if os.path.exists("/tmp/mira_e2e.db"):
        os.remove("/tmp/mira_e2e.db")
else:
    # fresh database each run for the Postgres target
    from sqlalchemy import create_engine, text

    _e = create_engine(os.environ["DATABASE_URL"])
    with _e.begin() as _c:
        for _t in (
            "feedback", "mappings", "match_suggestions", "materials",
            "audit_logs", "upload_batches", "cnmc", "users", "cpses",
        ):
            _c.execute(text(f"DROP TABLE IF EXISTS {_t} CASCADE"))
    _e.dispose()

import logging

logging.disable(logging.WARNING)

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

PASS = 0
FAIL = 0


def show(label, resp, keys=None, expect=200):
    global PASS, FAIL
    try:
        data = resp.json()
    except Exception:
        data = {}
    if keys and isinstance(data, dict):
        data = {k: data.get(k) for k in keys}
    ok = resp.status_code == expect
    PASS += ok
    FAIL += (not ok)
    print(f"{'PASS' if ok else 'FAIL'} {label}: {resp.status_code} {str(data)[:260]}")
    return data


def main():
    with TestClient(app) as client:
        show("health", client.get("/health"), ["status", "components"])

        r = client.post("/api/v1/auth/login", json={"email": "admin@mira.gov.in", "password": "Admin@123"})
        show("login", r, ["token_type", "expires_in"])
        H = {"Authorization": f"Bearer {r.json()['access_token']}"}
        show("me", client.get("/api/v1/auth/me", headers=H), ["id", "role"])
        show("create_reviewer", client.post("/api/v1/users", headers=H, json={
            "email": "reviewer@mira.gov.in", "password": "Review@123",
            "role": "reviewer", "cpse_id": 1}), ["id", "role"], expect=201)

        csv1 = (b"material_code,description,uom,category,last_purchase_price,avg_annual_quantity\n"
                b"IOCL-1001,BRG BALL 6205 2RS,NOS,Bearing,450,12000\n"
                b"IOCL-1002,VLV GATE 150NB CS PN16,NOS,Valve,8500,320\n"
                b"IOCL-1003,PIPE SCH40 2 INCH CS,MTR,Pipe,1850,4500\n")
        csv2 = (b"material_code,description,uom,category,last_purchase_price,avg_annual_quantity\n"
                b"BPCL-2001,BALL BEARING 6205 2RS SEALED,NOS,Bearing,410,9500\n"
                b"BPCL-2002,GATE VALVE 150MM CARBON STEEL PN16,NOS,Valve,8200,410\n"
                b"BPCL-2003,STEEL PIPE DN50 SCHEDULE 40,MTR,Pipe,1920,3800\n")
        show("upload_iocl", client.post("/api/v1/ingestion/upload", headers=H,
                                        data={"cpse_id": "1"}, files={"file": ("iocl.csv", csv1, "text/csv")}),
             ["upload_id", "inserted", "total_rows", "avg_quality_score", "embedding_indexed"])
        show("upload_bpcl", client.post("/api/v1/ingestion/upload", headers=H,
                                        data={"cpse_id": "2"}, files={"file": ("bpcl.csv", csv2, "text/csv")}),
             ["upload_id", "inserted", "total_rows"])
        show("quality_report", client.get("/api/v1/ingestion/quality-report/1", headers=H),
             ["upload_id", "avg_quality_score", "category_breakdown"])
        show("upload_history", client.get("/api/v1/ingestion/history", headers=H), ["total"])
        show("list_materials", client.get("/api/v1/ingestion/materials?cpse_id=1", headers=H), ["total"])

        run = show("run_matching", client.post("/api/v1/matching/run", headers=H, json={}),
                   ["processed", "suggestions_created", "by_decision", "embedding_backend", "vector_backend"])
        assert run["suggestions_created"] > 0, "no suggestions created"

        sugg = show("suggestions_queue", client.get("/api/v1/matching/suggestions", headers=H), ["total"])
        items = client.get("/api/v1/matching/suggestions", headers=H).json()["items"]
        for it in items[:6]:
            print(f"   {it['material_1']['material_code']} <-> {it['material_2']['material_code']} "
                  f"conf={it['final_confidence']} decision={it['decision']}")
        detail = client.get(f"/api/v1/matching/suggestions/{items[0]['id']}", headers=H).json()
        print("   EAI summary:", detail["explanation"]["summary"][:150])
        print("   EAI reasons:", detail["explanation"]["reasons"][:3])

        top = max(items, key=lambda x: x["final_confidence"] or 0)
        show("approve_top", client.post(f"/api/v1/review/approve/{top['id']}", headers=H,
                                        json={"reason": "Same bearing"}),
             ["status", "cnmc_code", "mapping_ids", "message"])

        queue = client.get("/api/v1/review/queue", headers=H).json()["items"]
        if queue:
            show("reject_low", client.post(f"/api/v1/review/reject/{queue[-1]['id']}", headers=H,
                                           json={"reason": "Not equivalent"}), ["status", "message"])

        reg_resp = client.get("/api/v1/cnmc", headers=H)
        show("cnmc_registry", reg_resp, ["total"])
        reg = reg_resp.json()
        assert reg["total"] >= 1
        r = client.get(f"/api/v1/cnmc/{reg['items'][0]['id']}", headers=H)
        show("cnmc_detail", r, ["cnmc_code", "mapped_materials_count", "unspsc_code", "nic_code"])
        print("   mapped codes:", [m["material_code"] for m in r.json()["mapped_materials"]])

        pid1 = client.get("/api/v1/ingestion/materials?cpse_id=1&search=PIPE", headers=H).json()["items"][0]["id"]
        pid2 = client.get("/api/v1/ingestion/materials?cpse_id=2&search=PIPE", headers=H).json()["items"][0]["id"]
        show("cnmc_generate", client.post("/api/v1/cnmc/generate", headers=H,
                                          json={"material_ids": [pid1, pid2], "reason": "manual demo"}),
             ["cnmc_code", "mapped_materials_count"])
        show("cnmc_update", client.put(f"/api/v1/cnmc/{reg['items'][0]['id']}", headers=H,
                                       json={"category": "Bearing"}), ["category"])

        show("mappings_cpse1", client.get("/api/v1/mapping/cpse/1", headers=H), ["total"])
        show("material_mapped", client.get("/api/v1/mapping/material/1", headers=H), ["mapped", "cnmc_code"])
        # material 1 (bearing, IOCL) is still unmapped -> manual map works
        show("manual_mapping", client.post("/api/v1/mapping/create", headers=H,
                                           json={"material_id": 1, "cnmc_id": reg["items"][0]["id"]}),
             ["material_id", "cnmc_code", "mapping_type"])
        # mapping an already-mapped material to the SAME CNMC -> 409
        show("manual_mapping_duplicate", client.post("/api/v1/mapping/create", headers=H,
                                                     json={"material_id": 2, "cnmc_id": reg["items"][0]["id"]}),
             ["detail"], expect=409)
        show("migration_status", client.get("/api/v1/mapping/migration-status?cpse_id=1", headers=H),
             ["total_materials", "mapped_materials", "progress_percent"])

        show("stats", client.get("/api/v1/dashboard/stats", headers=H),
             ["total_materials", "pending_matches", "approved_matches", "rejected_matches",
              "duplicate_groups", "total_cnmc", "avg_data_quality"])
        show("trends", client.get("/api/v1/dashboard/trends?days=30", headers=H), ["days"])
        show("heatmap", client.get("/api/v1/dashboard/category-heatmap", headers=H), ["items"])
        show("cpse_comparison", client.get("/api/v1/dashboard/cpse-comparison", headers=H), ["items"])

        r = client.get("/api/v1/roi/savings", headers=H).json()
        show("roi_savings", client.get("/api/v1/roi/savings", headers=H), ["cluster_count"])
        print(f"   savings: {r['totals']['total_savings_inr']} | sku_reduction={r['totals']['sku_reduction']}")
        show("roi_potential", client.get("/api/v1/roi/savings?mode=potential", headers=H), ["cluster_count"])
        show("roi_summary", client.get("/api/v1/roi/summary", headers=H), ["realized", "potential"])

        r = client.get("/api/v1/audit/trail", headers=H).json()
        print("audit actions seen:", [i["action"] for i in r["items"]][:12])
        show("audit_trail", client.get("/api/v1/audit/trail?action=approve_match", headers=H), ["total"])
        show("audit_verify", client.get("/api/v1/audit/verify", headers=H), ["valid", "total"])

        show("sap_status", client.get("/api/v1/sap/status", headers=H), ["mode", "items"])
        show("sap_sync_cpse3", client.post("/api/v1/sap/sync", headers=H, json={"cpse_id": 3}), ["results"])
        show("sap_status_after", client.get("/api/v1/sap/status", headers=H), ["items"])
        show("sap_push", client.post("/api/v1/sap/push-cnmc", headers=H, json={"cpse_id": 1}),
             ["status", "count", "message"])

        # RBAC negative checks
        r2 = client.post("/api/v1/auth/login", json={"email": "reviewer@mira.gov.in", "password": "Review@123"})
        H2 = {"Authorization": f"Bearer {r2.json()['access_token']}"}
        show("rbac_reviewer_cannot_upload", client.post("/api/v1/ingestion/upload", headers=H2,
                                                        data={"cpse_id": "1"},
                                                        files={"file": ("x.csv", b"a,b\n1,2", "text/csv")}),
             ["detail"], expect=403)
        show("rbac_reviewer_cannot_audit", client.get("/api/v1/audit/trail", headers=H2), ["detail"], expect=403)
        show("rbac_reviewer_can_review_queue", client.get("/api/v1/review/queue", headers=H2), ["total"])
        show("rbac_anonymous_denied", client.get("/api/v1/dashboard/stats"), ["detail"], expect=401)

        routes = client.get("/openapi.json").json()["paths"]
        print(f"\nTotal API routes registered: {len(routes)}")

    print(f"\n=== E2E RESULT: {PASS} passed, {FAIL} failed ===")
    sys.exit(1 if FAIL else 0)


def test_e2e_api():
    """Pytest wrapper - runs the full 39-check E2E demo."""
    main()


if __name__ == "__main__":
    main()

