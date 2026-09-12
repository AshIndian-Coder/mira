# MIRA Backend — Run on Your Machine (Simple Guide)

Branch: `arena/01a095f9-mira` (has Postgres persistence).

## 0. Install these first (one time only)

| What | How to check | Where to get it |
|---|---|---|
| Python 3.11+ | `python --version` | https://www.python.org/downloads/ (Windows: tick "Add Python to PATH") |
| PostgreSQL 14+ | `psql --version` | https://www.postgresql.org/download/ — remember the `postgres` password you set! |
| Git | `git --version` | https://git-scm.com/downloads |

Mac alternative: `brew install postgresql@14` then `brew services start postgresql@14`.
Linux alternative: `sudo apt install postgresql`.

## 1. Download the code

```bash
git clone https://github.com/Lakshya-arch29/Mira.git
cd Mira
git checkout arena/01a095f9-mira
```

Already cloned before? Run this instead (inside `Mira`):

```bash
git fetch origin
git checkout arena/01a095f9-mira
git pull origin arena/01a095f9-mira
```

Verify you have the new files:

- Windows: `dir backend\app\db_adapter.py backend\mira_full_schema.sql`
- Mac/Linux: `ls backend/app/db_adapter.py backend/mira_full_schema.sql`

No "not found" error = good.

## 2. Database (SKIP if your DB + tables already exist)

a) Create empty database `mira`:

```bash
psql -U postgres -c "CREATE DATABASE mira;"
```

b) Create the 9 tables (run from inside the `Mira` folder):

```bash
psql -U postgres -d mira -f backend/mira_full_schema.sql
```

You should see `CREATE TABLE` lines and no errors.

## 3. Python setup (inside `Mira` folder)

```bash
cd backend
python -m venv .venv
```

Activate it:

- Windows: `.venv\Scripts\activate`
- Mac/Linux: `source .venv/bin/activate`

You should see `(.venv)` in your terminal. Then install (5–15 min, one time only):

```bash
pip install -r requirements.txt
```

> If you get `ERROR: No matching distribution found for torch==2.14.0+cpu`:
> the `+cpu` torch build lives on PyTorch's own server, not PyPI.
> Install torch first, then re-run the same command:
>
> ```bash
> pip install torch --index-url https://download.pytorch.org/whl/cpu
> pip install -r requirements.txt
> ```

## 4. Database password

The app default is `postgresql://postgres:postgres@localhost:5432/mira` (password = `postgres`).

- If your postgres password **is** `postgres` → skip, nothing to do.
- If different → create file `backend/.env` with one line:

```
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/mira
```

## 5. Start the server (in `backend`, with `(.venv)` active)

```bash
uvicorn app.main:app --reload
```

Leave this terminal open. Stop later with `Ctrl+C`.

## 6. Try it

1. Open http://127.0.0.1:8000 → "MIRA Backend — Service is running".
2. Open http://127.0.0.1:8000/docs → click through endpoints.
3. `POST /api/materials/upload` → upload this CSV (save as `materials.csv`):

```csv
cpse,material_code,description,category,unit,manufacturer,manufacturer_part_number,material_grade
NTPC,NTPC-V001,BALL VALVE 50MM SS316 PN16,Valves,NOS,Audco,AV-50,SS316
BHEL,BHEL-V002,BALL VALVE 50 MM SS 316 PN 16,Valves,NOS,Audco,AV-50,SS316
NALCO,NAL-V003,GATE VALVE 100MM CI PN10,Valves,NOS,Kirloskar,GV-100,CI
NTPC,NTPC-P010,MS PIPE 100MM DIA 6M,Pipes,MTR,SAIL,PIPE-100,MS
BHEL,BHEL-P011,M S PIPE 100 MM DIA 6 METER,Pipes,MTR,SAIL,PIPE-100,MS
```

4. `POST /api/matching/run-batch` → Execute (first run downloads the AI model ~90 MB, needs internet).
5. `GET /api/matching/candidates` → see results.
6. `POST /api/review/queue/1/action` with `{"action":"APPROVE","user_id":"you"}` → approve one.

## 7. The persistence test

1. Terminal: `Ctrl+C` (stop server). Start again: `uvicorn app.main:app --reload`.
2. `GET /api/materials` → data still there? ✅
3. `GET /api/matching/candidates/1` → still APPROVED? ✅

Both survive = persistence works.

## 8. If something goes wrong

| Error | Fix |
|---|---|
| `connection refused` | Postgres not running — start it |
| `password authentication failed` | Wrong password in `backend/.env` |
| `relation "materials" does not exist` | Schema not applied — do Step 2b |
| `No module named 'app'` / `'fastapi'` | Activate `.venv`, run from `backend` folder |
| Slow first matching run | Normal — downloading AI model once (needs internet) |
| `Port 8000 already in use` | Old server still running — close it or use `--port 8001` |
| `No matching distribution ... torch==2.14.0+cpu` | Install torch from PyTorch's index first (see note in Step 3) |
