-- ApexForge AI - UBID production schema
-- PostgreSQL / Neon
-- Source of truth: PostgreSQL only, no demo store

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- Utility
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION touch_review_case_last_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.last_updated_at = NOW();
    RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- Processing runs
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS processing_runs (
    run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_run_id uuid,
    run_type text NOT NULL,
    triggered_by text NOT NULL DEFAULT 'system',
    triggered_by_user text,
    status text NOT NULL DEFAULT 'QUEUED',
    parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
    metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    records_seen bigint NOT NULL DEFAULT 0,
    records_valid bigint NOT NULL DEFAULT 0,
    records_invalid bigint NOT NULL DEFAULT 0,
    records_normalized bigint NOT NULL DEFAULT 0,
    candidate_edges bigint NOT NULL DEFAULT 0,
    clusters_created bigint NOT NULL DEFAULT 0,
    ubids_created bigint NOT NULL DEFAULT 0,
    error_message text,
    started_at timestamptz,
    finished_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT processing_runs_type_check CHECK (
        run_type IN (
            'INGESTION',
            'NORMALIZATION',
            'MATCHING',
            'CLUSTERING',
            'UBID_ASSIGNMENT',
            'STATUS_REFRESH',
            'REVIEW_SYNC',
            'EXPORT'
        )
    ),
    CONSTRAINT processing_runs_status_check CHECK (
        status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')
    )
);

CREATE INDEX IF NOT EXISTS idx_processing_runs_status ON processing_runs (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_processing_runs_type ON processing_runs (run_type, created_at DESC);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        WHERE t.tgname = 'trg_processing_runs_updated_at'
          AND c.relname = 'processing_runs'
    ) THEN
        CREATE TRIGGER trg_processing_runs_updated_at
        BEFORE UPDATE ON processing_runs
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Uploads and source files
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS uploads (
    upload_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    processing_run_id uuid,
    uploader_id text,
    uploader_name text,
    department_code text,
    dataset_name text,
    original_filename text NOT NULL,
    content_type text,
    file_format text NOT NULL,
    file_size_bytes bigint,
    content_sha256 char(64) NOT NULL UNIQUE,
    upload_status text NOT NULL DEFAULT 'RECEIVED',
    schema_mapping jsonb NOT NULL DEFAULT '{}'::jsonb,
    parse_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    validation_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_row_count bigint NOT NULL DEFAULT 0,
    valid_row_count bigint NOT NULL DEFAULT 0,
    rejected_row_count bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT uploads_file_format_check CHECK (file_format IN ('CSV', 'JSON')),
    CONSTRAINT uploads_status_check CHECK (
        upload_status IN ('RECEIVED', 'PARSED', 'VALIDATED', 'PROCESSED', 'FAILED', 'ARCHIVED')
    )
);

CREATE INDEX IF NOT EXISTS idx_uploads_status ON uploads (upload_status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_uploads_department ON uploads (department_code, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_uploads_run ON uploads (processing_run_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        WHERE t.tgname = 'trg_uploads_updated_at'
          AND c.relname = 'uploads'
    ) THEN
        CREATE TRIGGER trg_uploads_updated_at
        BEFORE UPDATE ON uploads
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
    END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS source_files (
    source_file_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    upload_id uuid NOT NULL,
    file_index integer NOT NULL DEFAULT 1,
    source_name text NOT NULL,
    source_format text NOT NULL,
    original_filename text,
    source_checksum char(64),
    source_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    file_status text NOT NULL DEFAULT 'STAGED',
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT source_files_format_check CHECK (source_format IN ('CSV', 'JSON')),
    CONSTRAINT source_files_status_check CHECK (
        file_status IN ('STAGED', 'IMPORTED', 'ARCHIVED', 'FAILED')
    ),
    CONSTRAINT source_files_unique_file UNIQUE (upload_id, file_index)
);

CREATE INDEX IF NOT EXISTS idx_source_files_upload ON source_files (upload_id, file_index);
CREATE INDEX IF NOT EXISTS idx_source_files_checksum ON source_files (source_checksum);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        WHERE t.tgname = 'trg_source_files_updated_at'
          AND c.relname = 'source_files'
    ) THEN
        CREATE TRIGGER trg_source_files_updated_at
        BEFORE UPDATE ON source_files
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Raw records
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_records (
    raw_record_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_file_id uuid NOT NULL,
    processing_run_id uuid,
    source_row_number bigint NOT NULL,
    source_record_key text,
    department_code text,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    raw_text text,
    ingestion_state text NOT NULL DEFAULT 'NEW',
    validation_errors jsonb NOT NULL DEFAULT '[]'::jsonb,
    mapping_warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
    mapping_confidence numeric(5,2),
    is_duplicate boolean NOT NULL DEFAULT FALSE,
    record_hash char(64) NOT NULL UNIQUE,
    business_name text NOT NULL,
    trade_name text,
    legal_name text,
    pan char(10),
    gstin char(15),
    pin_code char(6),
    district text,
    state text,
    city text,
    address_line1 text,
    address_line2 text,
    address_full text,
    activity_date date,
    registration_date date,
    last_activity_date date,
    source_status text,
    source_category text,
    sector text,
    extra_fields jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT raw_records_unique_row UNIQUE (source_file_id, source_row_number)
);

CREATE INDEX IF NOT EXISTS idx_raw_records_pan ON raw_records (pan) WHERE pan IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_raw_records_gstin ON raw_records (gstin) WHERE gstin IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_raw_records_pin ON raw_records (pin_code) WHERE pin_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_raw_records_department ON raw_records (department_code, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_raw_records_name_trgm ON raw_records USING GIN (business_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_raw_records_district ON raw_records (district) WHERE district IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_raw_records_state ON raw_records (state) WHERE state IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_raw_records_state_district_pin ON raw_records (state, district, pin_code)
    WHERE pin_code IS NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        WHERE t.tgname = 'trg_raw_records_updated_at'
          AND c.relname = 'raw_records'
    ) THEN
        CREATE TRIGGER trg_raw_records_updated_at
        BEFORE UPDATE ON raw_records
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Normalized records
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS normalized_records (
    normalized_record_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_record_id uuid NOT NULL UNIQUE,
    processing_run_id uuid,
    record_hash char(64) NOT NULL UNIQUE,
    canonical_name text NOT NULL,
    canonical_name_key text NOT NULL,
    name_tokens text[] NOT NULL DEFAULT '{}'::text[],
    phonetic_key text,
    name_bucket text NOT NULL,
    normalized_pan char(10),
    normalized_gstin char(15),
    normalized_pin char(6),
    normalized_district text,
    normalized_state text,
    normalized_city text,
    normalized_address text,
    address_key text,
    entity_type text,
    sector text,
    confidence numeric(5,2) NOT NULL DEFAULT 100.00,
    source_flags jsonb NOT NULL DEFAULT '{}'::jsonb,
    feature_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    normalizer_version text NOT NULL DEFAULT 'v1',
    name_embedding vector(384),
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_normalized_pan ON normalized_records (normalized_pan) WHERE normalized_pan IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_normalized_gstin ON normalized_records (normalized_gstin) WHERE normalized_gstin IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_normalized_pin ON normalized_records (normalized_pin) WHERE normalized_pin IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_normalized_district ON normalized_records (normalized_district) WHERE normalized_district IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_normalized_state ON normalized_records (normalized_state) WHERE normalized_state IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_normalized_name_bucket ON normalized_records (name_bucket, normalized_pin);
CREATE INDEX IF NOT EXISTS idx_normalized_name_trgm ON normalized_records USING GIN (canonical_name_key gin_trgm_ops);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        WHERE t.tgname = 'trg_normalized_records_updated_at'
          AND c.relname = 'normalized_records'
    ) THEN
        CREATE TRIGGER trg_normalized_records_updated_at
        BEFORE UPDATE ON normalized_records
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Entity clusters and UBIDs
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ubids (
    ubid_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ubid_code text NOT NULL UNIQUE,
    cluster_id uuid UNIQUE,
    canonical_name text NOT NULL,
    canonical_name_key text,
    legal_name text,
    trade_name text,
    sector text,
    normalized_pan char(10),
    normalized_gstin char(15),
    normalized_pin char(6),
    district text,
    state text,
    address_normalized text,
    first_seen_at timestamptz,
    last_seen_at timestamptz,
    record_count bigint NOT NULL DEFAULT 0,
    source_count bigint NOT NULL DEFAULT 0,
    status_source text NOT NULL DEFAULT 'status_events',
    summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_run_id uuid,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT ubids_status_source_check CHECK (status_source IN ('status_events', 'derived_view', 'manual_override'))
);

CREATE INDEX IF NOT EXISTS idx_ubids_pan ON ubids (normalized_pan) WHERE normalized_pan IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ubids_gstin ON ubids (normalized_gstin) WHERE normalized_gstin IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ubids_pin ON ubids (normalized_pin) WHERE normalized_pin IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ubids_name_trgm ON ubids USING GIN (canonical_name_key gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_ubids_last_seen ON ubids (last_seen_at DESC);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        WHERE t.tgname = 'trg_ubids_updated_at'
          AND c.relname = 'ubids'
    ) THEN
        CREATE TRIGGER trg_ubids_updated_at
        BEFORE UPDATE ON ubids
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
    END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS entity_clusters (
    cluster_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_code text NOT NULL UNIQUE,
    cluster_hash char(64) NOT NULL UNIQUE,
    cluster_state text NOT NULL DEFAULT 'OPEN',
    canonical_name text,
    canonical_name_key text,
    district text,
    state text,
    pin_code char(6),
    canonical_pan char(10),
    canonical_gstin char(15),
    member_count bigint NOT NULL DEFAULT 0,
    record_count bigint NOT NULL DEFAULT 0,
    confidence_score numeric(5,2) NOT NULL DEFAULT 0.00,
    created_run_id uuid,
    current_ubid_id uuid UNIQUE,
    merged_from_cluster_id uuid,
    summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT entity_clusters_state_check CHECK (cluster_state IN ('OPEN', 'MERGED', 'SPLIT', 'ARCHIVED'))
);

CREATE INDEX IF NOT EXISTS idx_entity_clusters_state ON entity_clusters (cluster_state, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_entity_clusters_pin ON entity_clusters (pin_code) WHERE pin_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entity_clusters_gstin ON entity_clusters (canonical_gstin) WHERE canonical_gstin IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entity_clusters_pan ON entity_clusters (canonical_pan) WHERE canonical_pan IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entity_clusters_name_trgm ON entity_clusters USING GIN (canonical_name_key gin_trgm_ops);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        WHERE t.tgname = 'trg_entity_clusters_updated_at'
          AND c.relname = 'entity_clusters'
    ) THEN
        CREATE TRIGGER trg_entity_clusters_updated_at
        BEFORE UPDATE ON entity_clusters
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
    END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS cluster_members (
    cluster_member_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_id uuid NOT NULL,
    normalized_record_id uuid NOT NULL UNIQUE,
    ubid_id uuid,
    match_edge_id uuid,
    member_role text NOT NULL DEFAULT 'MEMBER',
    membership_confidence numeric(5,2) NOT NULL DEFAULT 0.00,
    join_reason jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_canonical boolean NOT NULL DEFAULT FALSE,
    is_active boolean NOT NULL DEFAULT TRUE,
    joined_at timestamptz NOT NULL DEFAULT NOW(),
    left_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_cluster_members_cluster ON cluster_members (cluster_id, is_active);
CREATE INDEX IF NOT EXISTS idx_cluster_members_ubid ON cluster_members (ubid_id) WHERE ubid_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cluster_members_match_edge ON cluster_members (match_edge_id) WHERE match_edge_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Match edges
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS match_edges (
    match_edge_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    processing_run_id uuid,
    left_normalized_record_id uuid NOT NULL,
    right_normalized_record_id uuid NOT NULL,
    pair_hash text GENERATED ALWAYS AS (
        left_normalized_record_id::text || ':' || right_normalized_record_id::text
    ) STORED,
    block_type text NOT NULL,
    match_tier text NOT NULL,
    score numeric(5,2) NOT NULL,
    confidence numeric(5,2) NOT NULL,
    auto_action text NOT NULL,
    decision_state text NOT NULL DEFAULT 'PENDING',
    reason_codes jsonb NOT NULL DEFAULT '{}'::jsonb,
    signal_weights jsonb NOT NULL DEFAULT '{}'::jsonb,
    explanation jsonb NOT NULL DEFAULT '{}'::jsonb,
    left_record_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    right_record_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    cluster_id uuid,
    ubid_id uuid,
    resolved_by text,
    resolved_at timestamptz,
    reversed_by text,
    reversed_at timestamptz,
    reversal_reason text,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT match_edges_pair_order_check CHECK (left_normalized_record_id < right_normalized_record_id),
    CONSTRAINT match_edges_unique_pair UNIQUE (left_normalized_record_id, right_normalized_record_id),
    CONSTRAINT match_edges_tier_check CHECK (match_tier IN ('EXACT', 'STRONG', 'WEAK', 'IGNORED')),
    CONSTRAINT match_edges_block_check CHECK (
        block_type IN ('PAN', 'GSTIN', 'PIN', 'NAME_BUCKET', 'PHONETIC', 'ADDRESS')
    ),
    CONSTRAINT match_edges_action_check CHECK (auto_action IN ('AUTO_MERGE', 'REVIEW', 'IGNORE')),
    CONSTRAINT match_edges_state_check CHECK (
        decision_state IN (
            'PENDING',
            'AUTO_MERGED',
            'IN_REVIEW',
            'APPROVED',
            'REJECTED',
            'ESCALATED',
            'REVERSED'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_match_edges_processing_run ON match_edges (processing_run_id);
CREATE INDEX IF NOT EXISTS idx_match_edges_score ON match_edges (score DESC);
CREATE INDEX IF NOT EXISTS idx_match_edges_confidence ON match_edges (confidence DESC);
CREATE INDEX IF NOT EXISTS idx_match_edges_tier ON match_edges (match_tier, decision_state);
CREATE INDEX IF NOT EXISTS idx_match_edges_state ON match_edges (decision_state, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_match_edges_left ON match_edges (left_normalized_record_id);
CREATE INDEX IF NOT EXISTS idx_match_edges_right ON match_edges (right_normalized_record_id);
CREATE INDEX IF NOT EXISTS idx_match_edges_cluster ON match_edges (cluster_id) WHERE cluster_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_match_edges_ubid ON match_edges (ubid_id) WHERE ubid_id IS NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        WHERE t.tgname = 'trg_match_edges_updated_at'
          AND c.relname = 'match_edges'
    ) THEN
        CREATE TRIGGER trg_match_edges_updated_at
        BEFORE UPDATE ON match_edges
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Review workflow
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS review_cases (
    review_case_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    processing_run_id uuid,
    match_edge_id uuid NOT NULL UNIQUE,
    cluster_id uuid,
    ubid_id uuid,
    case_status text NOT NULL DEFAULT 'OPEN',
    priority smallint NOT NULL DEFAULT 5,
    assigned_to text,
    assigned_group text,
    review_reason text,
    review_summary text,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    opened_at timestamptz NOT NULL DEFAULT NOW(),
    last_updated_at timestamptz NOT NULL DEFAULT NOW(),
    closed_at timestamptz,
    reopened_count integer NOT NULL DEFAULT 0,
    current_action_id uuid,
    CONSTRAINT review_cases_status_check CHECK (
        case_status IN ('OPEN', 'IN_REVIEW', 'APPROVED', 'REJECTED', 'ESCALATED', 'CLOSED', 'REVERSED')
    ),
    CONSTRAINT review_cases_priority_check CHECK (priority BETWEEN 1 AND 10)
);

CREATE INDEX IF NOT EXISTS idx_review_cases_status ON review_cases (case_status, priority, opened_at);
CREATE INDEX IF NOT EXISTS idx_review_cases_assigned_to ON review_cases (assigned_to, case_status);
CREATE INDEX IF NOT EXISTS idx_review_cases_match_edge ON review_cases (match_edge_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        WHERE t.tgname = 'trg_review_cases_updated_at'
          AND c.relname = 'review_cases'
    ) THEN
        CREATE TRIGGER trg_review_cases_updated_at
        BEFORE UPDATE ON review_cases
        FOR EACH ROW
        EXECUTE FUNCTION touch_review_case_last_updated_at();
    END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS review_actions (
    review_action_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    review_case_id uuid NOT NULL,
    match_edge_id uuid,
    actor_id text NOT NULL,
    actor_name text,
    actor_role text,
    action_type text NOT NULL,
    decision_value text,
    note text,
    rationale jsonb NOT NULL DEFAULT '{}'::jsonb,
    before_state jsonb NOT NULL DEFAULT '{}'::jsonb,
    after_state jsonb NOT NULL DEFAULT '{}'::jsonb,
    reversed_action_id uuid,
    created_ip text,
    session_id text,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT review_actions_type_check CHECK (
        action_type IN ('APPROVE', 'REJECT', 'ESCALATE', 'REOPEN', 'REVERSE')
    )
);

CREATE INDEX IF NOT EXISTS idx_review_actions_case ON review_actions (review_case_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_review_actions_match ON review_actions (match_edge_id) WHERE match_edge_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_review_actions_actor ON review_actions (actor_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- Status engine
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS status_events (
    status_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ubid_id uuid NOT NULL,
    raw_record_id uuid,
    event_type text NOT NULL,
    event_source text,
    event_date timestamptz NOT NULL,
    activity_weight numeric(5,2) NOT NULL DEFAULT 1.00,
    derived_status text,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT status_events_status_check CHECK (
        derived_status IS NULL OR derived_status IN ('ACTIVE', 'DORMANT', 'CLOSED')
    )
);

CREATE INDEX IF NOT EXISTS idx_status_events_ubid ON status_events (ubid_id, event_date DESC);
CREATE INDEX IF NOT EXISTS idx_status_events_raw_record ON status_events (raw_record_id) WHERE raw_record_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_status_events_type ON status_events (event_type, event_date DESC);
CREATE INDEX IF NOT EXISTS idx_status_events_derived_status ON status_events (derived_status) WHERE derived_status IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Audit log
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS audit_logs (
    audit_log_id bigserial PRIMARY KEY,
    run_id uuid,
    actor_id text,
    actor_role text,
    event_type text NOT NULL,
    entity_type text NOT NULL,
    entity_id text NOT NULL,
    action text NOT NULL,
    severity text NOT NULL DEFAULT 'INFO',
    before_state jsonb,
    after_state jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    correlation_id uuid,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT audit_logs_severity_check CHECK (severity IN ('DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL'))
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_run ON audit_logs (run_id) WHERE run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_logs_event_type ON audit_logs (event_type, created_at DESC);

-- ---------------------------------------------------------------------------
-- Foreign keys added after table creation to avoid circular dependency issues
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_processing_runs_parent'
          AND t.relname = 'processing_runs'
    ) THEN
        ALTER TABLE processing_runs
            ADD CONSTRAINT fk_processing_runs_parent
            FOREIGN KEY (parent_run_id) REFERENCES processing_runs(run_id)
            ON DELETE SET NULL;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_uploads_processing_run'
          AND t.relname = 'uploads'
    ) THEN
        ALTER TABLE uploads
            ADD CONSTRAINT fk_uploads_processing_run
            FOREIGN KEY (processing_run_id) REFERENCES processing_runs(run_id)
            ON DELETE SET NULL;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_source_files_upload'
          AND t.relname = 'source_files'
    ) THEN
        ALTER TABLE source_files
            ADD CONSTRAINT fk_source_files_upload
            FOREIGN KEY (upload_id) REFERENCES uploads(upload_id)
            ON DELETE CASCADE;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_raw_records_source_file'
          AND t.relname = 'raw_records'
    ) THEN
        ALTER TABLE raw_records
            ADD CONSTRAINT fk_raw_records_source_file
            FOREIGN KEY (source_file_id) REFERENCES source_files(source_file_id)
            ON DELETE CASCADE;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_raw_records_processing_run'
          AND t.relname = 'raw_records'
    ) THEN
        ALTER TABLE raw_records
            ADD CONSTRAINT fk_raw_records_processing_run
            FOREIGN KEY (processing_run_id) REFERENCES processing_runs(run_id)
            ON DELETE SET NULL;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_normalized_records_raw_record'
          AND t.relname = 'normalized_records'
    ) THEN
        ALTER TABLE normalized_records
            ADD CONSTRAINT fk_normalized_records_raw_record
            FOREIGN KEY (raw_record_id) REFERENCES raw_records(raw_record_id)
            ON DELETE CASCADE;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_normalized_records_processing_run'
          AND t.relname = 'normalized_records'
    ) THEN
        ALTER TABLE normalized_records
            ADD CONSTRAINT fk_normalized_records_processing_run
            FOREIGN KEY (processing_run_id) REFERENCES processing_runs(run_id)
            ON DELETE SET NULL;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_ubids_created_run'
          AND t.relname = 'ubids'
    ) THEN
        ALTER TABLE ubids
            ADD CONSTRAINT fk_ubids_created_run
            FOREIGN KEY (created_run_id) REFERENCES processing_runs(run_id)
            ON DELETE SET NULL;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_entity_clusters_created_run'
          AND t.relname = 'entity_clusters'
    ) THEN
        ALTER TABLE entity_clusters
            ADD CONSTRAINT fk_entity_clusters_created_run
            FOREIGN KEY (created_run_id) REFERENCES processing_runs(run_id)
            ON DELETE SET NULL;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_entity_clusters_current_ubid'
          AND t.relname = 'entity_clusters'
    ) THEN
        ALTER TABLE entity_clusters
            ADD CONSTRAINT fk_entity_clusters_current_ubid
            FOREIGN KEY (current_ubid_id) REFERENCES ubids(ubid_id)
            ON DELETE SET NULL
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_ubids_cluster'
          AND t.relname = 'ubids'
    ) THEN
        ALTER TABLE ubids
            ADD CONSTRAINT fk_ubids_cluster
            FOREIGN KEY (cluster_id) REFERENCES entity_clusters(cluster_id)
            ON DELETE SET NULL
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_cluster_members_cluster'
          AND t.relname = 'cluster_members'
    ) THEN
        ALTER TABLE cluster_members
            ADD CONSTRAINT fk_cluster_members_cluster
            FOREIGN KEY (cluster_id) REFERENCES entity_clusters(cluster_id)
            ON DELETE CASCADE;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_cluster_members_record'
          AND t.relname = 'cluster_members'
    ) THEN
        ALTER TABLE cluster_members
            ADD CONSTRAINT fk_cluster_members_record
            FOREIGN KEY (normalized_record_id) REFERENCES normalized_records(normalized_record_id)
            ON DELETE CASCADE;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_cluster_members_ubid'
          AND t.relname = 'cluster_members'
    ) THEN
        ALTER TABLE cluster_members
            ADD CONSTRAINT fk_cluster_members_ubid
            FOREIGN KEY (ubid_id) REFERENCES ubids(ubid_id)
            ON DELETE SET NULL;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_cluster_members_edge'
          AND t.relname = 'cluster_members'
    ) THEN
        ALTER TABLE cluster_members
            ADD CONSTRAINT fk_cluster_members_edge
            FOREIGN KEY (match_edge_id) REFERENCES match_edges(match_edge_id)
            ON DELETE SET NULL;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_match_edges_processing_run'
          AND t.relname = 'match_edges'
    ) THEN
        ALTER TABLE match_edges
            ADD CONSTRAINT fk_match_edges_processing_run
            FOREIGN KEY (processing_run_id) REFERENCES processing_runs(run_id)
            ON DELETE SET NULL;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_match_edges_left_record'
          AND t.relname = 'match_edges'
    ) THEN
        ALTER TABLE match_edges
            ADD CONSTRAINT fk_match_edges_left_record
            FOREIGN KEY (left_normalized_record_id) REFERENCES normalized_records(normalized_record_id)
            ON DELETE CASCADE;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_match_edges_right_record'
          AND t.relname = 'match_edges'
    ) THEN
        ALTER TABLE match_edges
            ADD CONSTRAINT fk_match_edges_right_record
            FOREIGN KEY (right_normalized_record_id) REFERENCES normalized_records(normalized_record_id)
            ON DELETE CASCADE;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_match_edges_cluster'
          AND t.relname = 'match_edges'
    ) THEN
        ALTER TABLE match_edges
            ADD CONSTRAINT fk_match_edges_cluster
            FOREIGN KEY (cluster_id) REFERENCES entity_clusters(cluster_id)
            ON DELETE SET NULL;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_match_edges_ubid'
          AND t.relname = 'match_edges'
    ) THEN
        ALTER TABLE match_edges
            ADD CONSTRAINT fk_match_edges_ubid
            FOREIGN KEY (ubid_id) REFERENCES ubids(ubid_id)
            ON DELETE SET NULL;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_review_cases_processing_run'
          AND t.relname = 'review_cases'
    ) THEN
        ALTER TABLE review_cases
            ADD CONSTRAINT fk_review_cases_processing_run
            FOREIGN KEY (processing_run_id) REFERENCES processing_runs(run_id)
            ON DELETE SET NULL;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_review_cases_edge'
          AND t.relname = 'review_cases'
    ) THEN
        ALTER TABLE review_cases
            ADD CONSTRAINT fk_review_cases_edge
            FOREIGN KEY (match_edge_id) REFERENCES match_edges(match_edge_id)
            ON DELETE CASCADE;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_review_cases_cluster'
          AND t.relname = 'review_cases'
    ) THEN
        ALTER TABLE review_cases
            ADD CONSTRAINT fk_review_cases_cluster
            FOREIGN KEY (cluster_id) REFERENCES entity_clusters(cluster_id)
            ON DELETE SET NULL;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_review_cases_ubid'
          AND t.relname = 'review_cases'
    ) THEN
        ALTER TABLE review_cases
            ADD CONSTRAINT fk_review_cases_ubid
            FOREIGN KEY (ubid_id) REFERENCES ubids(ubid_id)
            ON DELETE SET NULL;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_review_cases_current_action'
          AND t.relname = 'review_cases'
    ) THEN
        ALTER TABLE review_cases
            ADD CONSTRAINT fk_review_cases_current_action
            FOREIGN KEY (current_action_id) REFERENCES review_actions(review_action_id)
            ON DELETE SET NULL
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_review_actions_case'
          AND t.relname = 'review_actions'
    ) THEN
        ALTER TABLE review_actions
            ADD CONSTRAINT fk_review_actions_case
            FOREIGN KEY (review_case_id) REFERENCES review_cases(review_case_id)
            ON DELETE CASCADE;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_review_actions_edge'
          AND t.relname = 'review_actions'
    ) THEN
        ALTER TABLE review_actions
            ADD CONSTRAINT fk_review_actions_edge
            FOREIGN KEY (match_edge_id) REFERENCES match_edges(match_edge_id)
            ON DELETE SET NULL;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_review_actions_reverse'
          AND t.relname = 'review_actions'
    ) THEN
        ALTER TABLE review_actions
            ADD CONSTRAINT fk_review_actions_reverse
            FOREIGN KEY (reversed_action_id) REFERENCES review_actions(review_action_id)
            ON DELETE SET NULL;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_status_events_ubid'
          AND t.relname = 'status_events'
    ) THEN
        ALTER TABLE status_events
            ADD CONSTRAINT fk_status_events_ubid
            FOREIGN KEY (ubid_id) REFERENCES ubids(ubid_id)
            ON DELETE CASCADE;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_status_events_raw_record'
          AND t.relname = 'status_events'
    ) THEN
        ALTER TABLE status_events
            ADD CONSTRAINT fk_status_events_raw_record
            FOREIGN KEY (raw_record_id) REFERENCES raw_records(raw_record_id)
            ON DELETE SET NULL;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE c.conname = 'fk_audit_logs_run'
          AND t.relname = 'audit_logs'
    ) THEN
        ALTER TABLE audit_logs
            ADD CONSTRAINT fk_audit_logs_run
            FOREIGN KEY (run_id) REFERENCES processing_runs(run_id)
            ON DELETE SET NULL;
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Helper views
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_ubid_registry AS
WITH latest_status AS (
    SELECT
        DISTINCT ON (se.ubid_id)
        se.ubid_id,
        se.event_date AS latest_activity_at,
        COALESCE(
            se.derived_status,
            CASE
                WHEN se.event_date >= NOW() - INTERVAL '12 months' THEN 'ACTIVE'
                WHEN se.event_date >= NOW() - INTERVAL '18 months' THEN 'DORMANT'
                ELSE 'CLOSED'
            END
        ) AS computed_status
    FROM status_events se
    ORDER BY se.ubid_id, se.event_date DESC, se.created_at DESC
),
  cluster_counts AS (
      SELECT
          cm.ubid_id,
          COUNT(*) FILTER (WHERE cm.is_active) AS member_count
      FROM cluster_members cm
      GROUP BY cm.ubid_id
  ),
  event_counts AS (
      SELECT
          se.ubid_id,
          COUNT(*) AS total_events
      FROM status_events se
      GROUP BY se.ubid_id
  )
SELECT
    u.ubid_id,
    u.ubid_code,
    u.canonical_name,
    u.legal_name,
    u.trade_name,
    COALESCE(u.summary->>'sector', '') AS sector,
    u.normalized_pan,
    u.normalized_gstin,
    u.normalized_pin,
    u.district,
    u.state,
    u.address_normalized,
    COALESCE(ls.latest_activity_at, u.last_seen_at) AS latest_activity_at,
      COALESCE(ls.computed_status, 'CLOSED') AS current_status,
      COALESCE(cc.member_count, 0) AS member_count,
      COALESCE(cc.member_count, 0) AS linked_records,
      COALESCE(ec.total_events, 0) AS total_events,
      COALESCE((u.summary->>'manual_score')::numeric, 0) AS pulse_score,
      u.record_count,
    u.source_count,
    u.summary,
    u.created_at,
    u.updated_at
  FROM ubids u
  LEFT JOIN latest_status ls ON ls.ubid_id = u.ubid_id
  LEFT JOIN cluster_counts cc ON cc.ubid_id = u.ubid_id
  LEFT JOIN event_counts ec ON ec.ubid_id = u.ubid_id;

CREATE OR REPLACE VIEW v_review_queue AS
SELECT
    rc.review_case_id,
    rc.case_status,
    rc.priority,
    rc.assigned_to,
    rc.assigned_group,
    rc.review_reason,
    rc.review_summary,
    rc.opened_at,
    rc.last_updated_at,
    me.match_edge_id,
    me.match_tier,
    me.block_type,
    me.score,
    me.confidence,
    me.auto_action,
    me.reason_codes,
    me.signal_weights,
    me.explanation,
    left_rec.canonical_name AS left_name,
    left_rec.normalized_pan AS left_pan,
    left_rec.normalized_gstin AS left_gstin,
    left_rec.normalized_pin AS left_pin,
    right_rec.canonical_name AS right_name,
    right_rec.normalized_pan AS right_pan,
    right_rec.normalized_gstin AS right_gstin,
    right_rec.normalized_pin AS right_pin
FROM review_cases rc
JOIN match_edges me ON me.match_edge_id = rc.match_edge_id
JOIN normalized_records left_rec ON left_rec.normalized_record_id = me.left_normalized_record_id
JOIN normalized_records right_rec ON right_rec.normalized_record_id = me.right_normalized_record_id;

CREATE OR REPLACE VIEW v_dashboard_summary AS
SELECT
    (SELECT COUNT(*) FROM uploads) AS total_uploads,
    (SELECT COUNT(*) FROM raw_records) AS total_raw_records,
    (SELECT COUNT(*) FROM normalized_records) AS total_normalized_records,
    (SELECT COUNT(*) FROM ubids) AS total_ubids,
    (SELECT COUNT(*) FROM entity_clusters) AS total_clusters,
    (SELECT COUNT(*) FROM match_edges WHERE decision_state = 'PENDING') AS pending_match_edges,
    (SELECT COUNT(*) FROM review_cases WHERE case_status IN ('OPEN', 'IN_REVIEW')) AS open_review_cases,
    (SELECT COUNT(*) FROM audit_logs) AS total_audit_logs,
    (SELECT COUNT(*) FROM status_events) AS total_status_events;
