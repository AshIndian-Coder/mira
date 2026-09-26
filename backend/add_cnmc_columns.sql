ALTER TABLE cnmc ADD COLUMN IF NOT EXISTS identity_hash VARCHAR(64) UNIQUE;
ALTER TABLE cnmc ADD COLUMN IF NOT EXISTS global_id INTEGER UNIQUE;
ALTER TABLE cnmc ADD COLUMN IF NOT EXISTS material_type VARCHAR(50);
ALTER TABLE cnmc ADD COLUMN IF NOT EXISTS canonical_material_record JSONB;

CREATE INDEX IF NOT EXISTS idx_cnmc_identity_hash ON cnmc (identity_hash);
CREATE INDEX IF NOT EXISTS idx_cnmc_global_id ON cnmc (global_id);

CREATE SEQUENCE IF NOT EXISTS cnmc_global_id_seq;
SELECT setval(
    'cnmc_global_id_seq',
    COALESCE((SELECT MAX(global_id) FROM cnmc), 1),
    (SELECT COUNT(*) > 0 FROM cnmc WHERE global_id IS NOT NULL)
);