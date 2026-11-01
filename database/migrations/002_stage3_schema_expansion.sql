-- ==============================================================================
-- InfoScope AI — Stage 3: Database Schema Expansion Migration (Production-Ready)
-- Migration ID: 002_stage3_schema_expansion
-- Parent Tables: public.research_sessions, public.research_sources
-- New Tables:
--   1. public.expected_fields
--   2. public.claims
--   3. public.issues
--   4. public.issue_evidence
--   5. public.checklist_items
--   6. public.reports
--
-- Core Guarantees:
--   - Non-destructive: No DROP TABLE, DROP COLUMN, or TRUNCATE.
--   - Transactional: Entire migration executes in an atomic transaction.
--   - Pre-flight checks: Validates existing schema and data before applying changes.
--   - Source ownership: Enforces research_sources.user_id = research_sessions.user_id.
--   - Cross-session integrity: Composite FKs prevent cross-session / cross-user references.
--   - PG14 & PG15+ compatibility: Version-aware checklist_items ON DELETE SET NULL handling.
--   - Pure top-level functions: No nested CREATE FUNCTION inside procedural DO blocks.
--   - Proper timestamptz defaults: Uses now() for session-timezone safety.
--   - RLS enabled on all tables: Strict auth.uid() = user_id enforcement.
-- ==============================================================================

BEGIN;

-- ------------------------------------------------------------------------------
-- Step 0: Ensure required extensions exist
-- ------------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";


-- ------------------------------------------------------------------------------
-- Step 1: Pre-Flight Safety & Integrity Assertions
-- Fails immediately with clear diagnostic message if schema or data is invalid.
-- ------------------------------------------------------------------------------
DO $$
DECLARE
    mismatched_sources INTEGER;
    orphaned_sources INTEGER;
BEGIN
    -- Check 1: Required parent tables must exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'research_sessions'
    ) THEN
        RAISE EXCEPTION 'Pre-migration check failed: Table public.research_sessions does not exist.';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'research_sources'
    ) THEN
        RAISE EXCEPTION 'Pre-migration check failed: Table public.research_sources does not exist.';
    END IF;

    -- Check 2: research_sessions must have expected user_id column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'research_sessions' AND column_name = 'user_id'
    ) THEN
        RAISE EXCEPTION 'Pre-migration check failed: public.research_sessions is missing column user_id.';
    END IF;

    -- Check 3: research_sources must have session_id and user_id columns
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'research_sources' AND column_name = 'session_id'
    ) OR NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'research_sources' AND column_name = 'user_id'
    ) THEN
        RAISE EXCEPTION 'Pre-migration check failed: public.research_sources is missing session_id or user_id columns.';
    END IF;

    -- Check 4: Check for orphaned research_sources
    SELECT COUNT(*) INTO orphaned_sources
    FROM public.research_sources src
    LEFT JOIN public.research_sessions ses ON src.session_id = ses.id
    WHERE ses.id IS NULL;

    IF orphaned_sources > 0 THEN
        RAISE EXCEPTION 'Pre-migration check failed: Found % orphaned row(s) in research_sources referencing non-existent sessions. Aborting.', orphaned_sources;
    END IF;

    -- Check 5: Check for user_id mismatch between research_sources and research_sessions
    SELECT COUNT(*) INTO mismatched_sources
    FROM public.research_sources src
    JOIN public.research_sessions ses ON src.session_id = ses.id
    WHERE src.user_id <> ses.user_id;

    IF mismatched_sources > 0 THEN
        RAISE EXCEPTION 'Pre-migration check failed: Found % row(s) in research_sources where user_id does not match parent research_sessions.user_id. Aborting.', mismatched_sources;
    END IF;
END $$;


-- ------------------------------------------------------------------------------
-- Step 2: Shared Updated Timestamp Function (Top-Level Definition)
-- Uses now() to store exact UTC timestamps without session-timezone skew.
-- Compatible with all existing and new triggers.
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ------------------------------------------------------------------------------
-- Step 3: Hardened Source Ownership & Parent Composite Unique Constraints
-- Enforces:
--   a) research_sessions(id, user_id) composite unique anchor
--   b) research_sources(session_id, user_id) composite foreign key -> research_sessions(id, user_id)
--   c) research_sources(id, session_id) composite unique anchor for child tables
-- ------------------------------------------------------------------------------
DO $$
BEGIN
    -- Composite unique constraint on research_sessions(id, user_id)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'uq_research_sessions_id_user' 
          AND conrelid = 'public.research_sessions'::regclass
    ) THEN
        ALTER TABLE public.research_sessions 
            ADD CONSTRAINT uq_research_sessions_id_user UNIQUE (id, user_id);
    END IF;

    -- Enforce research_sources.user_id = research_sessions.user_id
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'fk_research_sources_session_user' 
          AND conrelid = 'public.research_sources'::regclass
    ) THEN
        ALTER TABLE public.research_sources 
            ADD CONSTRAINT fk_research_sources_session_user 
            FOREIGN KEY (session_id, user_id) 
            REFERENCES public.research_sessions(id, user_id) 
            ON DELETE CASCADE;
    END IF;

    -- Composite unique constraint on research_sources(id, session_id)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'uq_research_sources_id_session' 
          AND conrelid = 'public.research_sources'::regclass
    ) THEN
        ALTER TABLE public.research_sources 
            ADD CONSTRAINT uq_research_sources_id_session UNIQUE (id, session_id);
    END IF;
END $$;


-- ==============================================================================
-- Table 1: public.expected_fields
-- Expected topic dimensions and completeness criteria
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.expected_fields (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    field_name VARCHAR(150) NOT NULL,
    field_category VARCHAR(100) NOT NULL DEFAULT 'general',
    description TEXT,
    is_required BOOLEAN NOT NULL DEFAULT true,
    weight NUMERIC(3, 2) NOT NULL DEFAULT 1.00 CHECK (weight >= 0.00 AND weight <= 5.00),
    status VARCHAR(50) NOT NULL DEFAULT 'missing' CHECK (status IN ('missing', 'partially_covered', 'covered')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Cross-user integrity constraint: child session_id and user_id must match parent session
    CONSTRAINT fk_expected_fields_session FOREIGN KEY (session_id, user_id) 
        REFERENCES public.research_sessions(id, user_id) ON DELETE CASCADE,

    -- Unique field name within a single research session
    CONSTRAINT uq_expected_fields_session_name UNIQUE (session_id, field_name),

    -- Relational anchor for downstream referencing
    CONSTRAINT uq_expected_fields_id_session UNIQUE (id, session_id)
);

COMMENT ON TABLE public.expected_fields IS 'Stores topic dimensions and criteria required for comprehensive research coverage.';
COMMENT ON COLUMN public.expected_fields.field_name IS 'Name of expected attribute (e.g. Pricing, Security, Architecture)';
COMMENT ON COLUMN public.expected_fields.weight IS 'Relative importance score (0.00 to 5.00)';
COMMENT ON COLUMN public.expected_fields.status IS 'Coverage status: missing, partially_covered, covered';

CREATE INDEX IF NOT EXISTS idx_expected_fields_session_id ON public.expected_fields(session_id);
CREATE INDEX IF NOT EXISTS idx_expected_fields_user_id ON public.expected_fields(user_id);
CREATE INDEX IF NOT EXISTS idx_expected_fields_status ON public.expected_fields(session_id, status);

DROP TRIGGER IF EXISTS set_expected_fields_updated_at ON public.expected_fields;
CREATE TRIGGER set_expected_fields_updated_at
    BEFORE UPDATE ON public.expected_fields
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_updated_at();

ALTER TABLE public.expected_fields ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own expected fields" ON public.expected_fields;
CREATE POLICY "Users can view own expected fields"
    ON public.expected_fields FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own expected fields" ON public.expected_fields;
CREATE POLICY "Users can insert own expected fields"
    ON public.expected_fields FOR INSERT
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update own expected fields" ON public.expected_fields;
CREATE POLICY "Users can update own expected fields"
    ON public.expected_fields FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own expected fields" ON public.expected_fields;
CREATE POLICY "Users can delete own expected fields"
    ON public.expected_fields FOR DELETE
    USING (auth.uid() = user_id);


-- ==============================================================================
-- Table 2: public.claims
-- Normalized factual statements extracted from research sources
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL,
    source_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    claim_text TEXT NOT NULL,
    context_snippet TEXT,
    confidence_score NUMERIC(3, 2) CHECK (confidence_score >= 0.00 AND confidence_score <= 1.00),
    status VARCHAR(50) NOT NULL DEFAULT 'unverified' CHECK (status IN ('verified', 'conflicting', 'unverified', 'refuted')),
    extracted_keywords TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Cross-user integrity: session_id and user_id must match parent session
    CONSTRAINT fk_claims_session FOREIGN KEY (session_id, user_id) 
        REFERENCES public.research_sessions(id, user_id) ON DELETE CASCADE,

    -- Cross-session integrity: source_id must belong to the exact same session_id
    CONSTRAINT fk_claims_source FOREIGN KEY (source_id, session_id) 
        REFERENCES public.research_sources(id, session_id) ON DELETE CASCADE,

    -- Relational anchor for downstream referencing
    CONSTRAINT uq_claims_id_session UNIQUE (id, session_id)
);

COMMENT ON TABLE public.claims IS 'Stores discrete extracted statements and factual assertions with source attribution.';
COMMENT ON COLUMN public.claims.source_id IS 'References the specific research source where this claim originated';
COMMENT ON COLUMN public.claims.confidence_score IS 'Extraction confidence score between 0.00 and 1.00';
COMMENT ON COLUMN public.claims.status IS 'Claim status: verified, conflicting, unverified, refuted';

CREATE INDEX IF NOT EXISTS idx_claims_session_id ON public.claims(session_id);
CREATE INDEX IF NOT EXISTS idx_claims_source_id ON public.claims(source_id);
CREATE INDEX IF NOT EXISTS idx_claims_user_id ON public.claims(user_id);
CREATE INDEX IF NOT EXISTS idx_claims_status ON public.claims(session_id, status);

DROP TRIGGER IF EXISTS set_claims_updated_at ON public.claims;
CREATE TRIGGER set_claims_updated_at
    BEFORE UPDATE ON public.claims
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_updated_at();

ALTER TABLE public.claims ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own claims" ON public.claims;
CREATE POLICY "Users can view own claims"
    ON public.claims FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own claims" ON public.claims;
CREATE POLICY "Users can insert own claims"
    ON public.claims FOR INSERT
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update own claims" ON public.claims;
CREATE POLICY "Users can update own claims"
    ON public.claims FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own claims" ON public.claims;
CREATE POLICY "Users can delete own claims"
    ON public.claims FOR DELETE
    USING (auth.uid() = user_id);


-- ==============================================================================
-- Table 3: public.issues
-- Contradictions, missing info gaps, outdated assertions, and ambiguities
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.issues (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    issue_type VARCHAR(50) NOT NULL CHECK (issue_type IN ('contradiction', 'unbacked_claim', 'gap', 'outdated_source', 'ambiguity')),
    severity VARCHAR(20) NOT NULL DEFAULT 'medium' CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'investigating', 'resolved', 'dismissed')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Cross-user integrity constraint: session_id and user_id must match parent session
    CONSTRAINT fk_issues_session FOREIGN KEY (session_id, user_id) 
        REFERENCES public.research_sessions(id, user_id) ON DELETE CASCADE,

    -- Relational anchor for downstream referencing
    CONSTRAINT uq_issues_id_session UNIQUE (id, session_id)
);

COMMENT ON TABLE public.issues IS 'Stores detected discrepancies, conflicts between claims, and identified information gaps.';
COMMENT ON COLUMN public.issues.issue_type IS 'Category: contradiction, unbacked_claim, gap, outdated_source, ambiguity';
COMMENT ON COLUMN public.issues.severity IS 'Priority ranking: low, medium, high, critical';
COMMENT ON COLUMN public.issues.status IS 'Lifecycle state: open, investigating, resolved, dismissed';

CREATE INDEX IF NOT EXISTS idx_issues_session_id ON public.issues(session_id);
CREATE INDEX IF NOT EXISTS idx_issues_user_id ON public.issues(user_id);
CREATE INDEX IF NOT EXISTS idx_issues_type_severity ON public.issues(session_id, issue_type, severity);
CREATE INDEX IF NOT EXISTS idx_issues_status ON public.issues(session_id, status);

DROP TRIGGER IF EXISTS set_issues_updated_at ON public.issues;
CREATE TRIGGER set_issues_updated_at
    BEFORE UPDATE ON public.issues
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_updated_at();

ALTER TABLE public.issues ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own issues" ON public.issues;
CREATE POLICY "Users can view own issues"
    ON public.issues FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own issues" ON public.issues;
CREATE POLICY "Users can insert own issues"
    ON public.issues FOR INSERT
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update own issues" ON public.issues;
CREATE POLICY "Users can update own issues"
    ON public.issues FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own issues" ON public.issues;
CREATE POLICY "Users can delete own issues"
    ON public.issues FOR DELETE
    USING (auth.uid() = user_id);


-- ==============================================================================
-- Table 4: public.issue_evidence
-- Links issues to specific claims and research sources with evidence polarity
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.issue_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL,
    issue_id UUID NOT NULL,
    claim_id UUID,
    source_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    polarity VARCHAR(20) NOT NULL DEFAULT 'contradicts' CHECK (polarity IN ('supports', 'contradicts', 'neutral', 'unbacked')),
    evidence_text TEXT NOT NULL,
    explanation TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Cross-user integrity constraint: session_id and user_id must match parent session
    CONSTRAINT fk_issue_evidence_session FOREIGN KEY (session_id, user_id) 
        REFERENCES public.research_sessions(id, user_id) ON DELETE CASCADE,

    -- Cross-session integrity constraint: issue_id must belong to the exact same session_id
    CONSTRAINT fk_issue_evidence_issue FOREIGN KEY (issue_id, session_id) 
        REFERENCES public.issues(id, session_id) ON DELETE CASCADE,

    -- Cross-session integrity constraint: source_id must belong to the exact same session_id
    CONSTRAINT fk_issue_evidence_source FOREIGN KEY (source_id, session_id) 
        REFERENCES public.research_sources(id, session_id) ON DELETE CASCADE,

    -- Cross-session integrity constraint: claim_id (if present) must belong to the exact same session_id
    CONSTRAINT fk_issue_evidence_claim FOREIGN KEY (claim_id, session_id) 
        REFERENCES public.claims(id, session_id) ON DELETE CASCADE
);

COMMENT ON TABLE public.issue_evidence IS 'Links detected issues to grounded claims and sources with evidence polarity.';
COMMENT ON COLUMN public.issue_evidence.polarity IS 'Polarity of this evidence: supports, contradicts, neutral, unbacked';
COMMENT ON COLUMN public.issue_evidence.evidence_text IS 'Exact source excerpt or quote demonstrating the contradiction or assertion';

CREATE INDEX IF NOT EXISTS idx_issue_evidence_session_id ON public.issue_evidence(session_id);
CREATE INDEX IF NOT EXISTS idx_issue_evidence_issue_id ON public.issue_evidence(issue_id);
CREATE INDEX IF NOT EXISTS idx_issue_evidence_claim_id ON public.issue_evidence(claim_id);
CREATE INDEX IF NOT EXISTS idx_issue_evidence_source_id ON public.issue_evidence(source_id);
CREATE INDEX IF NOT EXISTS idx_issue_evidence_user_id ON public.issue_evidence(user_id);

ALTER TABLE public.issue_evidence ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own issue evidence" ON public.issue_evidence;
CREATE POLICY "Users can view own issue evidence"
    ON public.issue_evidence FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own issue evidence" ON public.issue_evidence;
CREATE POLICY "Users can insert own issue evidence"
    ON public.issue_evidence FOR INSERT
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update own issue evidence" ON public.issue_evidence;
CREATE POLICY "Users can update own issue evidence"
    ON public.issue_evidence FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own issue evidence" ON public.issue_evidence;
CREATE POLICY "Users can delete own issue evidence"
    ON public.issue_evidence FOR DELETE
    USING (auth.uid() = user_id);


-- ==============================================================================
-- Table 5: public.checklist_items
-- Prioritized action items for human verification
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.checklist_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    issue_id UUID,
    task_description TEXT NOT NULL,
    priority VARCHAR(20) NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    status VARCHAR(50) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'completed', 'skipped')),
    verification_notes TEXT,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Cross-user integrity constraint: session_id and user_id must match parent session
    CONSTRAINT fk_checklist_items_session FOREIGN KEY (session_id, user_id) 
        REFERENCES public.research_sessions(id, user_id) ON DELETE CASCADE,

    -- Relational anchor for downstream referencing
    CONSTRAINT uq_checklist_items_id_session UNIQUE (id, session_id)
);

COMMENT ON TABLE public.checklist_items IS 'Stores prioritized verification tasks generated from identified gaps and contradictions.';
COMMENT ON COLUMN public.checklist_items.priority IS 'Verification urgency: low, medium, high, urgent';
COMMENT ON COLUMN public.checklist_items.status IS 'Task status: pending, in_progress, completed, skipped';

-- ------------------------------------------------------------------------------
-- Trigger Function for PostgreSQL 14 Checklist Integrity (Top-Level Definition)
-- Prevents linking an issue from one session to a checklist item in another.
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.check_checklist_item_issue_session()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.issue_id IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1 FROM public.issues 
            WHERE id = NEW.issue_id AND session_id = NEW.session_id
        ) THEN
            RAISE EXCEPTION 'Cross-session constraint violation: issue_id % does not belong to session_id %', 
                NEW.issue_id, NEW.session_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ------------------------------------------------------------------------------
-- Adaptive Foreign Key Configuration for checklist_items.issue_id:
-- In PG 15+: Uses native column-specific ON DELETE SET NULL (issue_id) on the composite key.
-- In PG 14: Uses single-column ON DELETE SET NULL on issue_id, combined with the cross-session validation trigger.
-- In both cases: Deleting an issue sets issue_id to NULL while strictly preserving session_id.
-- Procedural block contains ONLY dynamic SQL and procedural logic (no nested CREATE FUNCTION).
-- ------------------------------------------------------------------------------
DO $$
DECLARE
    pg_version_num INTEGER;
BEGIN
    SELECT current_setting('server_version_num')::integer INTO pg_version_num;

    IF pg_version_num >= 150000 THEN
        -- PostgreSQL 15+ supports column-specific SET NULL on composite keys
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint 
            WHERE conname = 'fk_checklist_items_issue' 
              AND conrelid = 'public.checklist_items'::regclass
        ) THEN
            EXECUTE '
                ALTER TABLE public.checklist_items 
                ADD CONSTRAINT fk_checklist_items_issue 
                FOREIGN KEY (issue_id, session_id) 
                REFERENCES public.issues(id, session_id) 
                ON DELETE SET NULL (issue_id)';
        END IF;
    ELSE
        -- PostgreSQL 14 and earlier:
        -- Single-column FK safely sets ONLY issue_id to NULL upon issue deletion (preserving session_id)
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint 
            WHERE conname = 'fk_checklist_items_issue' 
              AND conrelid = 'public.checklist_items'::regclass
        ) THEN
            EXECUTE '
                ALTER TABLE public.checklist_items 
                ADD CONSTRAINT fk_checklist_items_issue 
                FOREIGN KEY (issue_id) 
                REFERENCES public.issues(id) 
                ON DELETE SET NULL';
        END IF;

        -- Attach the cross-session validation trigger
        DROP TRIGGER IF EXISTS trg_checklist_item_issue_session ON public.checklist_items;
        CREATE TRIGGER trg_checklist_item_issue_session
            BEFORE INSERT OR UPDATE OF issue_id, session_id ON public.checklist_items
            FOR EACH ROW
            EXECUTE FUNCTION public.check_checklist_item_issue_session();
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_checklist_items_session_id ON public.checklist_items(session_id);
CREATE INDEX IF NOT EXISTS idx_checklist_items_user_id ON public.checklist_items(user_id);
CREATE INDEX IF NOT EXISTS idx_checklist_items_issue_id ON public.checklist_items(issue_id);
CREATE INDEX IF NOT EXISTS idx_checklist_items_status ON public.checklist_items(session_id, status);
CREATE INDEX IF NOT EXISTS idx_checklist_items_priority ON public.checklist_items(session_id, priority);

DROP TRIGGER IF EXISTS set_checklist_items_updated_at ON public.checklist_items;
CREATE TRIGGER set_checklist_items_updated_at
    BEFORE UPDATE ON public.checklist_items
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_updated_at();

ALTER TABLE public.checklist_items ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own checklist items" ON public.checklist_items;
CREATE POLICY "Users can view own checklist items"
    ON public.checklist_items FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own checklist items" ON public.checklist_items;
CREATE POLICY "Users can insert own checklist items"
    ON public.checklist_items FOR INSERT
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update own checklist items" ON public.checklist_items;
CREATE POLICY "Users can update own checklist items"
    ON public.checklist_items FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own checklist items" ON public.checklist_items;
CREATE POLICY "Users can delete own checklist items"
    ON public.checklist_items FOR DELETE
    USING (auth.uid() = user_id);


-- ==============================================================================
-- Table 6: public.reports
-- Synthesized research summary reports and analytical completeness scores
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL DEFAULT 'Research Synthesis Report',
    executive_summary TEXT NOT NULL,
    coverage_score INTEGER NOT NULL DEFAULT 0 CHECK (coverage_score >= 0 AND coverage_score <= 100),
    total_claims INTEGER NOT NULL DEFAULT 0 CHECK (total_claims >= 0),
    verified_claims INTEGER NOT NULL DEFAULT 0 CHECK (verified_claims >= 0),
    conflicting_claims INTEGER NOT NULL DEFAULT 0 CHECK (conflicting_claims >= 0),
    unbacked_claims INTEGER NOT NULL DEFAULT 0 CHECK (unbacked_claims >= 0),
    identified_gaps INTEGER NOT NULL DEFAULT 0 CHECK (identified_gaps >= 0),
    findings JSONB NOT NULL DEFAULT '{}'::jsonb,
    recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(50) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'final', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Cross-user integrity constraint: session_id and user_id must match parent session
    CONSTRAINT fk_reports_session FOREIGN KEY (session_id, user_id) 
        REFERENCES public.research_sessions(id, user_id) ON DELETE CASCADE,

    -- Relational anchor for downstream referencing
    CONSTRAINT uq_reports_id_session UNIQUE (id, session_id)
);

COMMENT ON TABLE public.reports IS 'Stores final synthesized research summaries, coverage metrics, and gap findings.';
COMMENT ON COLUMN public.reports.coverage_score IS 'Completeness score (0-100) reflecting verified criteria';
COMMENT ON COLUMN public.reports.status IS 'Report state: draft, final, archived';

CREATE INDEX IF NOT EXISTS idx_reports_session_id ON public.reports(session_id);
CREATE INDEX IF NOT EXISTS idx_reports_user_id ON public.reports(user_id);
CREATE INDEX IF NOT EXISTS idx_reports_created_at ON public.reports(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reports_status ON public.reports(session_id, status);

DROP TRIGGER IF EXISTS set_reports_updated_at ON public.reports;
CREATE TRIGGER set_reports_updated_at
    BEFORE UPDATE ON public.reports
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_updated_at();

ALTER TABLE public.reports ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own reports" ON public.reports;
CREATE POLICY "Users can view own reports"
    ON public.reports FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own reports" ON public.reports;
CREATE POLICY "Users can insert own reports"
    ON public.reports FOR INSERT
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update own reports" ON public.reports;
CREATE POLICY "Users can update own reports"
    ON public.reports FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own reports" ON public.reports;
CREATE POLICY "Users can delete own reports"
    ON public.reports FOR DELETE
    USING (auth.uid() = user_id);


-- ------------------------------------------------------------------------------
-- Step 7: Post-Migration Validation Check
-- Confirms that all 8 tables are present with RLS active before committing.
-- ------------------------------------------------------------------------------
DO $$
DECLARE
    expected_tables TEXT[] := ARRAY[
        'research_sessions', 'research_sources', 'expected_fields', 
        'claims', 'issues', 'issue_evidence', 'checklist_items', 'reports'
    ];
    tbl TEXT;
    rls_active BOOLEAN;
BEGIN
    FOREACH tbl IN ARRAY expected_tables LOOP
        SELECT rowsecurity INTO rls_active 
        FROM pg_tables 
        WHERE schemaname = 'public' AND tablename = tbl;

        IF rls_active IS NULL THEN
            RAISE EXCEPTION 'Post-migration assertion failed: Table public.% was not created.', tbl;
        ELSIF NOT rls_active THEN
            RAISE EXCEPTION 'Post-migration assertion failed: Row Level Security is NOT enabled on public.%.', tbl;
        END IF;
    END LOOP;
END $$;

COMMIT;
