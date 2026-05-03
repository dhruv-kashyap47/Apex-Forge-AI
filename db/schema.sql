-- ═══════════════════════════════════════════════════════════════════════════
-- ApexForge AI — PostgreSQL Schema
-- Version: 1.0.0  |  Engine: PostgreSQL 16 + pgvector
-- 
-- Tables:
--   departments        → source system registry
--   raw_records        → incoming records from each department (read-only overlay)
--   entities           → resolved UBID master records
--   entity_matches     → pairwise similarity edges (forms graph)
--   activity_events    → timestamped business signals
--   review_queue       → human-in-the-loop tasks
--   audit_log          → immutable decision provenance
--   users              → reviewer accounts
-- ═══════════════════════════════════════════════════════════════════════════

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;          -- pgvector: embedding similarity
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";    -- UUID generation
CREATE EXTENSION IF NOT EXISTS pg_trgm;        -- trigram fuzzy search

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. DEPARTMENTS — source system registry
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS departments (
    id            SERIAL PRIMARY KEY,
    code          VARCHAR(20)  UNIQUE NOT NULL,   -- e.g. GST, LABOUR, FACTORIES, KSPCB
    name          TEXT         NOT NULL,
    description   TEXT,
    created_at    TIMESTAMPTZ  DEFAULT NOW()
);

INSERT INTO departments (code, name, description) VALUES
    ('GST',       'GST Department',              'Goods and Services Tax registrations'),
    ('LABOUR',    'Labour Department',            'Labour license and compliance records'),
    ('FACTORIES', 'Factories Department',         'Factory registrations under Factories Act'),
    ('KSPCB',     'Karnataka State Pollution',    'Pollution control board consents')
ON CONFLICT (code) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. RAW_RECORDS — incoming records (simulates department exports)
--    These are NEVER  modified — pure overlay pattern
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw_records (
    id               UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    department_code  VARCHAR(20)  NOT NULL REFERENCES departments(code),
    external_id      TEXT         NOT NULL,          -- department's own PK
    business_name    TEXT         NOT NULL,
    normalized_name  TEXT,                            -- lowercase + stripped
    pan              VARCHAR(10),
    gstin            VARCHAR(15),
    address          TEXT,
    pin_code         VARCHAR(6),
    sector           TEXT,
    phone            TEXT,
    email            TEXT,
    registration_date DATE,
    status_raw       TEXT,                            -- raw status string from source
    extra_data       JSONB        DEFAULT '{}',       -- department-specific fields
    embedding        vector(384),                     -- sentence-transformer embedding
    ingested_at      TIMESTAMPTZ  DEFAULT NOW(),
    record_hash      TEXT         UNIQUE NOT NULL,    -- SHA256(dept+external_id+name) for idempotency

    CONSTRAINT raw_records_dept_ext_unique UNIQUE (department_code, external_id)
);

-- Indexes for blocking & search
CREATE INDEX IF NOT EXISTS idx_raw_records_pan         ON raw_records (pan) WHERE pan IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_raw_records_gstin       ON raw_records (gstin) WHERE gstin IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_raw_records_pin         ON raw_records (pin_code);
CREATE INDEX IF NOT EXISTS idx_raw_records_dept        ON raw_records (department_code);
CREATE INDEX IF NOT EXISTS idx_raw_records_name_trgm   ON raw_records USING GIN (normalized_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_raw_records_embedding   ON raw_records USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. ENTITIES — resolved master records (UBID holders)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS entities (
    ubid             UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    canonical_name   TEXT         NOT NULL,
    pan              VARCHAR(10),
    gstin            VARCHAR(15),
    pin_code         VARCHAR(6),
    address          TEXT,
    sector           TEXT,
    departments      TEXT[]       DEFAULT '{}',       -- which depts contributed
    record_count     INT          DEFAULT 1,
    confidence_score FLOAT        DEFAULT 1.0,        -- resolution confidence (0-1)
    vitality_status  VARCHAR(20)  DEFAULT 'UNKNOWN',  -- ACTIVE | DORMANT | CLOSED | UNKNOWN
    vitality_score   FLOAT        DEFAULT 0.5,        -- 0-1 vitality probability
    pulse_score      INT          DEFAULT 50,         -- 0-100 Vitality Pulse Score
    last_activity_at TIMESTAMPTZ,
    created_at       TIMESTAMPTZ  DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  DEFAULT NOW(),
    is_active        BOOLEAN      DEFAULT TRUE,       -- soft delete / archival

    CONSTRAINT vitality_status_check CHECK (vitality_status IN ('ACTIVE','DORMANT','CLOSED','UNKNOWN'))
);

CREATE INDEX IF NOT EXISTS idx_entities_pan        ON entities (pan) WHERE pan IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entities_gstin      ON entities (gstin) WHERE gstin IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entities_pin        ON entities (pin_code);
CREATE INDEX IF NOT EXISTS idx_entities_vitality   ON entities (vitality_status);
CREATE INDEX IF NOT EXISTS idx_entities_sector     ON entities (sector);
CREATE INDEX IF NOT EXISTS idx_entities_name_trgm  ON entities USING GIN (canonical_name gin_trgm_ops);

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. ENTITY_RECORD_MAP — links raw_records → entity (UBID)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS entity_record_map (
    id               SERIAL       PRIMARY KEY,
    ubid             UUID         NOT NULL REFERENCES entities(ubid) ON DELETE CASCADE,
    raw_record_id    UUID         NOT NULL REFERENCES raw_records(id) ON DELETE CASCADE,
    linked_at        TIMESTAMPTZ  DEFAULT NOW(),
    linked_by        TEXT         DEFAULT 'system',   -- 'system' | reviewer username
    link_confidence  FLOAT        DEFAULT 1.0,

    CONSTRAINT entity_record_map_unique UNIQUE (ubid, raw_record_id)
);

CREATE INDEX IF NOT EXISTS idx_erm_ubid   ON entity_record_map (ubid);
CREATE INDEX IF NOT EXISTS idx_erm_record ON entity_record_map (raw_record_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. ENTITY_MATCHES — pairwise similarity graph edges
--    This IS the graph — traversed with recursive CTEs
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS entity_matches (
    id                  SERIAL      PRIMARY KEY,
    record_a_id         UUID        NOT NULL REFERENCES raw_records(id),
    record_b_id         UUID        NOT NULL REFERENCES raw_records(id),

    -- individual signal scores
    pan_match           BOOLEAN     DEFAULT FALSE,
    gstin_match         BOOLEAN     DEFAULT FALSE,
    name_phonetic_score FLOAT       DEFAULT 0.0,   -- Double Metaphone similarity
    name_fuzzy_score    FLOAT       DEFAULT 0.0,   -- RapidFuzz token sort ratio
    embedding_score     FLOAT       DEFAULT 0.0,   -- cosine similarity (pgvector)
    pin_match           BOOLEAN     DEFAULT FALSE,
    address_score       FLOAT       DEFAULT 0.0,   -- fuzzy address match
    graph_boost         FLOAT       DEFAULT 0.0,   -- propagation from transitive matches

    -- composite
    confidence          FLOAT       NOT NULL,      -- final Bayesian ensemble score
    match_status        VARCHAR(20) DEFAULT 'PENDING',  -- PENDING|AUTO_LINKED|REVIEW|REJECTED

    explanation         JSONB       DEFAULT '{}',  -- AI-generated justification
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    reviewed_at         TIMESTAMPTZ,
    reviewed_by         TEXT,

    CONSTRAINT entity_matches_unique UNIQUE (record_a_id, record_b_id),
    CONSTRAINT match_status_check CHECK (match_status IN ('PENDING','AUTO_LINKED','REVIEW','REJECTED','MERGED','SPLIT'))
);

CREATE INDEX IF NOT EXISTS idx_matches_record_a    ON entity_matches (record_a_id);
CREATE INDEX IF NOT EXISTS idx_matches_record_b    ON entity_matches (record_b_id);
CREATE INDEX IF NOT EXISTS idx_matches_confidence  ON entity_matches (confidence DESC);
CREATE INDEX IF NOT EXISTS idx_matches_status      ON entity_matches (match_status);

-- ─────────────────────────────────────────────────────────────────────────────
-- 6. ACTIVITY_EVENTS — timestamped business signals (temporal engine input)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS activity_events (
    id              SERIAL       PRIMARY KEY,
    ubid            UUID         REFERENCES entities(ubid) ON DELETE SET NULL,
    raw_record_id   UUID         REFERENCES raw_records(id) ON DELETE SET NULL,
    department_code VARCHAR(20)  NOT NULL,
    event_type      TEXT         NOT NULL,    -- INSPECTION|RENEWAL|FILING|UTILITY|COMPLAINT|SHUTDOWN
    event_date      TIMESTAMPTZ  NOT NULL,
    signal_strength FLOAT        DEFAULT 1.0, -- 0-1 importance weight
    details         JSONB        DEFAULT '{}',
    created_at      TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_ubid        ON activity_events (ubid);
CREATE INDEX IF NOT EXISTS idx_events_date        ON activity_events (event_date DESC);
CREATE INDEX IF NOT EXISTS idx_events_type        ON activity_events (event_type);
CREATE INDEX IF NOT EXISTS idx_events_dept        ON activity_events (department_code);

-- ─────────────────────────────────────────────────────────────────────────────
-- 7. REVIEW_QUEUE — human-in-the-loop tasks
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS review_queue (
    id              SERIAL       PRIMARY KEY,
    match_id        INT          UNIQUE REFERENCES entity_matches(id) ON DELETE CASCADE,
    priority        INT          DEFAULT 5,     -- 1 (highest) to 10
    assigned_to     TEXT,
    status          VARCHAR(20)  DEFAULT 'PENDING',  -- PENDING|IN_REVIEW|DONE|ESCALATED
    created_at      TIMESTAMPTZ  DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,

    CONSTRAINT review_status_check CHECK (status IN ('PENDING','IN_REVIEW','DONE','ESCALATED'))
);

CREATE INDEX IF NOT EXISTS idx_review_status   ON review_queue (status);
CREATE INDEX IF NOT EXISTS idx_review_priority ON review_queue (priority ASC, created_at ASC);

-- ─────────────────────────────────────────────────────────────────────────────
-- 8. AUDIT_LOG — immutable decision provenance (append-only)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGSERIAL    PRIMARY KEY,
    event_type      TEXT         NOT NULL,     -- ENTITY_CREATED|MATCHED|LINKED|SPLIT|VITALITY_UPDATED|REVIEWER_DECISION
    entity_ubid     UUID,
    match_id        INT,
    actor           TEXT         DEFAULT 'system',
    action          TEXT         NOT NULL,
    before_state    JSONB,
    after_state     JSONB,
    confidence      FLOAT,
    justification   TEXT,
    ip_address      TEXT,
    session_id      TEXT,
    created_at      TIMESTAMPTZ  DEFAULT NOW()
);

-- audit_log is append-only: no UPDATE/DELETE permissions in production
CREATE INDEX IF NOT EXISTS idx_audit_entity    ON audit_log (entity_ubid);
CREATE INDEX IF NOT EXISTS idx_audit_created   ON audit_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_type      ON audit_log (event_type);
CREATE INDEX IF NOT EXISTS idx_audit_actor     ON audit_log (actor);

-- ─────────────────────────────────────────────────────────────────────────────
-- 9. USERS — reviewer accounts
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL       PRIMARY KEY,
    username        TEXT         UNIQUE NOT NULL,
    full_name       TEXT,
    role            VARCHAR(20)  DEFAULT 'reviewer',   -- admin|reviewer|viewer
    department_code VARCHAR(20),
    created_at      TIMESTAMPTZ  DEFAULT NOW(),
    last_login      TIMESTAMPTZ,
    is_active       BOOLEAN      DEFAULT TRUE
);

INSERT INTO users (username, full_name, role) VALUES
    ('admin',    'System Administrator', 'admin'),
    ('reviewer1','Priya Sharma',         'reviewer'),
    ('reviewer2','Rajan Nair',           'reviewer'),
    ('demo',     'Demo Officer',         'reviewer')
ON CONFLICT (username) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- 10. HELPER VIEWS
-- ─────────────────────────────────────────────────────────────────────────────

-- Entity enriched view (used by dashboard)
CREATE OR REPLACE VIEW v_entity_summary AS
SELECT
    e.ubid,
    e.canonical_name,
    e.pan,
    e.gstin,
    e.pin_code,
    e.sector,
    e.departments,
    e.record_count,
    e.confidence_score,
    e.vitality_status,
    e.vitality_score,
    e.pulse_score,
    e.last_activity_at,
    e.created_at,
    COUNT(DISTINCT ae.id) AS total_events,
    MAX(ae.event_date)    AS latest_event_date,
    COUNT(DISTINCT erm.raw_record_id) AS linked_records
FROM entities e
LEFT JOIN activity_events ae  ON ae.ubid = e.ubid
LEFT JOIN entity_record_map erm ON erm.ubid = e.ubid
WHERE e.is_active = TRUE
GROUP BY e.ubid;

-- Dashboard stats view
CREATE OR REPLACE VIEW v_dashboard_stats AS
SELECT
    COUNT(*)                                                    AS total_entities,
    COUNT(*) FILTER (WHERE vitality_status = 'ACTIVE')         AS active_count,
    COUNT(*) FILTER (WHERE vitality_status = 'DORMANT')        AS dormant_count,
    COUNT(*) FILTER (WHERE vitality_status = 'CLOSED')         AS closed_count,
    COUNT(*) FILTER (WHERE vitality_status = 'UNKNOWN')        AS unknown_count,
    ROUND(AVG(confidence_score)::NUMERIC, 3)                   AS avg_confidence,
    ROUND(AVG(pulse_score)::NUMERIC, 1)                        AS avg_pulse_score,
    COUNT(*) FILTER (WHERE record_count > 1)                   AS multi_dept_entities,
    (SELECT COUNT(*) FROM review_queue WHERE status = 'PENDING') AS pending_reviews,
    (SELECT COUNT(*) FROM raw_records)                         AS total_raw_records,
    (SELECT COUNT(*) FROM audit_log)                           AS total_audit_events
FROM entities
WHERE is_active = TRUE;

-- Active learning feedback view
CREATE OR REPLACE VIEW v_learning_feedback AS
SELECT
    em.id,
    em.confidence,
    em.match_status,
    em.pan_match,
    em.gstin_match,
    em.name_phonetic_score,
    em.name_fuzzy_score,
    em.embedding_score,
    em.pin_match,
    em.address_score,
    -- The label from reviewer: 1=MERGED, 0=SPLIT/REJECTED
    CASE WHEN em.match_status = 'MERGED' THEN 1 ELSE 0 END AS reviewer_label,
    em.reviewed_by,
    em.reviewed_at
FROM entity_matches em
WHERE em.match_status IN ('MERGED', 'SPLIT', 'REJECTED')
  AND em.reviewed_at IS NOT NULL;
