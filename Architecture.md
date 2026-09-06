# SIH26099 — Architecture

## 1. System Flow

```text
CSV / CPSE Material Master
          ↓
       Ingestion
          ↓
Normalization + Unit Standardization
          ↓
Parser / Attribute Extraction
          ↓
Category / Blocking
          ↓
Candidate Pair Generation
          ↓
Hybrid Similarity Scoring
          ↓
Critical Specification Gates
          ↓
HIGH_CONFIDENCE / REVIEW / DIFFERENT
          ↓
Human Review
          ↓
Approved Relationships
          ↓
Clustering + Conflict Detection
          ↓
Common Material Record
          ↓
Common National Material Code / Common ID
          ↓
CPSE Code → Common-Code Mapping
          ↓
Audit Trail + Export/API
```

The gate does not skip scoring. `final_score` is always calculated first; the gate then controls classification.

Similarity proposes candidates; specifications and gates protect the final decision; humans control uncertain mappings.

## 2. Tech Stack

### Frontend
- React
- Vite
- TypeScript

### Backend
- Python
- FastAPI
- Pydantic

### Database
- PostgreSQL
- pgvector

### Matching
- Python
- RapidFuzz
- sentence-transformers
- NumPy
- pandas

### Parsing / Normalization
- Python regex/rules
- technical dictionaries
- unit normalization/conversion

### Development
- Git
- GitHub
- Docker optional

Embeddings are local for the MVP. No cloud embedding API is required.

## 3. Directory Structure

```text
sih26099/
├── README.md
├── Project_Requirements.md
├── Architecture.md
├── rules.md
├── Phases.md
├── memory.md
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── api/
│   │   │   ├── upload.py
│   │   │   ├── materials.py
│   │   │   ├── matches.py
│   │   │   ├── review.py
│   │   │   └── analytics.py
│   │   ├── models/
│   │   │   ├── material.py
│   │   │   ├── match_result.py
│   │   │   └── common_material.py
│   │   ├── services/
│   │   │   ├── ingestion.py
│   │   │   ├── normalization.py
│   │   │   ├── parser.py
│   │   │   ├── blocking.py
│   │   │   ├── matcher.py
│   │   │   ├── gates.py
│   │   │   ├── clustering.py
│   │   │   └── evaluation.py
│   │   └── schemas/
│   │       ├── material.py
│   │       ├── match.py
│   │       └── common_material.py
│   └── tests/
├── frontend/
│   └── src/
│       ├── components/
│       ├── pages/
│       ├── services/
│       ├── types/
│       └── App.tsx
├── data/
│   ├── sample/
│   ├── dev/
│   └── evaluation/
├── scripts/
│   ├── generate_synthetic.py
│   ├── prepare_real_data.py
│   └── run_evaluation.py
└── docs/
    ├── evaluation.md
    ├── data_sources.md
    └── demo.md
```

## 4. Frozen Integration Schemas

### Material Record

```json
{
  "source_org": "CPSE_A",
  "source_material_code": "MAT-00182",
  "description": "HEX BOLT M16 X 60 SS304",
  "category": "fastener",
  "attributes": {
    "material": "SS304",
    "grade": "A2-70",
    "diameter": "M16",
    "length": "60 mm",
    "pressure_rating": null,
    "voltage_class": null
  }
}
```

### Pairwise Match Result

```json
{
  "left_material_code": "MAT-00182",
  "right_material_code": "M-7742",
  "scores": {
    "text_similarity": 0.94,
    "semantic_similarity": 0.91,
    "specification_similarity": 1.00,
    "material_grade_similarity": 1.00,
    "other_attributes_similarity": 1.00,
    "final_score": 0.94
  },
  "critical_gates": {
    "grade": "MATCH",
    "dimensions": "MATCH"
  },
  "classification": "HIGH_CONFIDENCE"
}
```

The five component fields map one-to-one to the five frozen weighted components.

### Common Material Record

```json
{
  "common_material_id": "COMMON-00421",
  "common_national_material_code": null,
  "canonical": {
    "category": "fastener",
    "material": "SS304",
    "grade": "A2-70",
    "diameter": "M16",
    "length": "60 mm"
  },
  "mappings": [
    {
      "source_org": "CPSE_A",
      "source_material_code": "MAT-00182"
    },
    {
      "source_org": "CPSE_B",
      "source_material_code": "M-7742"
    }
  ],
  "status": "REVIEW"
}
```

The exact Common National Material Code format is not frozen.

Any UNKNOWN critical canonical field blocks APPROVED status.

## 5. Matching Pipeline

1. Normalize while retaining raw values.
2. Parse technical attributes using rules, regex, dictionaries and unit mappings.
3. Block by category and available identifying attributes.
4. Calculate lexical similarity.
5. Calculate local semantic similarity.
6. Compare structured specifications.
7. Calculate material/grade similarity.
8. Calculate other-attribute similarity.
9. Calculate the frozen weighted score.
10. Apply category-dependent critical gates.
11. Classify.
12. Send REVIEW cases to human review.
13. Record review decisions as audit events.
14. Build connected components from approved/high-confidence relationships.
15. Detect incompatible specifications or rejected internal relationships.
16. Create traceable Common Material Records.
17. Assign/recommend the common identifier/code according to the selected design.
18. Expose mappings through API/export for downstream ERP/SAP integration.

## 6. UNSPSC Position

UNSPSC can be used as a supporting classification or blocking feature if useful.

It is not required for the core matcher and must not become an architectural dependency. The system must remain operational when UNSPSC coverage is incomplete.

## 7. Scale Strategy

Track:

```text
reduction_ratio = 1 - (candidate_pairs / all_possible_pairs)
```

Model behavior at:
- 15,000 records;
- 150,000 records;
- 1.5 million records.

The MVP does not claim execution at these scales. At larger scale, category-first partitioning, index optimization, sharding, and distributed candidate generation may be required.

## 8. SAP / ERP Integration

The MVP provides integration-ready:
- REST APIs;
- structured mapping outputs;
- CSV/export formats suitable for downstream migration workflows.

A live SAP/ERP connection is not required for the MVP. The system must preserve the source CPSE code so mappings remain traceable during any later migration.

## 9. Security

- local embeddings;
- no cloud embedding requirement;
- no external LLM processing of source material data in the MVP;
- private evaluation labels;
- Dataset B restricted until evaluation;
- no secrets in Git.
