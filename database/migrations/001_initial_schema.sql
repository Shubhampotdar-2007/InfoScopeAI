-- ==============================================================================
-- InfoScope AI — Stage 1 & 2: Initial Schema Migration
-- Migration ID: 001_initial_schema
-- Tables: public.research_sessions, public.research_sources
-- Row Level Security (RLS) enabled with user isolation policies
-- Compatible with Supabase PostgreSQL (auth.users)
-- ==============================================================================

-- Enable UUID extension if not already present
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 1. Create research_sessions table
CREATE TABLE IF NOT EXISTS public.research_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL DEFAULT 'Untitled Research Session',
    research_query TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'collecting', 'analyzing', 'completed', 'failed')),
    search_provider VARCHAR(50) NOT NULL DEFAULT 'tavily' CHECK (search_provider IN ('tavily', 'both', 'openrouter')),
    search_metadata JSONB DEFAULT '{}'::jsonb,
    summary TEXT,
    coverage_score INTEGER CHECK (coverage_score >= 0 AND coverage_score <= 100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- Idempotent column additions for existing installations
ALTER TABLE public.research_sessions 
    ADD COLUMN IF NOT EXISTS search_provider VARCHAR(50) NOT NULL DEFAULT 'tavily';

ALTER TABLE public.research_sessions 
    ADD COLUMN IF NOT EXISTS search_metadata JSONB DEFAULT '{}'::jsonb;

-- Add column comments for documentation
COMMENT ON TABLE public.research_sessions IS 'Stores multi-source research queries, status, coverage scores, and gap detection summaries.';
COMMENT ON COLUMN public.research_sessions.id IS 'Unique identifier for the research session';
COMMENT ON COLUMN public.research_sessions.user_id IS 'Owner of the research session, references Supabase auth.users(id)';
COMMENT ON COLUMN public.research_sessions.research_query IS 'The core topic or query investigated by InfoScope AI';
COMMENT ON COLUMN public.research_sessions.status IS 'Current session lifecycle status: pending, collecting, analyzing, completed, failed';
COMMENT ON COLUMN public.research_sessions.search_provider IS 'Search provider: tavily';
COMMENT ON COLUMN public.research_sessions.search_metadata IS 'Provider-specific execution statuses, result counts, and non-sensitive diagnostics';
COMMENT ON COLUMN public.research_sessions.coverage_score IS 'Calculated information completeness score (0-100)';

-- 2. Indexes for research_sessions
CREATE INDEX IF NOT EXISTS idx_research_sessions_user_id ON public.research_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_research_sessions_created_at ON public.research_sessions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_research_sessions_status ON public.research_sessions(status);
CREATE INDEX IF NOT EXISTS idx_research_sessions_provider ON public.research_sessions(search_provider);

-- 3. Automatic updated_at trigger function
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = timezone('utc'::text, now());
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS set_research_sessions_updated_at ON public.research_sessions;
CREATE TRIGGER set_research_sessions_updated_at
    BEFORE UPDATE ON public.research_sessions
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_updated_at();

-- 4. Enable Row Level Security (RLS) on research_sessions
ALTER TABLE public.research_sessions ENABLE ROW LEVEL SECURITY;

-- 5. RLS Policies for research_sessions (User Isolation)
DROP POLICY IF EXISTS "Users can view own research sessions" ON public.research_sessions;
CREATE POLICY "Users can view own research sessions"
    ON public.research_sessions
    FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own research sessions" ON public.research_sessions;
CREATE POLICY "Users can insert own research sessions"
    ON public.research_sessions
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update own research sessions" ON public.research_sessions;
CREATE POLICY "Users can update own research sessions"
    ON public.research_sessions
    FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own research sessions" ON public.research_sessions;
CREATE POLICY "Users can delete own research sessions"
    ON public.research_sessions
    FOR DELETE
    USING (auth.uid() = user_id);


-- ==============================================================================
-- 6. Create research_sources table (Stage 2: Source Ingestion & Attribution)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.research_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.research_sessions(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT 'Untitled Source',
    snippet TEXT,
    score NUMERIC,
    providers TEXT[] NOT NULL DEFAULT ARRAY['tavily']::TEXT[],
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

COMMENT ON TABLE public.research_sources IS 'Stores normalized web and URL research sources with provider attribution.';
COMMENT ON COLUMN public.research_sources.providers IS 'Search providers returning this source: e.g. {tavily}';
COMMENT ON COLUMN public.research_sources.canonical_url IS 'Canonicalized URL used for cross-provider deduplication';

-- Indexes for research_sources
CREATE INDEX IF NOT EXISTS idx_research_sources_session_id ON public.research_sources(session_id);
CREATE INDEX IF NOT EXISTS idx_research_sources_user_id ON public.research_sources(user_id);
CREATE INDEX IF NOT EXISTS idx_research_sources_canonical_url ON public.research_sources(session_id, canonical_url);

-- Enable RLS on research_sources
ALTER TABLE public.research_sources ENABLE ROW LEVEL SECURITY;

-- RLS Policies for research_sources (User Isolation)
DROP POLICY IF EXISTS "Users can view own research sources" ON public.research_sources;
CREATE POLICY "Users can view own research sources"
    ON public.research_sources
    FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own research sources" ON public.research_sources;
CREATE POLICY "Users can insert own research sources"
    ON public.research_sources
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update own research sources" ON public.research_sources;
CREATE POLICY "Users can update own research sources"
    ON public.research_sources
    FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own research sources" ON public.research_sources;
CREATE POLICY "Users can delete own research sources"
    ON public.research_sources
    FOR DELETE
    USING (auth.uid() = user_id);
