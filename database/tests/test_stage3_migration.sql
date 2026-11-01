-- ==============================================================================
-- InfoScope AI — Stage 3: Schema & Relational Integrity Verification Suite
-- Test File: database/tests/test_stage3_migration.sql
--
-- Safety Guarantees:
--   - Executed within an explicit transaction (BEGIN ... ROLLBACK).
--   - Automatically rolls back at the end; NEVER alters production data.
--   - Safely runnable in the Supabase SQL Editor as a single batch.
--   - Requires two existing Supabase Auth accounts in auth.users; never modifies,
--     creates, or deletes auth users.
--   - Row Level Security (RLS) Scope:
--     * Functionally tested on research_sessions (tenant isolation and WITH CHECK).
--     * The six new tables (expected_fields, claims, issues, issue_evidence,
--       checklist_items, reports) have RLS enabled and configured via migration,
--       but this test suite does not independently exercise every individual policy.
--   - Uses specific exception handling; unexpected errors propagate immediately.
--   - GUC-based context lifecycle: Retains fixture IDs across DO blocks and role
--     switches via transaction-local PostgreSQL settings (set_config/current_setting),
--     completely eliminating dependencies on temporary tables.
-- ==============================================================================

BEGIN;

-- ------------------------------------------------------------------------------
-- 1. Setup Test Fixtures & Run Integrity Tests
-- (Executes as privileged role to set up data and verify foreign key behaviors)
-- ------------------------------------------------------------------------------
DO $$
DECLARE
    user1_id UUID;
    user2_id UUID;
    session1_id UUID := gen_random_uuid();
    session2_id UUID := gen_random_uuid();
    source1_id  UUID := gen_random_uuid();
    source2_id  UUID := gen_random_uuid();
    field1_id   UUID := gen_random_uuid();
    claim1_id   UUID := gen_random_uuid();
    issue1_id   UUID := gen_random_uuid();
    iss2_id     UUID := gen_random_uuid();
    evid1_id    UUID := gen_random_uuid();
    check1_id   UUID := gen_random_uuid();
    report1_id  UUID := gen_random_uuid();

    temp_issue_id UUID;
    temp_session_id UUID;
    test_passed BOOLEAN;
BEGIN
    RAISE NOTICE '==============================================================';
    RAISE NOTICE 'BEGINNING STAGE 3 MIGRATION TEST SUITE';
    RAISE NOTICE 'Scope: Relational integrity, FK cascades, cross-session rules.';
    RAISE NOTICE 'RLS Scope: Functionally testing research_sessions tenant isolation.';
    RAISE NOTICE 'Note: Six child tables have RLS enabled/configured in schema,';
    RAISE NOTICE '      but are not independently exercised in this suite.';
    RAISE NOTICE '==============================================================';

    -- Step 1.1: Retrieve two distinct existing users from auth.users for multi-user isolation testing.
    -- Strict Requirement: Never create, modify, or delete records in auth.users.
    SELECT id INTO user1_id FROM auth.users ORDER BY created_at ASC LIMIT 1;
    SELECT id INTO user2_id FROM auth.users WHERE id <> user1_id ORDER BY created_at ASC LIMIT 1;

    IF user1_id IS NULL OR user2_id IS NULL THEN
        RAISE EXCEPTION 'Stage 3 test suite requires at least two existing Supabase Auth users in auth.users for two-user RLS testing. Please ensure at least two test accounts exist before running this script. No auth users were created, modified, or deleted.';
    END IF;

    RAISE NOTICE 'Found existing auth.users in database. Using test user IDs: % and %', user1_id, user2_id;

    -- Store resolved IDs in transaction-local GUC settings for downstream RLS tests.
    -- Eliminates temporary table dependencies and survives role changes across poolers.
    PERFORM set_config('test_stage3.u1_id', user1_id::text, true);
    PERFORM set_config('test_stage3.u2_id', user2_id::text, true);
    PERFORM set_config('test_stage3.s1_id', session1_id::text, true);
    PERFORM set_config('test_stage3.s2_id', session2_id::text, true);
    PERFORM set_config('test_stage3.src1_id', source1_id::text, true);
    PERFORM set_config('test_stage3.src2_id', source2_id::text, true);
    PERFORM set_config('test_stage3.iss1_id', issue1_id::text, true);
    PERFORM set_config('test_stage3.iss2_id', iss2_id::text, true);
    PERFORM set_config('test_stage3.chk1_id', check1_id::text, true);
    PERFORM set_config('test_stage3.clm1_id', claim1_id::text, true);
    PERFORM set_config('test_stage3.ev1_id', evid1_id::text, true);
    PERFORM set_config('test_stage3.rep1_id', report1_id::text, true);

    -- --------------------------------------------------------------------------
    -- SCENARIO 1: Valid Insertion Across All Six Tables + Parent Tables
    -- --------------------------------------------------------------------------
    RAISE NOTICE '[Test 1] Testing valid inserts into all tables...';

    -- Parent: research_sessions
    INSERT INTO public.research_sessions (id, user_id, title, research_query, status)
    VALUES (session1_id, user1_id, 'Test Session 1', 'AI Gap Analysis Investigation', 'pending');

    -- Parent: research_sources
    INSERT INTO public.research_sources (id, session_id, user_id, url, canonical_url, title)
    VALUES (source1_id, session1_id, user1_id, 'https://example.com/spec', 'https://example.com/spec', 'Official Spec');

    -- Table 1: expected_fields
    INSERT INTO public.expected_fields (id, session_id, user_id, field_name, field_category, weight)
    VALUES (field1_id, session1_id, user1_id, 'Pricing Model', 'pricing', 2.0);

    -- Table 2: claims
    INSERT INTO public.claims (id, session_id, source_id, user_id, claim_text, confidence_score, status)
    VALUES (claim1_id, session1_id, source1_id, user1_id, 'Enterprise plan starts at $500/mo', 0.95, 'verified');

    -- Table 3: issues
    INSERT INTO public.issues (id, session_id, user_id, issue_type, severity, title, description)
    VALUES (issue1_id, session1_id, user1_id, 'contradiction', 'high', 'Pricing Conflict', 'Source A states $500 while Source B states $400');

    -- Table 4: issue_evidence
    INSERT INTO public.issue_evidence (id, session_id, issue_id, claim_id, source_id, user_id, polarity, evidence_text)
    VALUES (evid1_id, session1_id, issue1_id, claim1_id, source1_id, user1_id, 'supports', 'Enterprise tier starts at $500 per seat');

    -- Table 5: checklist_items
    INSERT INTO public.checklist_items (id, session_id, user_id, issue_id, task_description, priority)
    VALUES (check1_id, session1_id, user1_id, issue1_id, 'Verify enterprise pricing on official portal', 'high');

    -- Table 6: reports
    INSERT INTO public.reports (id, session_id, user_id, title, executive_summary, coverage_score)
    VALUES (report1_id, session1_id, user1_id, 'Synthesis 1', 'Investigation complete with 1 pricing issue.', 85);

    RAISE NOTICE '[Test 1 PASSED] All tables accepted valid relational inserts.';


    -- --------------------------------------------------------------------------
    -- SCENARIO 2: Cross-User Insertion Attempts (Must Fail)
    -- --------------------------------------------------------------------------
    RAISE NOTICE '[Test 2] Testing cross-user integrity constraints...';

    -- Attempt 2.1: Insert a claim for Session 1 (User 1) using User 2's ID
    test_passed := FALSE;
    BEGIN
        INSERT INTO public.claims (session_id, source_id, user_id, claim_text)
        VALUES (session1_id, source1_id, user2_id, 'Cross-user claim attempt');
    EXCEPTION WHEN foreign_key_violation THEN
        test_passed := TRUE;
    END;
    IF NOT test_passed THEN
        RAISE EXCEPTION '[Test 2.1 FAILED] Foreign key allowed child claim with user_id mismatching parent session!';
    END IF;

    -- Attempt 2.2: Insert a source for Session 1 (User 1) using User 2's ID
    test_passed := FALSE;
    BEGIN
        INSERT INTO public.research_sources (session_id, user_id, url, canonical_url, title)
        VALUES (session1_id, user2_id, 'https://cross-user.com', 'https://cross-user.com', 'Cross Source');
    EXCEPTION WHEN foreign_key_violation THEN
        test_passed := TRUE;
    END;
    IF NOT test_passed THEN
        RAISE EXCEPTION '[Test 2.2 FAILED] Foreign key allowed research_source with user_id mismatching parent session!';
    END IF;

    -- Attempt 2.3: Insert an issue for Session 1 (User 1) using User 2's ID
    test_passed := FALSE;
    BEGIN
        INSERT INTO public.issues (session_id, user_id, issue_type, title, description)
        VALUES (session1_id, user2_id, 'gap', 'Cross-user issue', 'Description');
    EXCEPTION WHEN foreign_key_violation THEN
        test_passed := TRUE;
    END;
    IF NOT test_passed THEN
        RAISE EXCEPTION '[Test 2.3 FAILED] Foreign key allowed issue with user_id mismatching parent session!';
    END IF;

    RAISE NOTICE '[Test 2 PASSED] Cross-user insertion attempts correctly rejected.';


    -- --------------------------------------------------------------------------
    -- SCENARIO 3: Cross-Session Relationship Attempts (Must Fail)
    -- --------------------------------------------------------------------------
    RAISE NOTICE '[Test 3] Testing cross-session relationship constraints...';

    -- Create Session 2 owned by User 1
    INSERT INTO public.research_sessions (id, user_id, title, research_query)
    VALUES (session2_id, user1_id, 'Test Session 2', 'Second investigation');

    -- Create Source 2 in Session 2
    INSERT INTO public.research_sources (id, session_id, user_id, url, canonical_url, title)
    VALUES (source2_id, session2_id, user1_id, 'https://session2.com', 'https://session2.com', 'Source 2');

    -- Attempt 3.1: Insert a Claim in Session 1 referencing Source 2 (which belongs to Session 2)
    test_passed := FALSE;
    BEGIN
        INSERT INTO public.claims (session_id, source_id, user_id, claim_text)
        VALUES (session1_id, source2_id, user1_id, 'Claim linking to external session source');
    EXCEPTION WHEN foreign_key_violation THEN
        test_passed := TRUE;
    END;
    IF NOT test_passed THEN
        RAISE EXCEPTION '[Test 3.1 FAILED] Claim was allowed to reference a source from a different session!';
    END IF;

    -- Attempt 3.2: Insert an IssueEvidence in Session 1 referencing an Issue from Session 2
    INSERT INTO public.issues (id, session_id, user_id, issue_type, title, description)
    VALUES (iss2_id, session2_id, user1_id, 'gap', 'Session 2 Issue', 'Desc');

    test_passed := FALSE;
    BEGIN
        INSERT INTO public.issue_evidence (session_id, issue_id, source_id, user_id, polarity, evidence_text)
        VALUES (session1_id, iss2_id, source1_id, user1_id, 'supports', 'Evidence bridging two sessions');
    EXCEPTION WHEN foreign_key_violation THEN
        test_passed := TRUE;
    END;
    IF NOT test_passed THEN
        RAISE EXCEPTION '[Test 3.2 FAILED] Issue evidence was allowed to reference an issue from another session!';
    END IF;

    -- Attempt 3.3: Insert a ChecklistItem in Session 1 referencing an Issue from Session 2
    test_passed := FALSE;
    BEGIN
        INSERT INTO public.checklist_items (session_id, user_id, issue_id, task_description)
        VALUES (session1_id, user1_id, iss2_id, 'Checklist item with cross-session issue');
    EXCEPTION WHEN foreign_key_violation THEN
        test_passed := TRUE;
    END;
    IF NOT test_passed THEN
        RAISE EXCEPTION '[Test 3.3 FAILED] Checklist item was allowed to reference an issue from another session!';
    END IF;

    RAISE NOTICE '[Test 3 PASSED] Cross-session relational mismatches rejected.';


    -- --------------------------------------------------------------------------
    -- SCENARIO 5: Deleting a Research Source with Dependent Claims and Evidence
    -- Expected behavior: Source deletion cascades to claims and issue_evidence, but preserves the session.
    -- Note: Executed before Scenario 4 so claim1_id and evid1_id still exist when source1_id is deleted.
    -- --------------------------------------------------------------------------
    RAISE NOTICE '[Test 5] Testing cascade deletion on research sources...';

    -- Delete source1_id while dependent claim1_id and evid1_id still exist
    DELETE FROM public.research_sources WHERE id = source1_id;

    -- Assert claims referencing source1_id were deleted
    IF EXISTS (SELECT 1 FROM public.claims WHERE id = claim1_id) THEN
        RAISE EXCEPTION '[Test 5 FAILED] Claim was not cascade-deleted when its source was removed!';
    END IF;

    -- Assert evidence referencing source1_id was deleted
    IF EXISTS (SELECT 1 FROM public.issue_evidence WHERE id = evid1_id) THEN
        RAISE EXCEPTION '[Test 5 FAILED] Issue evidence was not cascade-deleted when its source was removed!';
    END IF;

    -- Assert session still exists
    IF NOT EXISTS (SELECT 1 FROM public.research_sessions WHERE id = session1_id) THEN
        RAISE EXCEPTION '[Test 5 FAILED] Parent research session was unexpectedly deleted!';
    END IF;

    RAISE NOTICE '[Test 5 PASSED] Cascade deletion successfully cleaned up claims and evidence while preserving session.';


    -- --------------------------------------------------------------------------
    -- SCENARIO 4: Deleting an Issue Linked to a Checklist Item
    -- Expected behavior: Checklist item is preserved, session_id is preserved, issue_id becomes NULL.
    -- --------------------------------------------------------------------------
    RAISE NOTICE '[Test 4] Testing issue deletion and checklist_items preservation...';

    -- Delete the issue
    DELETE FROM public.issues WHERE id = issue1_id;

    -- Query checklist item
    SELECT issue_id, session_id INTO temp_issue_id, temp_session_id
    FROM public.checklist_items
    WHERE id = check1_id;

    -- Explicitly verify checklist item was not deleted
    IF NOT FOUND THEN
        RAISE EXCEPTION '[Test 4 FAILED] Checklist item was unexpectedly deleted when parent issue was removed!';
    END IF;

    -- Verify issue_id was set to NULL
    IF temp_issue_id IS NOT NULL THEN
        RAISE EXCEPTION '[Test 4 FAILED] Checklist item issue_id was not set to NULL upon issue deletion! Value: %', temp_issue_id;
    END IF;

    -- Verify session_id remains intact and matches original session
    IF temp_session_id IS NULL OR temp_session_id <> session1_id THEN
        RAISE EXCEPTION '[Test 4 FAILED] Checklist item session_id was corrupted or lost! Expected %, got %', session1_id, temp_session_id;
    END IF;

    RAISE NOTICE '[Test 4 PASSED] Issue deletion preserved checklist_items row and set issue_id to NULL while keeping session_id intact.';


    -- --------------------------------------------------------------------------
    -- Prepare fixtures for SCENARIO 6 (RLS Tenant Isolation)
    -- Clean session 2 if exists, then re-insert owned by User 2
    -- --------------------------------------------------------------------------
    DELETE FROM public.research_sessions WHERE id = session2_id;
    INSERT INTO public.research_sessions (id, user_id, title, research_query)
    VALUES (session2_id, user2_id, 'User 2 Private Session', 'Confidential Research Investigation');

END $$;


-- ------------------------------------------------------------------------------
-- 2. SCENARIO 6: Genuine Row Level Security (RLS) Tenant Isolation Test
-- Executed as top-level statements using SET LOCAL ROLE authenticated.
-- Tests authentic tenant isolation under PostgreSQL RLS engine rules on research_sessions.
-- Note: The six new expansion tables have RLS enabled and configured in the migration,
-- but this test specifically exercises RLS policies on research_sessions.
-- ------------------------------------------------------------------------------

-- Switch database role to authenticated
SET LOCAL ROLE authenticated;

-- Execute genuine RLS tenant isolation assertions
DO $$
DECLARE
    u1 UUID := current_setting('test_stage3.u1_id')::uuid;
    u2 UUID := current_setting('test_stage3.u2_id')::uuid;
    s1 UUID := current_setting('test_stage3.s1_id')::uuid;
    s2 UUID := current_setting('test_stage3.s2_id')::uuid;
    visible_count INTEGER;
    cross_insert_failed BOOLEAN := FALSE;
BEGIN
    -- --------------------------------------------------------------------------
    -- Step 2.1: Impersonate User 1 via Supabase auth claims
    -- --------------------------------------------------------------------------
    PERFORM set_config('request.jwt.claim.sub', u1::text, true);
    PERFORM set_config('request.jwt.claims', json_build_object('sub', u1::text, 'role', 'authenticated')::text, true);

    -- User 1 must see Session 1
    SELECT COUNT(*) INTO visible_count FROM public.research_sessions WHERE id = s1;
    IF visible_count <> 1 THEN
        RAISE EXCEPTION '[Test 6.1 FAILED] RLS blocked User 1 from viewing their own research session!';
    END IF;

    -- User 1 must NOT see Session 2
    SELECT COUNT(*) INTO visible_count FROM public.research_sessions WHERE id = s2;
    IF visible_count <> 0 THEN
        RAISE EXCEPTION '[Test 6.2 FAILED] RLS leaked User 2 research session to User 1!';
    END IF;

    -- --------------------------------------------------------------------------
    -- Step 2.2: Impersonate User 2 via Supabase auth claims
    -- --------------------------------------------------------------------------
    PERFORM set_config('request.jwt.claim.sub', u2::text, true);
    PERFORM set_config('request.jwt.claims', json_build_object('sub', u2::text, 'role', 'authenticated')::text, true);

    -- User 2 must see Session 2
    SELECT COUNT(*) INTO visible_count FROM public.research_sessions WHERE id = s2;
    IF visible_count <> 1 THEN
        RAISE EXCEPTION '[Test 6.3 FAILED] RLS blocked User 2 from viewing their own research session!';
    END IF;

    -- User 2 must NOT see Session 1
    SELECT COUNT(*) INTO visible_count FROM public.research_sessions WHERE id = s1;
    IF visible_count <> 0 THEN
        RAISE EXCEPTION '[Test 6.4 FAILED] RLS leaked User 1 research session to User 2!';
    END IF;

    -- --------------------------------------------------------------------------
    -- Step 2.3: Scenario 6.5 - User 2 cannot insert a row claiming User 1 ownership
    -- Verify that the authenticated role has table-level INSERT permission before testing RLS.
    -- This prevents a missing table privilege from masquerading as a successful RLS check.
    -- --------------------------------------------------------------------------
    IF NOT has_table_privilege('authenticated', 'public.research_sessions', 'INSERT') THEN
        RAISE EXCEPTION '[Test 6.5 FAILED] Role "authenticated" lacks table-level INSERT privilege on public.research_sessions; cannot validate RLS WITH CHECK policy.';
    END IF;

    -- Execute fraudulent insert and verify rejection specifically by RLS WITH CHECK policy
    BEGIN
        INSERT INTO public.research_sessions (id, user_id, title, research_query)
        VALUES (gen_random_uuid(), u1, 'Fraudulent Session', 'Should be blocked by RLS WITH CHECK');
    EXCEPTION WHEN insufficient_privilege THEN
        IF SQLERRM LIKE '%row-level security policy%' THEN
            cross_insert_failed := TRUE;
        ELSE
            RAISE EXCEPTION '[Test 6.5 FAILED] Insert was rejected due to table privilege denial rather than RLS WITH CHECK policy: %', SQLERRM;
        END IF;
    END;

    IF NOT cross_insert_failed THEN
        RAISE EXCEPTION '[Test 6.5 FAILED] RLS WITH CHECK allowed User 2 to insert a session owned by User 1!';
    END IF;

    RAISE NOTICE '[Test 6 PASSED] Genuine Row Level Security tenant isolation verified on research_sessions under authenticated role.';
    RAISE NOTICE 'Note: Six child tables have RLS enabled and configured in schema.';
    RAISE NOTICE '==============================================================';
    RAISE NOTICE 'ALL STAGE 3 MIGRATION TESTS PASSED SUCCESSFULLY!';
    RAISE NOTICE '==============================================================';
END $$;

-- Safely restore the original role
RESET ROLE;

-- Explicitly rollback all changes to ensure test execution is 100% side-effect free
ROLLBACK;
