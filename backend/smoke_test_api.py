"""MIRA Backend - full API smoke test (every endpoint, in dependency order).

Usage:
    python smoke_test_api.py [BASE_URL]

Defaults to http://127.0.0.1:8000. Exercises all endpoints including
negative cases (401/400/404/409) and prints a PASS/FAIL table.

Self-contained: the sample CSVs are embedded below and written to
sample_data/ automatically on first run. Safe to re-run against the same
DB (existing test user is tolerated); for a pristine result set run it
against a fresh database.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
DATA = Path(__file__).parent / "sample_data"

IOCL_CSV = """material_code,description,uom,category,specifications,last_purchase_price,avg_annual_quantity
IOCL-1001,"Deep groove ball bearing 6205 ZZ C3, SKF make",NOS,Bearing,"ID 25mm, OD 52mm, Width 15mm, chrome steel",850,120
IOCL-1002,"Gate valve 150mm class 150 carbon steel flanged",NOS,Valve,"DN 150, PN 16, WCB body, rising stem",18500,24
IOCL-1003,"Hex bolt M12x60 grade 8.8 zinc plated",NOS,Fasteners,"IS 1364, full thread",45,5000
IOCL-1004,"MS pipe 50mm NB schedule 40 seamless",MTR,Pipes,"DN 50, ASTM A106 Gr B",620,300
IOCL-1005,"Induction motor 5HP 3-phase 1440 RPM TEFC",NOS,Electrical,"415V, IE3, B3 mounting, frame 112M",14200,15
"""

BPCL_CSV = """material_code,description,uom,category,specifications,last_purchase_price,avg_annual_quantity
BPCL-2001,"Ball bearing 6205 ZZ C3 deep groove SKF",NOS,Bearing,"ID 25 mm OD 52 mm, chrome steel",910,150
BPCL-2002,"Gate valve DN 150 #150 CS flanged WCB body",NOS,Valve,"Class 150, PN 20, rising stem",19800,30
BPCL-2003,"Hex head bolt M12x60 Gr 8.8 zinc plated",NOS,Fasteners,"IS 1364-1, zinc plated",48,6000
BPCL-2004,"Seamless MS pipe DN50 SCH 40 ASTM A106 GrB",MTR,Pipes,"50mm NB",650,250
BPCL-2005,"3-phase induction motor 3.7 kW 1440 rpm TEFC IE3",NOS,Electrical,"415V B3 frame 112M",13900,18
"""


def ensure_sample_data() -> None:
    """Write the embedded sample CSVs if they are not present yet."""
    DATA.mkdir(exist_ok=True)
    for fname, content in [("iocl_materials.csv", IOCL_CSV), ("bpcl_materials.csv", BPCL_CSV)]:
        target = DATA / fname
        if not target.exists():
            target.write_text(content, encoding="utf-8")
            print(f"Created {target}")

RESULTS: list[dict] = []
TOKEN: str | None = None


def record(name: str, method: str, url: str, expected, resp: httpx.Response, extra: str = "") -> bool:
    ok = resp.status_code in (expected if isinstance(expected, (list, tuple, set)) else [expected])
    body_preview = ""
    try:
        body_preview = json.dumps(resp.json())[:160]
    except Exception:
        body_preview = resp.text[:160].replace("\n", " ")
    RESULTS.append({
        "name": name, "method": method, "url": url,
        "expected": expected, "actual": resp.status_code,
        "ok": ok, "extra": extra, "body": body_preview,
    })
    flag = "PASS" if ok else "FAIL"
    print(f"[{flag}] {name:<52} {method} {url} -> {resp.status_code} (want {expected}) {extra}")
    if not ok:
        print(f"       body: {body_preview}")
    return ok


def main() -> int:
    global TOKEN
    ensure_sample_data()
    client = httpx.Client(base_url=BASE, timeout=120)

    # ---------------------------------------------------------------- meta
    r = client.get("/");                 record("root", "GET", "/", 200, r)
    r = client.get("/health");           record("health", "GET", "/health", 200, r)

    # ---------------------------------------------------------------- auth
    r = client.post("/api/v1/auth/login", json={"email": "admin@mira.gov.in", "password": "wrong"})
    record("auth/login wrong password -> 401", "POST", "/api/v1/auth/login", 401, r)

    r = client.get("/api/v1/auth/me")
    record("auth/me without token -> 401", "GET", "/api/v1/auth/me", 401, r)

    r = client.post("/api/v1/auth/login", json={"email": "admin@mira.gov.in", "password": "Admin@123"})
    if record("auth/login (admin)", "POST", "/api/v1/auth/login", 200, r):
        TOKEN = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {TOKEN}"}

    r = client.get("/api/v1/auth/me", headers=headers)
    record("auth/me", "GET", "/api/v1/auth/me", 200, r)

    r = client.post("/api/v1/auth/refresh", json={"access_token": TOKEN}, headers=headers)
    record("auth/refresh", "POST", "/api/v1/auth/refresh", 200, r)

    # ---------------------------------------------------------------- users
    r = client.get("/api/v1/users", headers=headers)
    record("users list", "GET", "/api/v1/users", 200, r)

    r = client.post("/api/v1/users", headers=headers, json={
        "email": "reviewer.test@mira.gov.in", "password": "Reviewer@123",
        "full_name": "Test Reviewer", "role": "reviewer", "cpse_id": 1,
    })
    new_user_id = None
    if record("users create (reviewer)", "POST", "/api/v1/users", [201, 409], r,
              extra="(409 = already exists from a previous run, OK)"):
        if r.status_code == 201:
            new_user_id = r.json()["id"]
        else:
            # Re-run on a dirty DB: reuse the existing user for the PUT/DELETE checks.
            rr = client.get("/api/v1/users", headers=headers,
                            params={"page_size": 200})
            if rr.status_code == 200:
                for u in rr.json()["items"]:
                    if u["email"] == "reviewer.test@mira.gov.in":
                        new_user_id = u["id"]
                        break

    if new_user_id:
        r = client.put(f"/api/v1/users/{new_user_id}", headers=headers,
                       json={"full_name": "Test Reviewer (updated)", "role": "data_steward"})
        record("users update", "PUT", f"/api/v1/users/{new_user_id}", 200, r)

        r = client.delete(f"/api/v1/users/{new_user_id}", headers=headers)
        record("users deactivate", "DELETE", f"/api/v1/users/{new_user_id}", 200, r)

    # ---------------------------------------------------------------- ingestion
    uploads: dict[str, dict] = {}
    for cpse_id, fname in [(1, "iocl_materials.csv"), (2, "bpcl_materials.csv")]:
        with open(DATA / fname, "rb") as fh:
            r = client.post("/api/v1/ingestion/upload", headers=headers,
                            files={"file": (fname, fh, "text/csv")}, data={"cpse_id": str(cpse_id)})
        if record(f"ingestion/upload {fname} (cpse {cpse_id})", "POST", "/api/v1/ingestion/upload", 200, r):
            uploads[fname] = r.json()
            print(f"       -> {json.dumps(r.json())[:220]}")

    r = client.post("/api/v1/ingestion/upload", headers=headers,
                    files={"file": ("bad.txt", b"hello", "text/plain")}, data={"cpse_id": "1"})
    record("ingestion/upload bad file type -> 400", "POST", "/api/v1/ingestion/upload", 400, r)

    r = client.get("/api/v1/ingestion/history", headers=headers)
    record("ingestion/history", "GET", "/api/v1/ingestion/history", 200, r)

    batch_id = next(iter(uploads.values()), {}).get("batch_id") or 1
    r = client.get(f"/api/v1/ingestion/quality-report/{batch_id}", headers=headers)
    record("ingestion/quality-report", "GET", f"/api/v1/ingestion/quality-report/{batch_id}", 200, r)

    r = client.get("/api/v1/ingestion/quality-report/99999", headers=headers)
    record("ingestion/quality-report 404", "GET", "/api/v1/ingestion/quality-report/99999", 404, r)

    r = client.get("/api/v1/ingestion/materials", headers=headers, params={"page": 1, "page_size": 50})
    material_ids: list[int] = []
    if record("ingestion/materials", "GET", "/api/v1/ingestion/materials", 200, r):
        material_ids = [m["id"] for m in r.json()["items"]]

    # ---------------------------------------------------------------- matching
    r = client.post("/api/v1/matching/run", headers=headers, json={})
    if record("matching/run (all materials)", "POST", "/api/v1/matching/run", 200, r):
        print(f"       -> {json.dumps(r.json())}")

    r = client.get("/api/v1/matching/suggestions", headers=headers,
                   params={"status": "pending", "page_size": 100})
    suggestions: list[dict] = []
    if record("matching/suggestions", "GET", "/api/v1/matching/suggestions", 200, r):
        suggestions = r.json()["items"]
        print(f"       -> total={r.json()['total']} counts={r.json()['counts']}")

    if suggestions:
        sid = suggestions[0]["id"]
        r = client.get(f"/api/v1/matching/suggestions/{sid}", headers=headers)
        record("matching/suggestions/{id} detail", "GET", f"/api/v1/matching/suggestions/{sid}", 200, r)
    r = client.get("/api/v1/matching/suggestions/999999", headers=headers)
    record("matching/suggestions 404", "GET", "/api/v1/matching/suggestions/999999", 404, r)

    r = client.post("/api/v1/matching/bulk-match", headers=headers, json={})
    record("matching/bulk-match without ids -> 400", "POST", "/api/v1/matching/bulk-match", 400, r)

    if material_ids:
        r = client.post("/api/v1/matching/bulk-match", headers=headers,
                        json={"material_ids": material_ids[:2], "include_same_cpse": False})
        record("matching/bulk-match (explicit ids)", "POST", "/api/v1/matching/bulk-match", 200, r)

    # ---------------------------------------------------------------- review
    r = client.get("/api/v1/review/queue", headers=headers, params={"page_size": 100})
    queue: list[dict] = []
    if record("review/queue", "GET", "/api/v1/review/queue", 200, r):
        queue = r.json()["items"]

    reviewed: list[int] = []
    if queue:
        mid = queue[0]["id"]
        r = client.post(f"/api/v1/review/approve/{mid}", headers=headers,
                        json={"reason": "Confirmed identical part by specs"})
        if record("review/approve", "POST", f"/api/v1/review/approve/{mid}", 200, r):
            print(f"       -> {json.dumps(r.json())[:220]}")
            reviewed.append(mid)

        r = client.post(f"/api/v1/review/approve/{mid}", headers=headers, json={})
        record("review/approve twice -> 409", "POST", f"/api/v1/review/approve/{mid}", 409, r)

    if len(queue) > 1:
        mid = queue[1]["id"]
        r = client.post(f"/api/v1/review/reject/{mid}", headers=headers,
                        json={"reason": "Different bore size"})
        record("review/reject", "POST", f"/api/v1/review/reject/{mid}", 200, r)
        reviewed.append(mid)

    remaining = [q["id"] for q in queue if q["id"] not in reviewed][:2]
    if remaining:
        r = client.post("/api/v1/review/bulk-approve", headers=headers,
                        json={"match_ids": remaining, "reason": "Bulk verify"})
        record("review/bulk-approve", "POST", "/api/v1/review/bulk-approve", 200, r)

    # ---------------------------------------------------------------- cnmc
    r = client.get("/api/v1/cnmc", headers=headers, params={"page_size": 50})
    cnmc_ids: list[int] = []
    if record("cnmc registry", "GET", "/api/v1/cnmc", 200, r):
        cnmc_ids = [c["id"] for c in r.json()["items"]]
        print(f"       -> total={r.json()['total']}")

    if cnmc_ids:
        cid = cnmc_ids[0]
        r = client.get(f"/api/v1/cnmc/{cid}", headers=headers)
        record("cnmc detail", "GET", f"/api/v1/cnmc/{cid}", 200, r)

        r = client.put(f"/api/v1/cnmc/{cid}", headers=headers,
                       json={"standardized_description": "Deep groove ball bearing 6205 ZZ C3 (national standard)",
                             "unspsc_code": "31171504"})
        record("cnmc update", "PUT", f"/api/v1/cnmc/{cid}", 200, r)
    r = client.get("/api/v1/cnmc/999999", headers=headers)
    record("cnmc detail 404", "GET", "/api/v1/cnmc/999999", 404, r)

    # manual cluster generation: pick two materials that are not mapped yet
    unmapped: list[int] = []
    for mid in material_ids:
        if len(unmapped) == 2:
            break
        rr = client.get(f"/api/v1/mapping/material/{mid}", headers=headers)
        if rr.status_code == 200 and not rr.json().get("mapped"):
            unmapped.append(mid)
    if len(unmapped) == 2:
        r = client.post("/api/v1/cnmc/generate", headers=headers,
                        json={"material_ids": unmapped, "reason": "Manual cluster test"})
        if record("cnmc/generate (manual cluster)", "POST", "/api/v1/cnmc/generate", 200, r):
            print(f"       -> {json.dumps(r.json())[:220]}")
    r = client.post("/api/v1/cnmc/generate", headers=headers,
                    json={"material_ids": material_ids[:1] if material_ids else []})
    record("cnmc/generate <2 materials -> 400/422", "POST", "/api/v1/cnmc/generate", (400, 422), r)

    # ---------------------------------------------------------------- mapping
    r = client.get("/api/v1/mapping/cpse/1", headers=headers)
    record("mapping/cpse/1", "GET", "/api/v1/mapping/cpse/1", 200, r)

    mapped_material = None
    if material_ids:
        for mid in material_ids:
            r = client.get(f"/api/v1/mapping/material/{mid}", headers=headers)
            if record("mapping/material/{id}", "GET", f"/api/v1/mapping/material/{mid}", 200, r):
                if r.json().get("mapped"):
                    mapped_material = mid
                    break
    r = client.get("/api/v1/mapping/material/999999", headers=headers)
    record("mapping/material 404", "GET", "/api/v1/mapping/material/999999", 404, r)

    if cnmc_ids and material_ids:
        # map some still-unmapped material to the first CNMC
        target = None
        for mid in material_ids:
            rr = client.get(f"/api/v1/mapping/material/{mid}", headers=headers)
            if rr.status_code == 200 and not rr.json().get("mapped"):
                target = mid
                break
        if target:
            r = client.post("/api/v1/mapping/create", headers=headers,
                            json={"material_id": target, "cnmc_id": cnmc_ids[0], "confidence_score": 95.0})
            record("mapping/create", "POST", "/api/v1/mapping/create", 200, r)

    r = client.get("/api/v1/mapping/migration-status", headers=headers)
    record("mapping/migration-status", "GET", "/api/v1/mapping/migration-status", 200, r)

    # ---------------------------------------------------------------- dashboard
    for path in ["/api/v1/dashboard/stats", "/api/v1/dashboard/trends?days=30",
                 "/api/v1/dashboard/category-heatmap", "/api/v1/dashboard/cpse-comparison"]:
        r = client.get(path, headers=headers)
        record(f"dashboard {path.split('/')[-1].split('?')[0]}", "GET", path, 200, r)

    # ---------------------------------------------------------------- roi
    r = client.get("/api/v1/roi/savings", headers=headers)
    if record("roi/savings", "GET", "/api/v1/roi/savings", 200, r):
        print(f"       -> {json.dumps(r.json())[:220]}")
    r = client.get("/api/v1/roi/summary", headers=headers)
    record("roi/summary", "GET", "/api/v1/roi/summary", 200, r)

    # ---------------------------------------------------------------- audit
    r = client.get("/api/v1/audit/trail", headers=headers, params={"page_size": 100})
    if record("audit/trail", "GET", "/api/v1/audit/trail", 200, r):
        print(f"       -> total={r.json()['total']}")
    r = client.get("/api/v1/audit/verify", headers=headers)
    record("audit/verify (hash chain)", "GET", "/api/v1/audit/verify", 200, r)

    # ---------------------------------------------------------------- sap
    r = client.get("/api/v1/sap/status", headers=headers)
    record("sap/status", "GET", "/api/v1/sap/status", 200, r)

    r = client.post("/api/v1/sap/sync", headers=headers, json={"cpse_id": 3})
    record("sap/sync CPCL (simulated)", "POST", "/api/v1/sap/sync", 200, r)

    r = client.post("/api/v1/sap/push-cnmc", headers=headers, json={"cpse_id": 1})
    record("sap/push-cnmc cpse 1", "POST", "/api/v1/sap/push-cnmc", 200, r)

    # ---------------------------------------------------------------- logout
    r = client.post("/api/v1/auth/logout", headers=headers)
    record("auth/logout", "POST", "/api/v1/auth/logout", 200, r)

    # ---------------------------------------------------------------- summary
    passed = sum(1 for x in RESULTS if x["ok"])
    failed = [x for x in RESULTS if not x["ok"]]
    print("\n" + "=" * 72)
    print(f"TOTAL: {len(RESULTS)} checks | PASSED: {passed} | FAILED: {len(failed)}")
    for x in failed:
        print(f"  FAILED: {x['name']} -> {x['actual']} (want {x['expected']}) {x['body']}")
    with open("smoke_results.json", "w", encoding="utf-8") as fh:
        json.dump(RESULTS, fh, indent=2)
    print("Full log written to smoke_results.json")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
