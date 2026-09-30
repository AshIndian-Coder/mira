# Synthetic CPSE Material Master Dataset

This dataset is an **explicitly synthetic and anonymized benchmark dataset** engineered specifically for testing the end-to-end pipeline of **MIRA (AI-Driven Standardization and Harmonization of Material Codes Across CPSEs)**.

> [!NOTE]
> **Synthetic Nature**: All records in this dataset are synthetic and represent simulated industrial procurement and material master data across Indian CPSE organizations (NTPC, BHEL, IOCL, ONGC, GAIL, NALCO, SAIL, HPCL, BPCL, POWERGRID). No row contains proprietary or private production data.

---

## Dataset Summary Statistics

* **Total Records**: 172
* **Represented CPSEs (10)**:
  * IOCL: 26 records
  * NTPC: 22 records
  * BHEL: 22 records
  * ONGC: 20 records
  * GAIL: 18 records
  * HPCL: 18 records
  * BPCL: 16 records
  * NALCO: 14 records
  * SAIL: 12 records
  * POWERGRID: 4 records
* **Categories Represented**:
  * Fasteners: 48 records
  * Pipes, Tubes & Fittings: 32 records
  * Valves: 26 records
  * Electrical & Cables: 25 records
  * Bearings & Power Transmission: 18 records
  * Pressure & Process Instrumentation: 11 records
  * Welding & Consumables: 10 records
  * Pumps & Rotating Equipment: 7 records
  * Gaskets & Sealing Materials: 9 records
* **Ground Truth Test Pairs**: 95 explicit relationship assertions in `synthetic_material_master_manifest.json`.

---

## Controlled Test Distributions

1. **True Cross-CPSE Equivalents (~40%)**:
   - Multiple CPSE phrasings for identical materials (e.g. `HEX HEAD BOLT M8 X 25 MM SS304 GRADE A2-70` vs `BOLT, HEX, M8 × 25, SS304` vs `HEXAGONAL HEAD BOLT SS 304 M8X25MM`).
   - Verifies normalization, tokenization, semantic vector indexing, and critical gate approval (`HIGH_CONFIDENCE`).

2. **Hard Negatives & High-Similarity Traps (~25%)**:
   - Materials with very high lexical/embedding overlap where a critical technical specification differs (e.g. `M8x25` vs `M8x30`, `50NB SCH40` vs `50NB SCH80`, `2 IN Class 150` vs `2 IN Class 300`, `415V` vs `3.3KV`).
   - Tests MIRA's critical gates to ensure false positives are rejected (`DIFFERENT`).

3. **Specification Conflicts (~15%)**:
   - Isolated single-attribute variations across diameter, length, thread pitch, pipe schedule, material grade, voltage class, power, and pressure ratings.

4. **Ambiguous / Incomplete Records (~10%)**:
   - Truncated descriptions omitting critical attributes (e.g. `HEX HEAD BOLT SS304`, `PIPE 50NB SCH 40`, `PRESSURE GAUGE SS316`).
   - Verifies MIRA routes candidates to `UNKNOWN` / `REVIEW` rather than fabricating missing attributes.

5. **Messy Industrial Shorthand (~10%)**:
   - Inconsistent casing, punctuation, slashes, abbreviation forms (`VLV`, `PPL`, `BRG`, `CBL`, `SMLS`), and reordered specifications.

---

## File Structure

* [`synthetic_material_master.csv`](file:///home/shikhar/Desktop/mira/data/sample/synthetic_material_master.csv): CSV file ready for upload or batch ingestion.
* [`synthetic_material_master_manifest.json`](file:///home/shikhar/Desktop/mira/data/sample/synthetic_material_master_manifest.json): Machine-readable ground truth manifest of all test families and expected outcomes.
* [`generate_master_dataset.py`](file:///home/shikhar/Desktop/mira/data/sample/generate_master_dataset.py): Deterministic generator script.

---

## How to Import and Test in MIRA

### 1. Web UI Upload
1. Open MIRA UI in your browser (`http://localhost:5173/materials`).
2. Navigate to **Materials Master** $\rightarrow$ Click **Upload CSV**.
3. Select `data/sample/synthetic_material_master.csv`.
4. Run Matching from the **Matching** screen.

### 2. CLI / Backend Ingestion Validation
Run the Python validation script to verify parsing and critical gate behavior:
```bash
PYTHONPATH=backend backend/.venv/bin/python -c '
from app.services.ingestion.service import parse_legacy_file
from app.services.parsing.service import parse_specifications

with open("data/sample/synthetic_material_master.csv", "rb") as f:
    records = parse_legacy_file(f.read(), "synthetic_material_master.csv")
print(f"Successfully ingested {len(records)} records.")
'
```

### 3. Run Backend Regression Tests
```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/
```
