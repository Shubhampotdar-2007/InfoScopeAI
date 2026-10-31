-- ==============================================================================
-- InfoScope AI — Database Schema
-- Table: research_sessions
-- Row Level Security (RLS) enabled with user isolation policies
-- Compatible with Supabase PostgreSQL (auth.users)
-- ==============================================================================

-- Enable UUID extension if not already present
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Drop table if needing clean migration in development (optional, commented out for safety)
-- DROP TABLE IF EXISTS public.research_sessions CASCADE;

-- 1. Create research_sessions table
CREATE TABLE IF NOT EXISTS public.research_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL DEFAULT 'Untitled Research Session',
    research_query TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'collecting', 'analyzing', 'completed', 'failed')),
    summary TEXT,
    coverage_score INTEGER CHECK (coverage_score >= 0 AND coverage_score <= 100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- Add column comments for documentation
COMMENT ON TABLE public.research_sessions IS 'Stores multi-source research queries, status, coverage scores, and gap detection summaries.';
COMMENT ON COLUMN public.research_sessions.id IS 'Unique identifier for the research session';
COMMENT ON COLUMN public.research_sessions.user_id IS 'Owner of the research session, references Supabase auth.users(id)';
COMMENT ON COLUMN public.research_sessions.research_query IS 'The core topic or query investigated by InfoScope AI';
COMMENT ON COLUMN public.research_sessions.status IS 'Current session lifecycle status: pending, collecting, analyzing, completed, failed';
COMMENT ON COLUMN public.research_sessions.coverage_score IS 'Calculated information completeness score (0-100)';

-- 2. Indexes for performance
CREATE INDEX IF NOT EXISTS idx_research_sessions_user_id ON public.research_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_research_sessions_created_at ON public.research_sessions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_research_sessions_status ON public.research_sessions(status);

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

-- 4. Enable Row Level Security (RLS)
ALTER TABLE public.research_sessions ENABLE ROW LEVEL SECURITY;

-- 5. RLS Policies (User Isolation)
-- Policy 1: Users can view only their own research sessions
CREATE POLICY "Users can view own research sessions"
    ON public.research_sessions
    FOR SELECT
    USING (auth.uid() = user_id);

-- Policy 2: Users can insert their own research sessions
CREATE POLICY "Users can insert own research sessions"
    ON public.research_sessions
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Policy 3: Users can update their own research sessions
CREATE POLICY "Users can update own research sessions"
    ON public.research_sessions
    FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Policy 4: Users can delete their own research sessions
CREATE POLICY "Users can delete own research sessions"
    ON public.research_sessions
    FOR DELETE
    USING (auth.uid() = user_id);
