"""MIRA Backend - ADVANCED API tests (RBAC, validation, filters, Excel).

Complements smoke_test_api.py (which only uses the admin token).
Covers:
  * RBAC 403 enforcement for reviewer / auditor / data_steward roles
  * Role-ALLOWED operations per role (positive RBAC)
  * Deactivated-user login rejection (403)
  * Request-validation errors (422/400) and 404s
  * Pagination + filter correctness (materials, suggestions, cnmc, audit)
  * Excel (.xlsx) upload built in-memory (no local files)

Usage:
    python test_advanced_api.py [BASE_URL]      (default http://127.0.0.1:8000)

Re-runnable: test users get unique timestamped emails each run and are
deactivated at the end.
"""
from __future__ import annotations

import io
import json
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
RESULTS: list[dict] = []
RUN_TAG = str(int(time.time()))  # unique per run


def record(name: str, method: str, url: str, expected, resp: httpx.Response, extra: str = "") -> bool:
    ok = resp.status_code in (expected if isinstance(expected, (list, tuple, set)) else [expected])
    try:
        body_preview = json.dumps(resp.json())[:150]
    except Exception:
        body_preview = resp.text[:150].replace("\n", " ")
    RESULTS.append({"name": name, "actual": resp.status_code, "expected": expected, "ok": ok})
    print(f"[{'PASS' if ok else 'FAIL'}] {name:<58} {method} {url} -> {resp.status_code} (want {expected}) {extra}")
    if not ok:
        print(f"       body: {body_preview}")
    return ok


def make_xlsx() -> bytes:
    """Build a small .xlsx in memory (openpyxl is in requirements.txt)."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["material_code", "description", "uom", "category", "last_purchase_price", "avg_annual_quantity"])
    ws.append(["NTPC-9001", "Deep groove ball bearing 6308 ZZ C3 SKF make", "NOS", "Bearing", 1450, 60])
    ws.append(["NTPC-9002", "Gate valve DN 200 class 150 CS flanged WCB", "NOS", "Valve", 32500, 8])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=120)

    # ---------- admin login ----------
    r = client.post("/api/v1/auth/login", json={"email": "admin@mira.gov.in", "password": "Admin@123"})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    ADMIN = {"Authorization": "Bearer " + r.json()["access_token"]}

    # ---------- create + login the three non-admin roles ----------
    tokens: dict[str, dict] = {}
    user_ids: dict[str, int] = {}
    for role in ("reviewer", "auditor", "data_steward"):
        email = f"{role}.{RUN_TAG}@mira.gov.in"
        r = client.post("/api/v1/users", headers=ADMIN, json={
            "email": email, "password": "TestPass@123", "full_name": f"Test {role}",
            "role": role, "cpse_id": 1,
        })
        assert r.status_code == 201, f"could not create {role}: {r.status_code} {r.text}"
        user_ids[role] = r.json()["id"]
        rl = client.post("/api/v1/auth/login", json={"email": email, "password": "TestPass@123"})
        assert rl.status_code == 200, f"could not login as {role}: {rl.status_code}"
        tokens[role] = {"Authorization": "Bearer " + rl.json()["access_token"]}
        print(f"[setup] {role} user id={user_ids[role]} logged in")

    REV, AUD, DS = tokens["reviewer"], tokens["auditor"], tokens["data_steward"]

    # ---------- RBAC: reviewer ----------
    r = client.post("/api/v1/users", headers=REV, json={"email": "x@y.z", "password": "whatever12", "role": "reviewer"})
    record("reviewer: create user -> 403 (manage_users=admin)", "POST", "/api/v1/users", 403, r)
    r = client.post("/api/v1/matching/run", headers=REV, json={})
    record("reviewer: run matching -> 403", "POST", "/api/v1/matching/run", 403, r)
    r = client.post("/api/v1/ingestion/upload", headers=REV,
                    files={"file": ("a.csv", b"material_code,description\nX,Y", "text/csv")}, data={"cpse_id": "1"})
    record("reviewer: upload data -> 403", "POST", "/api/v1/ingestion/upload", 403, r)
    r = client.get("/api/v1/audit/trail", headers=REV)
    record("reviewer: audit trail -> 403 (view_audit)", "GET", "/api/v1/audit/trail", 403, r)
    r = client.get("/api/v1/sap/status", headers=REV)
    record("reviewer: sap status -> 403 (view_sap)", "GET", "/api/v1/sap/status", 403, r)
    r = client.get("/api/v1/review/queue", headers=REV)
    record("reviewer: review queue -> 200 (view_matches)", "GET", "/api/v1/review/queue", 200, r)
    pending = r.json()["items"] if r.status_code == 200 else []
    r = client.post("/api/v1/cnmc/generate", headers=REV, json={"material_ids": [1, 2]})
    record("reviewer: cnmc generate -> 403", "POST", "/api/v1/cnmc/generate", 403, r)
    if pending:
        mid = pending[-1]["id"]  # last = lowest confidence; leave top ones for other tests
        r = client.post(f"/api/v1/review/approve/{mid}", headers=REV, json={"reason": "reviewer RBAC positive test"})
        record("reviewer: approve match -> 200 (POSITIVE RBAC)", "POST", f"/api/v1/review/approve/{mid}", 200, r)
    else:
        print("[skip] reviewer approve: no pending suggestions left")

    # ---------- RBAC: auditor ----------
    r = client.get("/api/v1/audit/trail", headers=AUD)
    record("auditor: audit trail -> 200 (POSITIVE RBAC)", "GET", "/api/v1/audit/trail", 200, r)
    r = client.get("/api/v1/audit/verify", headers=AUD)
    record("auditor: audit verify -> 200", "GET", "/api/v1/audit/verify", 200, r)
    r = client.get("/api/v1/sap/status", headers=AUD)
    record("auditor: sap status -> 200", "GET", "/api/v1/sap/status", 200, r)
    r = client.post("/api/v1/matching/run", headers=AUD, json={})
    record("auditor: run matching -> 403", "POST", "/api/v1/matching/run", 403, r)
    if pending:
        mid = pending[-2]["id"] if len(pending) > 1 else pending[-1]["id"]
        if mid != (pending[-1]["id"] if pending else None) or len(pending) == 1:
            pass
        r = client.post(f"/api/v1/review/approve/{mid}", headers=AUD, json={})
        record("auditor: approve match -> 403 (cannot review)", "POST", f"/api/v1/review/approve/{mid}", [403, 409], r,
               extra="(409 tolerated if the id was already reviewed above)")

    # ---------- RBAC: data_steward ----------
    r = client.post("/api/v1/matching/run", headers=DS, json={"limit": 5})
    record("data_steward: run matching -> 200 (POSITIVE RBAC)", "POST", "/api/v1/matching/run", 200, r)
    r = client.post("/api/v1/ingestion/upload", headers=DS,
                    files={"file": ("ntpc_excel_test.xlsx", make_xlsx(),
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                    data={"cpse_id": "5"})
    record("data_steward: EXCEL upload -> 200", "POST", "/api/v1/ingestion/upload", 200, r)
    r = client.post("/api/v1/users", headers=DS, json={"email": "x2@y.z", "password": "whatever12", "role": "reviewer"})
    record("data_steward: create user -> 403 (manage_users=admin)", "POST", "/api/v1/users", 403, r)
    if pending:
        mid = pending[-1]["id"]
        r = client.post(f"/api/v1/review/approve/{mid}", headers=DS, json={})
        record("data_steward: approve match -> 403/409 (cannot review)", "POST", f"/api/v1/review/approve/{mid}", [403, 409], r)

    # ---------- deactivated user cannot log in ----------
    r = client.delete(f"/api/v1/users/{user_ids['auditor']}", headers=ADMIN)
    record("admin: deactivate auditor", "DELETE", f"/api/v1/users/{user_ids['auditor']}", 200, r)
    r = client.post("/api/v1/auth/login", json={"email": f"auditor.{RUN_TAG}@mira.gov.in", "password": "TestPass@123"})
    record("deactivated user login -> 403", "POST", "/api/v1/auth/login", 403, r)

    # ---------- validation & 404s ----------
    r = client.post("/api/v1/users", headers=ADMIN, json={"email": "short@y.z", "password": "abc", "role": "reviewer"})
    record("user create: short password -> 422", "POST", "/api/v1/users", 422, r)
    r = client.post("/api/v1/users", headers=ADMIN, json={"email": "badrole@y.z", "password": "validPass12", "role": "superuser"})
    record("user create: invalid role -> 4xx (was 500 before fix)", "POST", "/api/v1/users", (400, 422), r)
    r = client.post("/api/v1/review/approve/999999", headers=ADMIN, json={})
    record("approve nonexistent -> 404", "POST", "/api/v1/review/approve/999999", 404, r)
    r = client.post("/api/v1/mapping/create", headers=ADMIN, json={"material_id": 999999, "cnmc_id": 1})
    record("mapping create: bad material -> 404", "POST", "/api/v1/mapping/create", 404, r)

    # ---------- pagination + filters ----------
    r = client.get("/api/v1/ingestion/materials", headers=ADMIN, params={"page": 1, "page_size": 2})
    if record("materials: page_size=2", "GET", "/api/v1/ingestion/materials", 200, r):
        d = r.json()
        ok = len(d["items"]) == 2 and d["total"] > 2
        print(f"       -> items={len(d['items'])} total={d['total']} {'OK' if ok else 'UNEXPECTED'}")
    r = client.get("/api/v1/matching/suggestions", headers=ADMIN,
                   params={"decision": "REVIEW", "min_confidence": 50, "page_size": 100})
    if record("suggestions: decision=REVIEW & min_confidence=50", "GET", "/api/v1/matching/suggestions", 200, r):
        d = r.json()
        bad = [i for i in d["items"] if i["decision"] != "REVIEW" or (i["final_confidence"] or 0) < 50]
        print(f"       -> total={d['total']} filter-violations={len(bad)}")
    r = client.get("/api/v1/cnmc", headers=ADMIN, params={"search": "CNMC-"})
    record("cnmc: search=CNMC-", "GET", "/api/v1/cnmc", 200, r)
    r = client.get("/api/v1/audit/trail", headers=ADMIN, params={"action": "approve_match"})
    if record("audit: action=approve_match filter", "GET", "/api/v1/audit/trail", 200, r):
        d = r.json()
        bad = [i for i in d["items"] if i["action"] != "approve_match"]
        print(f"       -> total={d['total']} filter-violations={len(bad)}")
    r = client.get("/api/v1/roi/savings", headers=ADMIN, params={"mode": "potential"})
    record("roi: mode=potential", "GET", "/api/v1/roi/savings", 200, r)
    r = client.get("/api/v1/roi/savings", headers=ADMIN, params={"mode": "ai_suggestions"})
    record("roi: bad mode -> 422", "GET", "/api/v1/roi/savings", 422, r)

    # ---------- cleanup: deactivate the test users ----------
    for role in ("reviewer", "data_steward"):
        client.delete(f"/api/v1/users/{user_ids[role]}", headers=ADMIN)
    print("[cleanup] test users deactivated")

    passed = sum(1 for x in RESULTS if x["ok"])
    failed = [x for x in RESULTS if not x["ok"]]
    print("\n" + "=" * 72)
    print(f"TOTAL: {len(RESULTS)} checks | PASSED: {passed} | FAILED: {len(failed)}")
    for x in failed:
        print(f"  FAILED: {x['name']} -> {x['actual']} (want {x['expected']})")
    try:
        with open("advanced_results.json", "w", encoding="utf-8") as fh:
            json.dump(RESULTS, fh, indent=2)
        print("Full log written to advanced_results.json")
    except OSError as exc:
        print(f"(could not write advanced_results.json: {exc})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
