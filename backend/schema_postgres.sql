-- MIRA - PostgreSQL schema (generated from app ORM metadata; matches the code exactly)
-- Supersedes the DATABASE.pdf plan: adds all columns/indexes the app actually uses.
-- Usage:  psql -U postgres -d material_master -f schema_postgres.sql

CREATE TABLE cpses (
	id SERIAL NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	short_code VARCHAR(20) NOT NULL, 
	sap_url VARCHAR(500), 
	last_sync_at TIMESTAMP WITHOUT TIME ZONE, 
	last_sync_status VARCHAR(50), 
	last_sync_error TEXT, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (short_code)
);

CREATE TABLE users (
	id SERIAL NOT NULL, 
	email VARCHAR(255) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	full_name VARCHAR(255), 
	role VARCHAR(50) NOT NULL, 
	cpse_id INTEGER, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	last_login TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(cpse_id) REFERENCES cpses (id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE TABLE upload_batches (
	id SERIAL NOT NULL, 
	cpse_id INTEGER NOT NULL, 
	uploaded_by INTEGER NOT NULL, 
	filename VARCHAR(255), 
	file_size_bytes BIGINT, 
	total_records INTEGER, 
	successful_records INTEGER, 
	failed_records INTEGER, 
	data_quality_score INTEGER, 
	quality_report JSONB, 
	uploaded_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(cpse_id) REFERENCES cpses (id), 
	FOREIGN KEY(uploaded_by) REFERENCES users (id)
);
CREATE INDEX idx_upload_batches_cpse ON upload_batches (cpse_id);
CREATE INDEX idx_upload_batches_uploaded_by ON upload_batches (uploaded_by);

CREATE TABLE materials (
	id BIGSERIAL NOT NULL, 
	cpse_id INTEGER NOT NULL, 
	material_code VARCHAR(100) NOT NULL, 
	description TEXT NOT NULL, 
	cleaned_description TEXT, 
	attributes JSONB, 
	category VARCHAR(100), 
	uom VARCHAR(20), 
	uom_normalized VARCHAR(20), 
	specifications TEXT, 
	technical_details JSONB, 
	last_purchase_price NUMERIC(15, 2), 
	avg_annual_quantity NUMERIC(15, 3), 
	data_quality_score INTEGER, 
	status VARCHAR(50) NOT NULL, 
	upload_batch_id INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_materials_cpse_code UNIQUE (cpse_id, material_code), 
	FOREIGN KEY(cpse_id) REFERENCES cpses (id) ON DELETE CASCADE, 
	FOREIGN KEY(upload_batch_id) REFERENCES upload_batches (id) ON DELETE SET NULL
);
CREATE INDEX idx_materials_category ON materials (category);
CREATE INDEX idx_materials_cpse ON materials (cpse_id);
CREATE INDEX idx_materials_status ON materials (status);

CREATE TABLE cnmc (
	id SERIAL NOT NULL, 
	cnmc_code VARCHAR(50) NOT NULL, 
	standardized_description TEXT NOT NULL, 
	category VARCHAR(100), 
	unspsc_code VARCHAR(20), 
	nic_code VARCHAR(20), 
	technical_specs JSONB, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	approved_by INTEGER, 
	approved_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(approved_by) REFERENCES users (id)
);
CREATE INDEX idx_cnmc_category ON cnmc (category);
CREATE INDEX idx_cnmc_unspsc ON cnmc (unspsc_code);
CREATE UNIQUE INDEX ix_cnmc_cnmc_code ON cnmc (cnmc_code);

CREATE TABLE mappings (
	id BIGSERIAL NOT NULL, 
	material_id BIGINT NOT NULL, 
	cnmc_id INTEGER NOT NULL, 
	confidence_score NUMERIC(5, 2), 
	mapping_type VARCHAR(50), 
	approved_by INTEGER, 
	approved_at TIMESTAMP WITHOUT TIME ZONE, 
	status VARCHAR(50) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_mappings_material_status UNIQUE (material_id, status), 
	FOREIGN KEY(material_id) REFERENCES materials (id) ON DELETE CASCADE, 
	FOREIGN KEY(cnmc_id) REFERENCES cnmc (id) ON DELETE CASCADE, 
	FOREIGN KEY(approved_by) REFERENCES users (id)
);
CREATE INDEX idx_mappings_cnmc ON mappings (cnmc_id);
CREATE INDEX idx_mappings_status ON mappings (status);

CREATE TABLE match_suggestions (
	id BIGSERIAL NOT NULL, 
	material_1_id BIGINT NOT NULL, 
	material_2_id BIGINT NOT NULL, 
	semantic_similarity NUMERIC(5, 2), 
	fuzzy_similarity NUMERIC(5, 2), 
	attribute_similarity NUMERIC(5, 2), 
	final_confidence NUMERIC(5, 2), 
	explanation JSONB, 
	status VARCHAR(50) NOT NULL, 
	reviewed_by INTEGER, 
	reviewed_at TIMESTAMP WITHOUT TIME ZONE, 
	review_comments VARCHAR(500), 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(material_1_id) REFERENCES materials (id) ON DELETE CASCADE, 
	FOREIGN KEY(material_2_id) REFERENCES materials (id) ON DELETE CASCADE, 
	FOREIGN KEY(reviewed_by) REFERENCES users (id)
);
CREATE INDEX idx_match_suggestions_confidence ON match_suggestions (final_confidence);
CREATE INDEX idx_match_suggestions_created ON match_suggestions (created_at);
CREATE INDEX idx_match_suggestions_status ON match_suggestions (status);
CREATE UNIQUE INDEX uq_match_suggestions_pair ON match_suggestions (material_1_id, material_2_id);

CREATE TABLE feedback (
	id BIGSERIAL NOT NULL, 
	match_suggestion_id BIGINT NOT NULL, 
	reviewer_id INTEGER NOT NULL, 
	action VARCHAR(20) NOT NULL, 
	reason TEXT, 
	timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(match_suggestion_id) REFERENCES match_suggestions (id) ON DELETE CASCADE, 
	FOREIGN KEY(reviewer_id) REFERENCES users (id)
);
CREATE INDEX idx_feedback_match ON feedback (match_suggestion_id);
CREATE INDEX idx_feedback_reviewer ON feedback (reviewer_id);

CREATE TABLE audit_logs (
	id BIGSERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	action VARCHAR(100) NOT NULL, 
	entity_type VARCHAR(50), 
	entity_id BIGINT, 
	changes JSONB, 
	timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);
CREATE INDEX idx_audit_logs_action ON audit_logs (action);
CREATE INDEX idx_audit_logs_timestamp ON audit_logs (timestamp);
CREATE INDEX idx_audit_logs_user ON audit_logs (user_id);

-- Full-text search index from the database plan (PDF):
CREATE INDEX IF NOT EXISTS idx_materials_description_gin ON materials USING gin(to_tsvector('english', description));