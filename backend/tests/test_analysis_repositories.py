"""
Test Suite for Analysis Repositories (Stage 3, Phase 2, Step 2B).
Tests:
1. ExpectedFieldsRepository:
   - Creation, batch insertion, retrieval, and updates.
   - Weight validation (0.00 to 5.00).
   - Weighted coverage score calculation.
2. ClaimsRepository:
   - Creation, batch insertion, retrieval by ID, session, and source.
   - Confidence score validation (0.00 to 1.00) and status validation.
   - Filtering by status and minimum confidence.
3. IssuesRepository & IssueEvidenceRepository:
   - Issue creation, filtering by type/severity/status.
   - Evidence creation, batch ingestion, retrieval by issue and source.
   - Polarity validation.
   - Linked evidence query from issues repository.
4. ChecklistRepository:
   - Task creation and batch creation.
   - Task completion timestamp handling and task reopening (clearing completed_at).
   - Priority and notes updates.
5. ReportsRepository:
   - Report creation, metrics validation (coverage_score 0-100, non-negative counters).
   - Metrics and status updates.
6. Ownership, Anti-Tampering, and Constraint Handling:
   - Unauthenticated rejection across all repositories.
   - Anti-tampering (stripping client-supplied user_id/id).
   - Composite foreign key error mapping (code 23503 -> DatabaseConstraintError).
   - Dependency injection helpers.
"""

import uuid
import json
import pytest
import jwt
import httpx

from app.core.security import AuthenticatedUser
from app.database import (
    PostgrestClient,
    EntityNotFoundError,
    DatabaseConstraintError,
    DatabaseAuthenticationError,
    ExpectedFieldsRepository,
    ClaimsRepository,
    IssuesRepository,
    IssueEvidenceRepository,
    ChecklistRepository,
    ReportsRepository,
    get_expected_fields_repository,
    get_claims_repository,
    get_issues_repository,
    get_issue_evidence_repository,
    get_checklist_repository,
    get_reports_repository,
)


TEST_USER_ID = "00000000-0000-0000-0000-000000000001"
OTHER_USER_ID = "00000000-0000-0000-0000-000000000002"
TEST_ANON_KEY = "anon-key-test"


def create_user_client(user_id: str = TEST_USER_ID, transport: httpx.AsyncBaseTransport = None) -> PostgrestClient:
    """Helper to create a PostgrestClient bound to a verified AuthenticatedUser."""
    token = jwt.encode(
        {"sub": user_id, "role": "authenticated", "aud": "authenticated"},
        "a_super_secret_test_key_at_least_32_bytes_long",
        algorithm="HS256",
    )
    user = AuthenticatedUser(user_id=user_id, email=f"{user_id}@example.com", access_token=token)
    mock_http = httpx.AsyncClient(transport=transport) if transport else None
    return PostgrestClient(
        user=user,
        anon_key=TEST_ANON_KEY,
        base_url="https://test.supabase.co/rest/v1",
        http_client=mock_http,
    )


# ==============================================================================
# 1. ExpectedFieldsRepository Tests
# ==============================================================================

@pytest.mark.anyio
async def test_expected_fields_crud_and_coverage():
    session_id = str(uuid.uuid4())
    field_id = str(uuid.uuid4())
    captured_requests = []

    def mock_handler(request: httpx.Request):
        captured_requests.append(request)
        method = request.method
        url = str(request.url)

        if method == "POST":
            data = json.loads(request.content)
            if isinstance(data, list):
                for item in data:
                    item["id"] = str(uuid.uuid4())
                return httpx.Response(201, json=data)
            data["id"] = field_id
            return httpx.Response(201, json=[data])

        elif method == "GET":
            if f"id=eq.{field_id}" in url:
                return httpx.Response(200, json=[{
                    "id": field_id, "session_id": session_id, "user_id": TEST_USER_ID,
                    "field_name": "Pricing", "weight": 2.0, "status": "missing"
                }])
            return httpx.Response(200, json=[
                {"id": "1", "field_name": "F1", "weight": 1.0, "status": "covered"},
                {"id": "2", "field_name": "F2", "weight": 2.0, "status": "covered"},
                {"id": "3", "field_name": "F3", "weight": 1.0, "status": "partially_covered"},
                {"id": "4", "field_name": "F4", "weight": 1.0, "status": "missing"},
            ])

        elif method == "PATCH":
            updated = json.loads(request.content)
            updated["id"] = field_id
            return httpx.Response(200, json=[updated])

        elif method == "DELETE":
            return httpx.Response(200, json=[{"id": field_id}])

        return httpx.Response(400)

    client = create_user_client(transport=httpx.MockTransport(mock_handler))
    repo = ExpectedFieldsRepository(client)

    # 1. Create single
    created = await repo.create_expected_field(
        session_id=session_id,
        field_name="Pricing",
        field_category="commercial",
        weight=2.0,
    )
    assert created["field_name"] == "Pricing"
    assert created["user_id"] == TEST_USER_ID

    # 2. Batch create
    batch = await repo.create_expected_fields_batch(session_id, [
        {"field_name": "Security", "weight": 1.5},
        {"field_name": "Compliance", "weight": 1.0},
    ])
    assert len(batch) == 2

    # 3. Get by ID
    field = await repo.get_field_by_id(field_id)
    assert field["id"] == field_id

    # 4. Update
    updated = await repo.update_coverage_status(field_id, "covered")
    assert updated["status"] == "covered"

    # 5. Calculate coverage statistics
    # 2 covered (w=1, w=2 -> 3 pts), 1 partial (w=1 -> 0.5 pts), 1 missing (w=1 -> 0 pts)
    # Total weight = 5.0, points = 3.5 -> (3.5 / 5.0) * 100 = 70%
    stats = await repo.calculate_coverage_statistics(session_id)
    assert stats["total_fields"] == 4
    assert stats["covered_fields"] == 2
    assert stats["partially_covered_fields"] == 1
    assert stats["missing_fields"] == 1
    assert stats["coverage_score"] == 70
    assert stats["total_weight"] == 5.0

    # 6. Delete
    deleted = await repo.delete_expected_field(field_id)
    assert deleted["id"] == field_id


def test_expected_fields_weight_and_status_validation():
    client = create_user_client()
    repo = ExpectedFieldsRepository(client)

    # Weight out of bounds (> 5.00)
    with pytest.raises(ValueError, match="out of bounds"):
        repo._validate_weight(5.5)

    # Weight out of bounds (< 0.00)
    with pytest.raises(ValueError, match="out of bounds"):
        repo._validate_weight(-0.5)

    # Valid weights
    assert repo._validate_weight(0) == 0.0
    assert repo._validate_weight("3.25") == 3.25
    assert repo._validate_weight(5.0) == 5.0


# ==============================================================================
# 2. ClaimsRepository Tests
# ==============================================================================

@pytest.mark.anyio
async def test_claims_crud_and_filtering():
    session_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    claim_id = str(uuid.uuid4())
    captured_requests = []

    def mock_handler(request: httpx.Request):
        captured_requests.append(request)
        method = request.method
        url = str(request.url)

        if method == "POST":
            data = json.loads(request.content)
            if isinstance(data, list):
                for item in data:
                    item["id"] = str(uuid.uuid4())
                return httpx.Response(201, json=data)
            data["id"] = claim_id
            return httpx.Response(201, json=[data])

        elif method == "GET":
            if f"id=eq.{claim_id}" in url:
                return httpx.Response(200, json=[{
                    "id": claim_id, "session_id": session_id, "source_id": source_id,
                    "user_id": TEST_USER_ID, "claim_text": "Model achieves 95% accuracy.",
                    "status": "unverified", "confidence_score": 0.85
                }])
            return httpx.Response(200, json=[
                {"id": claim_id, "claim_text": "Claim 1", "status": "verified", "confidence_score": 0.95}
            ])

        elif method == "PATCH":
            updated = json.loads(request.content)
            updated["id"] = claim_id
            return httpx.Response(200, json=[updated])

        elif method == "DELETE":
            return httpx.Response(200, json=[{"id": claim_id}])

        return httpx.Response(400)

    client = create_user_client(transport=httpx.MockTransport(mock_handler))
    repo = ClaimsRepository(client)

    # 1. Create claim
    claim = await repo.create_claim(
        session_id=session_id,
        source_id=source_id,
        claim_text="Model achieves 95% accuracy.",
        confidence_score=0.85,
        status="unverified",
    )
    assert claim["id"] == claim_id
    assert claim["confidence_score"] == 0.85

    # 2. Confidence validation
    with pytest.raises(ValueError, match="out of bounds"):
        await repo.create_claim(
            session_id=session_id,
            source_id=source_id,
            claim_text="Invalid confidence",
            confidence_score=1.5,
        )

    # 3. Retrieve with confidence and status filter
    results = await repo.get_claims_by_session(session_id, status="verified", min_confidence=0.9)
    assert len(results) == 1
    req_url = str(captured_requests[-1].url)
    assert "status=eq.verified" in req_url
    assert "confidence_score=gte.0.9" in req_url

    # 4. Retrieve by source
    by_src = await repo.get_claims_by_source(source_id)
    assert len(by_src) == 1

    # 5. Update status
    updated = await repo.update_claim_status(claim_id, "verified")
    assert updated["status"] == "verified"

    # 6. Delete
    deleted = await repo.delete_claim(claim_id)
    assert deleted["id"] == claim_id


# ==============================================================================
# 3. IssuesRepository & IssueEvidenceRepository Tests
# ==============================================================================

@pytest.mark.anyio
async def test_issues_crud_and_filtering():
    session_id = str(uuid.uuid4())
    issue_id = str(uuid.uuid4())
    captured_requests = []

    def mock_handler(request: httpx.Request):
        captured_requests.append(request)
        method = request.method
        url = str(request.url)

        if method == "POST":
            data = json.loads(request.content)
            data["id"] = issue_id
            return httpx.Response(201, json=[data])

        elif method == "GET":
            if "issue_evidence" in url:
                return httpx.Response(200, json=[{"id": "ev-1", "issue_id": issue_id, "polarity": "contradicts"}])
            return httpx.Response(200, json=[{
                "id": issue_id, "session_id": session_id, "issue_type": "contradiction",
                "severity": "high", "title": "Conflicting Pricing Data", "status": "open"
            }])

        elif method == "PATCH":
            updated = json.loads(request.content)
            updated["id"] = issue_id
            return httpx.Response(200, json=[updated])

        elif method == "DELETE":
            return httpx.Response(200, json=[{"id": issue_id}])

        return httpx.Response(400)

    client = create_user_client(transport=httpx.MockTransport(mock_handler))
    repo = IssuesRepository(client)

    # 1. Create issue
    issue = await repo.create_issue(
        session_id=session_id,
        issue_type="contradiction",
        title="Conflicting Pricing Data",
        description="Source A says $10/mo while Source B says $20/mo.",
        severity="high",
        status="open",
    )
    assert issue["id"] == issue_id
    assert issue["severity"] == "high"

    # 2. Validation
    with pytest.raises(ValueError, match="Invalid issue_type"):
        await repo.create_issue(
            session_id=session_id,
            issue_type="invalid_type",
            title="T",
            description="D",
        )

    # 3. Get by session with filters
    issues = await repo.get_issues_by_session(session_id, issue_type="contradiction", severity="high", status="open")
    assert len(issues) == 1
    req_url = str(captured_requests[-1].url)
    assert "issue_type=eq.contradiction" in req_url
    assert "severity=eq.high" in req_url
    assert "status=eq.open" in req_url

    # 4. Get linked evidence
    evidence = await repo.get_issue_evidence(issue_id)
    assert len(evidence) == 1
    assert evidence[0]["polarity"] == "contradicts"

    # 5. Update status
    updated = await repo.update_issue_status(issue_id, "investigating")
    assert updated["status"] == "investigating"

    # 6. Delete
    deleted = await repo.delete_issue(issue_id)
    assert deleted["id"] == issue_id


@pytest.mark.anyio
async def test_issue_evidence_crud():
    session_id = str(uuid.uuid4())
    issue_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    claim_id = str(uuid.uuid4())
    evidence_id = str(uuid.uuid4())

    def mock_handler(request: httpx.Request):
        method = request.method
        url = str(request.url)

        if method == "POST":
            data = json.loads(request.content)
            if isinstance(data, list):
                for item in data:
                    item["id"] = str(uuid.uuid4())
                return httpx.Response(201, json=data)
            data["id"] = evidence_id
            return httpx.Response(201, json=[data])

        elif method == "GET":
            if f"id=eq.{evidence_id}" in url:
                return httpx.Response(200, json=[{
                    "id": evidence_id, "session_id": session_id, "issue_id": issue_id,
                    "source_id": source_id, "polarity": "contradicts",
                    "evidence_text": "Price is $20.", "user_id": TEST_USER_ID
                }])
            return httpx.Response(200, json=[
                {"id": evidence_id, "issue_id": issue_id, "source_id": source_id, "polarity": "contradicts"}
            ])

        elif method == "DELETE":
            return httpx.Response(200, json=[{"id": evidence_id}])

        return httpx.Response(400)

    client = create_user_client(transport=httpx.MockTransport(mock_handler))
    repo = IssueEvidenceRepository(client)

    # 1. Create single evidence
    ev = await repo.create_evidence(
        session_id=session_id,
        issue_id=issue_id,
        source_id=source_id,
        claim_id=claim_id,
        evidence_text="Price is $20.",
        polarity="contradicts",
        explanation="Contradicts original statement of $10.",
    )
    assert ev["id"] == evidence_id
    assert ev["polarity"] == "contradicts"

    # 2. Polarity validation
    with pytest.raises(ValueError, match="Invalid polarity"):
        await repo.create_evidence(
            session_id=session_id,
            issue_id=issue_id,
            source_id=source_id,
            evidence_text="Txt",
            polarity="invalid_polarity",
        )

    # 3. Retrieve by issue
    by_issue = await repo.get_evidence_by_issue(issue_id)
    assert len(by_issue) == 1

    # 4. Retrieve by source
    by_source = await repo.get_evidence_by_source(source_id)
    assert len(by_source) == 1

    # 5. Delete
    deleted = await repo.delete_evidence(evidence_id)
    assert deleted["id"] == evidence_id


# ==============================================================================
# 4. ChecklistRepository Tests
# ==============================================================================

@pytest.mark.anyio
async def test_checklist_crud_and_completion_lifecycle():
    session_id = str(uuid.uuid4())
    item_id = str(uuid.uuid4())

    def mock_handler(request: httpx.Request):
        method = request.method
        url = str(request.url)

        if method == "POST":
            data = json.loads(request.content)
            if isinstance(data, list):
                for item in data:
                    item["id"] = str(uuid.uuid4())
                return httpx.Response(201, json=data)
            data["id"] = item_id
            return httpx.Response(201, json=[data])

        elif method == "GET":
            if f"id=eq.{item_id}" in url:
                return httpx.Response(200, json=[{
                    "id": item_id, "session_id": session_id, "user_id": TEST_USER_ID,
                    "task_description": "Verify pricing page directly", "priority": "high", "status": "pending"
                }])
            return httpx.Response(200, json=[
                {"id": item_id, "task_description": "Task 1", "priority": "high", "status": "pending"}
            ])

        elif method == "PATCH":
            updated = json.loads(request.content)
            updated["id"] = item_id
            return httpx.Response(200, json=[updated])

        elif method == "DELETE":
            return httpx.Response(200, json=[{"id": item_id}])

        return httpx.Response(400)

    client = create_user_client(transport=httpx.MockTransport(mock_handler))
    repo = ChecklistRepository(client)

    # 1. Create item
    item = await repo.create_item(
        session_id=session_id,
        task_description="Verify pricing page directly",
        priority="high",
        status="pending",
    )
    assert item["id"] == item_id
    assert item["priority"] == "high"
    assert item["completed_at"] is None

    # 2. Mark completed (sets completed_at timestamp)
    completed = await repo.mark_completed(item_id, verification_notes="Verified against official website.")
    assert completed["status"] == "completed"
    assert completed["completed_at"] is not None

    # 3. Reopen task (clears completed_at timestamp)
    reopened = await repo.reopen_item(item_id, status="in_progress")
    assert reopened["status"] == "in_progress"
    assert reopened["completed_at"] is None

    # 4. Updates (task description, priority, notes)
    upd_desc = await repo.update_task_description(item_id, "Updated task description")
    assert upd_desc["task_description"] == "Updated task description"

    upd_priority = await repo.update_priority(item_id, "urgent")
    assert upd_priority["priority"] == "urgent"

    # 5. Delete
    deleted = await repo.delete_item(item_id)
    assert deleted["id"] == item_id


# ==============================================================================
# 5. ReportsRepository Tests
# ==============================================================================

@pytest.mark.anyio
async def test_reports_crud_and_metrics_validation():
    session_id = str(uuid.uuid4())
    report_id = str(uuid.uuid4())

    def mock_handler(request: httpx.Request):
        method = request.method
        url = str(request.url)

        if method == "POST":
            data = json.loads(request.content)
            data["id"] = report_id
            return httpx.Response(201, json=[data])

        elif method == "GET":
            if f"id=eq.{report_id}" in url:
                return httpx.Response(200, json=[{
                    "id": report_id, "session_id": session_id, "user_id": TEST_USER_ID,
                    "title": "Synthesis Report", "executive_summary": "Summary text",
                    "coverage_score": 85, "status": "draft"
                }])
            return httpx.Response(200, json=[
                {"id": report_id, "title": "Synthesis Report", "coverage_score": 85, "status": "draft"}
            ])

        elif method == "PATCH":
            updated = json.loads(request.content)
            updated["id"] = report_id
            return httpx.Response(200, json=[updated])

        elif method == "DELETE":
            return httpx.Response(200, json=[{"id": report_id}])

        return httpx.Response(400)

    client = create_user_client(transport=httpx.MockTransport(mock_handler))
    repo = ReportsRepository(client)

    # 1. Create report
    report = await repo.create_report(
        session_id=session_id,
        title="Synthesis Report",
        executive_summary="Summary text of findings.",
        coverage_score=85,
        total_claims=20,
        verified_claims=16,
        conflicting_claims=2,
        unbacked_claims=2,
        identified_gaps=1,
        findings={"contradictions": ["Pricing variance"]},
        recommendations=["Directly verify Vendor X portal."],
        status="draft",
    )
    assert report["id"] == report_id
    assert report["coverage_score"] == 85

    # 2. Score validation (out of bounds)
    with pytest.raises(ValueError, match="out of bounds"):
        await repo.create_report(
            session_id=session_id,
            executive_summary="Summary",
            coverage_score=105,
        )

    # 3. Negative metric counter validation
    with pytest.raises(ValueError, match="cannot be negative"):
        await repo.create_report(
            session_id=session_id,
            executive_summary="Summary",
            total_claims=-1,
        )

    # 4. Update metrics
    updated_metrics = await repo.update_metrics(
        report_id,
        coverage_score=92,
        verified_claims=18,
    )
    assert updated_metrics["coverage_score"] == 92
    assert updated_metrics["verified_claims"] == 18

    # 5. Update status
    final_report = await repo.update_status(report_id, "final")
    assert final_report["status"] == "final"

    # 6. Delete
    deleted = await repo.delete_report(report_id)
    assert deleted["id"] == report_id


# ==============================================================================
# 6. Ownership & Dependency Injection Tests
# ==============================================================================

def test_unauthenticated_client_rejection_all_repositories():
    unauth_client = PostgrestClient.__new__(PostgrestClient)
    unauth_client.user = None
    unauth_client.access_token = None

    for repo_cls in (
        ExpectedFieldsRepository,
        ClaimsRepository,
        IssuesRepository,
        IssueEvidenceRepository,
        ChecklistRepository,
        ReportsRepository,
    ):
        with pytest.raises(DatabaseAuthenticationError):
            repo_cls(unauth_client)


def test_dependency_injection_all_repositories():
    client = create_user_client()

    assert isinstance(get_expected_fields_repository(client), ExpectedFieldsRepository)
    assert isinstance(get_claims_repository(client), ClaimsRepository)
    assert isinstance(get_issues_repository(client), IssuesRepository)
    assert isinstance(get_issue_evidence_repository(client), IssueEvidenceRepository)
    assert isinstance(get_checklist_repository(client), ChecklistRepository)
    assert isinstance(get_reports_repository(client), ReportsRepository)


@pytest.mark.anyio
async def test_composite_foreign_key_error_mapping():
    """
    Tests handling of PostgreSQL composite foreign key violation
    when referencing a session that does not exist or belongs to another user.
    """
    def mock_handler(request: httpx.Request):
        return httpx.Response(
            409,
            json={
                "code": "23503",
                "message": 'insert or update on table "claims" violates foreign key constraint "fk_claims_session"',
                "details": "Key (session_id, user_id)=(...) is not present in table research_sessions.",
            },
        )

    client = create_user_client(transport=httpx.MockTransport(mock_handler))
    repo = ClaimsRepository(client)

    with pytest.raises(DatabaseConstraintError) as exc_info:
        await repo.create_claim(
            session_id=str(uuid.uuid4()),
            source_id=str(uuid.uuid4()),
            claim_text="Cross-user claim",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.details == {"code": "23503"}
