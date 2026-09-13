-- ============================================================
-- MIRA - Full persistence schema
-- Every table mirrors the exact dict shape the existing route
-- code already produces, so persisting data requires ZERO
-- changes to how any route builds its records.
-- ============================================================

-- ------------------------------------------------------------
-- cpses / users / upload_batches
-- Not yet written to by any route (no auth, no batch-tracking
-- wired up yet) -- included now so the schema matches
-- DATABASE.pdf's target design and nothing has to be redone
-- later. Safe to leave empty until those features exist.
-- ------------------------------------------------------------
CREATE TABLE cpses (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    short_code VARCHAR(20) UNIQUE NOT NULL,
    sap_url VARCHAR(500),
    last_sync_at TIMESTAMP,
    last_sync_status VARCHAR(50),
    last_sync_error TEXT,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(50) NOT NULL,
    cpse_id INTEGER REFERENCES cpses(id),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE upload_batches (
    id SERIAL PRIMARY KEY,
    cpse_id INTEGER REFERENCES cpses(id),
    uploaded_by INTEGER REFERENCES users(id),
    filename VARCHAR(255),
    total_records INTEGER,
    data_quality_score INTEGER,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- materials
-- Mirrors the exact dict built in api/routes/materials.py's
-- upload_materials_csv(). Every key in that dict = one column.
-- ------------------------------------------------------------
CREATE TABLE materials (
    id BIGINT PRIMARY KEY, -- app assigns this itself, not SERIAL
    cpse VARCHAR(100) NOT NULL,
    material_code VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    normalized_description TEXT,
    category VARCHAR(200),
    unit VARCHAR(50),
    manufacturer VARCHAR(200),
    manufacturer_part_number VARCHAR(200),
    material_grade VARCHAR(200),
    dimensions JSONB,
    specifications JSONB,
    parsed_specifications JSONB,
    other_attributes JSONB,
    upload_batch_id INTEGER REFERENCES upload_batches(id),
    last_purchase_price DECIMAL(15, 2),
    avg_annual_quantity DECIMAL(15, 3),
    data_quality_score INTEGER,
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_materials_cpse ON materials (cpse);
CREATE INDEX idx_materials_category ON materials (category);
CREATE INDEX idx_materials_description_gin ON materials USING gin (to_tsvector('english', description));

-- ------------------------------------------------------------
-- match_suggestions
-- Mirrors the exact "candidate" dict built in
-- api/routes/matching.py's run_batch_matching(). This is
-- richer than DATABASE.pdf's original draft -- the real code
-- needs the FULL score breakdown + critical_checks +
-- engine_decision (separate from human review status), all of
-- which were missing from the original design doc. Fixed here.
-- ------------------------------------------------------------
CREATE TABLE match_suggestions (
    id BIGINT PRIMARY KEY, -- app assigns this itself, not SERIAL
    source_material_id BIGINT NOT NULL REFERENCES materials(id),
    target_material_id BIGINT NOT NULL REFERENCES materials(id),

    source_cpse VARCHAR(100),
    target_cpse VARCHAR(100),
    source_code VARCHAR(200),
    target_code VARCHAR(200),
    source_description TEXT,
    target_description TEXT,

    -- Full score breakdown as one JSONB blob, exactly matching
    -- calculate_match_score()'s output:
    -- {text_similarity, semantic_similarity, specification_similarity,
    --  material_grade_similarity, other_attributes_similarity, final_score}
    scores JSONB NOT NULL,

    -- List of {field, status, ...} objects from evaluate_critical_gates()
    critical_checks JSONB NOT NULL,

    engine_decision VARCHAR(50) NOT NULL, -- HIGH_CONFIDENCE | REVIEW | DIFFERENT
    review_status VARCHAR(50) NOT NULL, -- PENDING | APPROVED | REJECTED

    reviewer_id VARCHAR(200),
    reviewer_comments TEXT,
    reviewed_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_match_suggestions_decision ON match_suggestions (engine_decision);
CREATE INDEX idx_match_suggestions_review_status ON match_suggestions (review_status);

-- ------------------------------------------------------------
-- cnmc + mappings
-- mappings.py builds ONE record per NMC cluster with a NESTED
-- cpse_mappings list inside it. Rather than force that into a
-- rigid per-material join (which the route code doesn't
-- produce), the mappings table mirrors that exact nested shape
-- directly -- so mappings.py needs zero changes. cnmc is kept
-- as a lightweight companion table matching DATABASE.pdf's
-- intent, ready for later use once real NMC approval workflow
-- is built.
-- ------------------------------------------------------------
CREATE TABLE cnmc (
    id SERIAL PRIMARY KEY,
    cnmc_code VARCHAR(50) UNIQUE NOT NULL,
    standardized_description TEXT,
    category VARCHAR(100),
    unspsc_code VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_by INTEGER REFERENCES users(id)
);

CREATE TABLE mappings (
    id BIGINT PRIMARY KEY, -- app assigns this itself, not SERIAL
    nmc VARCHAR(50) NOT NULL,
    cpse_mappings JSONB NOT NULL, -- [{material_id, cpse, material_code, description, category, material_grade}, ...]
    cluster_size INTEGER NOT NULL,
    status VARCHAR(50) DEFAULT 'PROVISIONAL',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- feedback
-- Not yet written to by review.py directly (it stores reviewer
-- comments on the candidate itself), but kept ready per
-- DATABASE.pdf -- future training-data export can read from
-- here once wired up.
-- ------------------------------------------------------------
CREATE TABLE feedback (
    id BIGSERIAL PRIMARY KEY,
    match_suggestion_id BIGINT NOT NULL REFERENCES match_suggestions(id),
    reviewer_id VARCHAR(200) NOT NULL,
    action VARCHAR(20) NOT NULL,
    reason TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- audit_logs
-- Mirrors the exact event dict built in review.py's
-- AUDIT_EVENTS.append() call.
-- ------------------------------------------------------------
CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    candidate_id BIGINT,
    source_code VARCHAR(200),
    target_code VARCHAR(200),
    source_cpse VARCHAR(100),
    target_cpse VARCHAR(100),
    actor VARCHAR(200),
    comments TEXT,
    final_score DECIMAL(6, 4),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_logs_event_type ON audit_logs (event_type);
