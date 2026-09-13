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
 cpse_id INTEGER,
 is_active BOOLEAN DEFAULT TRUE,
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY (cpse_id) REFERENCES cpses(id)
);

CREATE TABLE materials (
 id BIGSERIAL PRIMARY KEY,
 cpse_id INTEGER NOT NULL,
 material_code VARCHAR(100) NOT NULL, 
 description TEXT NOT NULL,
 cleaned_description TEXT,
 attributes JSONB,
 category VARCHAR(100),
 uom VARCHAR(20),
 last_purchase_price DECIMAL(15,2),
 avg_annual_quantity DECIMAL(15,3),
 data_quality_score INTEGER,
 status VARCHAR(50) DEFAULT 'active',
 upload_batch_id INTEGER,
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY (cpse_id) REFERENCES cpses(id),
 UNIQUE (cpse_id, material_code)
);
CREATE INDEX idx_materials_description_gin ON materials USING gin(to_tsvector('english', description));
CREATE INDEX idx_materials_category ON materials(category);

CREATE TABLE upload_batches (
 id SERIAL PRIMARY KEY,
 cpse_id INTEGER NOT NULL,
 uploaded_by INTEGER NOT NULL,
 filename VARCHAR(255),
 total_records INTEGER,
 data_quality_score INTEGER,
 uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY (cpse_id) REFERENCES cpses(id),
 FOREIGN KEY (uploaded_by) REFERENCES users(id)
);
ALTER TABLE materials ADD FOREIGN KEY (upload_batch_id) REFERENCES upload_batches(id);

CREATE TABLE cnmc (
 id SERIAL PRIMARY KEY,
 cnmc_code VARCHAR(50) UNIQUE NOT NULL, 
 standardized_description TEXT NOT NULL,
 category VARCHAR(100),
 unspsc_code VARCHAR(20),
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 approved_by INTEGER,
 FOREIGN KEY (approved_by) REFERENCES users(id)
);

CREATE TABLE mappings (
 id BIGSERIAL PRIMARY KEY,
 material_id BIGINT NOT NULL,
 cnmc_id INTEGER NOT NULL,
 confidence_score DECIMAL(5,2),
 approved_by INTEGER,
 approved_at TIMESTAMP,
 status VARCHAR(50) DEFAULT 'active',
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY (material_id) REFERENCES materials(id),
 FOREIGN KEY (cnmc_id) REFERENCES cnmc(id),
 FOREIGN KEY (approved_by) REFERENCES users(id),
 UNIQUE (material_id, status)
);

CREATE TABLE match_suggestions (
 id BIGSERIAL PRIMARY KEY,
 material_1_id BIGINT NOT NULL,
 material_2_id BIGINT NOT NULL,
 text_similarity DECIMAL(5,2),
 semantic_similarity DECIMAL(5,2),
 specification_similarity DECIMAL(5,2),
 grade_similarity DECIMAL(5,2),
 other_attribute_similarity DECIMAL(5,2),
 final_score DECIMAL(5,2), 
 gate_status VARCHAR(20) NOT NULL,
 ai_decision VARCHAR(30) NOT NULL,
 explanation JSONB,
 review_status VARCHAR(50) DEFAULT 'pending',
 reviewed_by INTEGER,
 reviewed_at TIMESTAMP,
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY (material_1_id) REFERENCES materials(id),
 FOREIGN KEY (material_2_id) REFERENCES materials(id),
 FOREIGN KEY (reviewed_by) REFERENCES users(id)
);
CREATE INDEX idx_match_review_status ON match_suggestions(review_status);
CREATE INDEX idx_match_ai_decision ON match_suggestions(ai_decision);
CREATE INDEX idx_match_gate ON match_suggestions(gate_status);
CREATE INDEX idx_match_score ON match_suggestions(final_score DESC);

CREATE TABLE feedback (
 id BIGSERIAL PRIMARY KEY,
 match_suggestion_id BIGINT NOT NULL,
 reviewer_id INTEGER NOT NULL,
 action VARCHAR(20) NOT NULL,
 reason TEXT,
 timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY (match_suggestion_id) REFERENCES match_suggestions(id),
 FOREIGN KEY (reviewer_id) REFERENCES users(id)
);

CREATE TABLE audit_logs (
 id BIGSERIAL PRIMARY KEY,
 user_id INTEGER NOT NULL,
 action VARCHAR(100) NOT NULL, 
 entity_type VARCHAR(50),
 entity_id BIGINT,
 changes JSONB,
 timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY (user_id) REFERENCES users(id)
);
