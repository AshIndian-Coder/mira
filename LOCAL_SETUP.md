# MIRA — Local Setup from Scratch

**Audience:** an evaluator starting on a clean machine. Nothing is assumed to be installed.
**Platform:** Windows (PowerShell) first; macOS/Linux notes are given where they differ.
**Time:** about 30–45 minutes, most of it downloads. Add 5–10 minutes for the first model download.

> **Important expectation.** On the very first upload, MIRA fetches a 753 MB embedding
> model from Hugging Face and verifies it. The UI will sit on "Uploading…" for roughly
> 30–60 seconds (fast connection) while that happens. This is normal, it happens once
> per machine, and every later upload is fast. There is no GPU requirement.

---

## 0. What you need before you start

| Software | Version | Check with | Get it from |
|---|---|---|---|
| Git | any | `git --version` | https://git-scm.com/downloads |
| Python | 3.11 – 3.13 (3.13 verified) | `python --version` | https://www.python.org/downloads/ — on Windows tick **Add python.exe to PATH** |
| Node.js | **20.19+ or 22.12+** (the frontend uses Vite 8) | `node --version` | https://nodejs.org |
| PostgreSQL | 14 or newer (16/17 fine) | `psql --version` | https://www.postgresql.org/download/ — **remember the password you set for `postgres`** |
| Docker Desktop | any recent | `docker --version` | https://www.docker.com/products/docker-desktop/ — needed for the Milvus vector store |

Also needed:

- **~6 GB free disk space** (about 3 GB of Python packages, ~1.5 GB for the model, the rest for Docker images)
- **Internet access** for the package installs and the model download
- **Access to the repository** — it is private. Ask for a collaborator invite, or use the ZIP you were given.

Quick pre-flight (all four should print a version, no errors):

```powershell
git --version
python --version
node --version
psql --version
docker --version
```

---

## 1. Get the code

```powershell
cd "$env:USERPROFILE\Downloads"
git clone https://github.com/AshIndian-Coder/mira.git mira
cd mira
```

If you were given a ZIP instead, unzip it and `cd` into the folder — the rest of this guide is identical.

**Check it is the right code:**

```powershell
dir backend\mira_full_schema.sql, backend\app\main.py, frontend\package.json, data\sample, Original_company_records_no_synthetic.csv
```

All five must appear. If `mira_full_schema.sql` is missing, you have the wrong folder.

---

## 2. Database (PostgreSQL)

MIRA uses PostgreSQL as its system of record. The application does **not** create tables
itself — the schema must be applied once, before the first start.

### 2.1 Create the database

```powershell
psql -U postgres -c "CREATE DATABASE mira;"
```

It will prompt for the `postgres` password. Expected output: `CREATE DATABASE`.

> If you get `psql: command not found`, PostgreSQL's `bin` folder is not on your PATH.
> Either add it, or use the full path, e.g.
> `"C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -c "CREATE DATABASE mira;"`.

### 2.2 Apply the schema

Run this **from the repository root** (the folder containing `backend`):

```powershell
psql -U postgres -d mira -f backend/mira_full_schema.sql
```

Expected: a series of `CREATE TABLE` / `CREATE INDEX` lines and **no `ERROR`**.

### 2.3 Verify

```powershell
psql -U postgres -d mira -c "\dt"
```

You should see **9 tables**: `audit_logs`, `cnmc`, `cpses`, `feedback`, `mappings`,
`match_suggestions`, `materials`, `upload_batches`, `users`.

> No `CREATE EXTENSION` step is needed. MIRA does not use pgvector — vector search runs
> in Milvus (§3).

---

## 3. Milvus (vector search)

MIRA runs two candidate sources: deterministic blocking **and** a semantic nearest-neighbour
search over embeddings stored in Milvus. Milvus is what lets the system find pairs that
share no keyword, so it is a normal part of the stack — start it before you upload anything.

### 3.1 Start the containers

Docker Desktop must be running (wait for the whale icon to stop animating). Then, **from the `backend` folder**:

```powershell
cd backend
docker compose -f docker-compose.milvus.yml up -d
```

First run downloads three images (a few hundred MB). Then check:

```powershell
docker ps --format "{{.Names}}  {{.Status}}"
```

All three must be listed as `Up` (Milvus itself may show `(healthy)` after ~30 seconds):

| Container | Purpose |
|---|---|
| `milvus-etcd` | metadata store |
| `milvus-minio` | object storage for vectors |
| `milvus-standalone` | the vector database (host port **19530**) |

If one is missing, wait 20–30 seconds and check again — Milvus takes a moment to become healthy.

### 3.2 Create the collection (once)

```powershell
python create_milvus_collection.py
```

Expected: `Created collection 'material_embeddings' with dynamic dim=1024.`

This is safe to re-run — it skips creation if the collection already exists. **Do not**
pass `--recreate` later: that drops the collection and discards any vectors you have already uploaded.

---

## 4. Python environment

### 4.1 Create and activate a virtual environment

From the **`backend`** folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Your prompt should now start with `(.venv)`.

> If PowerShell refuses with *"running scripts is disabled on this system"*, run this once
> in the same window and try again:
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> ```

macOS/Linux alternative:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4.2 Install the packages

Install the CPU build of PyTorch **first** — the `+cpu` wheel lives on PyTorch's own server, not PyPI:

```powershell
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

Then everything else (5–15 minutes, one time only):

```powershell
pip install -r requirements.txt
```

Finally, the two packages the INT8 embedding model needs to load:

```powershell
pip install bitsandbytes accelerate
```

> If `pip install -r requirements.txt` stops with `No matching distribution found for torch==2.14.0+cpu`,
> it means torch was not installed in the previous step — install it, then re-run this command.

### 4.3 Verify the environment

```powershell
python -c "import fastapi, sqlalchemy, torch, sentence_transformers, pymilvus, bitsandbytes; print('dependencies OK')"
```

Must print `dependencies OK`.

---

## 5. Configuration

MIRA reads an optional `backend/.env` file. The only value you may need to change is the database URL.

**Default:** `postgresql://postgres:postgres@localhost:5432/mira`

- If your `postgres` password **is** `postgres` → nothing to do; skip to §6.
- If it is something else → create the 
