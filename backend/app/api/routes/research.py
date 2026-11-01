"""
Research Sessions API Route (Tavily Web Search Ingestion & Persistence).
Integrates ResearchSessionRepository and ResearchSourceRepository with PostgREST.
Ensures user identity is derived strictly from verified JWT (zero trust in body parameters).
"""

import uuid
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.response import APIResponse
from app.schemas.research import (
    ResearchSessionCreate,
    ResearchSessionResponse,
    ResearchSessionDetailResponse,
    ResearchSessionStatusResponse,
    ResearchSessionUpdate,
    ExpectedFieldBase,
    ExpectedFieldCreate,
    ExpectedFieldUpdate,
    ExpectedFieldResponse,
    ResearchCoverageResponse,
    SourceItemResponse,
    SourceSelection,
    SearchProviderEnum,
)
from app.core.security import get_current_user, AuthenticatedUser
from app.database import (
    ResearchSessionRepository,
    get_research_session_repository,
    VALID_SESSION_STATUSES,
    ResearchSourceRepository,
    get_research_source_repository,
    ExpectedFieldsRepository,
    get_expected_fields_repository,
    VALID_EXPECTED_FIELD_STATUSES,
    EntityNotFoundError,
    DatabaseError,
)
from app.services.search.orchestrator import SearchOrchestrator
from app.services.search.base import NormalizedSource
from app.services.search.normalizer import canonicalize_url, merge_and_deduplicate_sources

router = APIRouter(prefix="/research", tags=["Research Sessions"])


@router.get(
    "/sessions",
    response_model=APIResponse[List[ResearchSessionResponse]],
    status_code=status.HTTP_200_OK,
    summary="List User Research Sessions",
    description="Retrieves research sessions owned by the authenticated user with pagination. User identity is derived strictly from verified Supabase JWT."
)
async def list_user_sessions(
    limit: int = Query(default=50, ge=1, le=100, description="Maximum number of sessions to return"),
    offset: int = Query(default=0, ge=0, description="Number of sessions to skip for pagination"),
    status_filter: Optional[str] = Query(default=None, alias="status", description="Optional filter by session lifecycle status"),
    session_repo: ResearchSessionRepository = Depends(get_research_session_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> APIResponse[List[ResearchSessionResponse]]:
    """Retrieves research sessions owned by the authenticated user with pagination support."""
    if status_filter and status_filter not in VALID_SESSION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status filter '{status_filter}'. Must be one of {sorted(VALID_SESSION_STATUSES)}"
        )

    sessions = await session_repo.list_user_sessions(
        status=status_filter,
        limit=limit,
        offset=offset,
        order="created_at.desc",
    )

    validated = [ResearchSessionResponse.model_validate(s) for s in sessions]

    return APIResponse(
        success=True,
        status_code=status.HTTP_200_OK,
        message=f"Retrieved {len(validated)} session(s) for authenticated user {current_user.email or current_user.user_id}",
        data=validated,
    )


@router.get(
    "/sessions/{session_id}/status",
    response_model=APIResponse[ResearchSessionStatusResponse],
    status_code=status.HTTP_200_OK,
    summary="Get Research Session Status",
    description="Retrieves the current execution status, search stage, and provider diagnostics for an owned session."
)
async def get_research_session_status(
    session_id: str,
    session_repo: ResearchSessionRepository = Depends(get_research_session_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> APIResponse[ResearchSessionStatusResponse]:
    """Retrieves session status, search stage, and diagnostics. Enforces user isolation."""
    try:
        val_uuid = uuid.UUID(str(session_id))
    except (ValueError, AttributeError):
        raise EntityNotFoundError(f"Research session '{session_id}' was not found.")

    session = await session_repo.get_session(str(val_uuid))
    metadata = session.get("search_metadata") or {}
    search_stage = metadata.get("search_stage")

    status_data = {
        "session_id": session["id"],
        "id": session["id"],
        "status": session["status"],
        "search_stage": search_stage,
        "search_metadata": metadata,
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
    }

    return APIResponse(
        success=True,
        status_code=status.HTTP_200_OK,
        message=f"Retrieved status for session '{session_id}'",
        data=ResearchSessionStatusResponse.model_validate(status_data),
    )


@router.get(
    "/sessions/{session_id}/sources",
    response_model=APIResponse[List[SourceItemResponse]],
    status_code=status.HTTP_200_OK,
    summary="List Research Session Sources",
    description="Retrieves persisted sources associated with an owned session with pagination support."
)
async def list_research_session_sources(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=100, description="Maximum number of sources to return"),
    offset: int = Query(default=0, ge=0, description="Number of sources to skip for pagination"),
    session_repo: ResearchSessionRepository = Depends(get_research_session_repository),
    source_repo: ResearchSourceRepository = Depends(get_research_source_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> APIResponse[List[SourceItemResponse]]:
    """Retrieves sources for an owned research session. Validates session existence and ownership first."""
    try:
        val_uuid = uuid.UUID(str(session_id))
    except (ValueError, AttributeError):
        raise EntityNotFoundError(f"Research session '{session_id}' was not found.")

    # 1. Verify session exists and is owned by authenticated user (raises EntityNotFoundError 404 if not)
    await session_repo.get_session(str(val_uuid))

    # 2. Retrieve sources scoped to user and session with pagination
    sources = await source_repo.get_sources_by_session(
        session_id=str(val_uuid),
        limit=limit,
        offset=offset,
        order="created_at.asc",
    )

    validated = [SourceItemResponse.model_validate(s) for s in sources]

    return APIResponse(
        success=True,
        status_code=status.HTTP_200_OK,
        message=f"Retrieved {len(validated)} source(s) for session '{session_id}'",
        data=validated,
    )


@router.get(
    "/sessions/{session_id}",
    response_model=APIResponse[ResearchSessionDetailResponse],
    status_code=status.HTTP_200_OK,
    summary="Get Research Session Details",
    description="Retrieves an individual research session and its associated sources. Enforces user isolation."
)
async def get_research_session(
    session_id: str,
    session_repo: ResearchSessionRepository = Depends(get_research_session_repository),
    source_repo: ResearchSourceRepository = Depends(get_research_source_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> APIResponse[ResearchSessionDetailResponse]:
    """Retrieves an individual research session owned by the authenticated user."""
    try:
        val_uuid = uuid.UUID(str(session_id))
    except (ValueError, AttributeError):
        raise EntityNotFoundError(f"Research session '{session_id}' was not found.")

    session = await session_repo.get_session(str(val_uuid))
    sources = await source_repo.get_sources_by_session(str(val_uuid))

    session_data = dict(session)
    session_data["sources"] = sources
    validated = ResearchSessionDetailResponse.model_validate(session_data)

    return APIResponse(
        success=True,
        status_code=status.HTTP_200_OK,
        message=f"Retrieved research session '{session_id}'",
        data=validated,
    )


@router.patch(
    "/sessions/{session_id}",
    response_model=APIResponse[ResearchSessionResponse],
    status_code=status.HTTP_200_OK,
    summary="Update Research Session",
    description="Safely updates allowed metadata (e.g. title) for an owned research session. Forbids immutable or system-managed fields."
)
async def update_research_session(
    session_id: str,
    payload: ResearchSessionUpdate,
    session_repo: ResearchSessionRepository = Depends(get_research_session_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> APIResponse[ResearchSessionResponse]:
    """Updates allowed session metadata. Strictly enforces field allow-list and user isolation."""
    try:
        val_uuid = uuid.UUID(str(session_id))
    except (ValueError, AttributeError):
        raise EntityNotFoundError(f"Research session '{session_id}' was not found.")

    update_fields = payload.model_dump(exclude_unset=True)
    if not update_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No valid updatable fields provided in request body."
        )

    if "title" in update_fields:
        clean_title = (update_fields["title"] or "").strip()
        if not clean_title:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="title cannot be empty or whitespace."
            )
        update_fields["title"] = clean_title

    updated = await session_repo.update_session(str(val_uuid), update_fields)

    return APIResponse(
        success=True,
        status_code=status.HTTP_200_OK,
        message=f"Research session '{session_id}' updated successfully.",
        data=ResearchSessionResponse.model_validate(updated),
    )


# ==============================================================================
# Expected Fields & Coverage Endpoints (Stage 3, Phase 3, Step 3)
# ==============================================================================

@router.get(
    "/sessions/{session_id}/expected-fields",
    response_model=APIResponse[List[ExpectedFieldResponse]],
    status_code=status.HTTP_200_OK,
    summary="List Expected Fields for Session",
    description="Retrieves all expected research fields belonging to an owned session. Preserves database ordering."
)
async def list_expected_fields(
    session_id: str,
    status_filter: Optional[str] = Query(default=None, alias="status", description="Optional filter by coverage status"),
    session_repo: ResearchSessionRepository = Depends(get_research_session_repository),
    expected_fields_repo: ExpectedFieldsRepository = Depends(get_expected_fields_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> APIResponse[List[ExpectedFieldResponse]]:
    """Retrieves expected fields for an owned session. Validates session existence and ownership first."""
    try:
        val_uuid = uuid.UUID(str(session_id))
    except (ValueError, AttributeError):
        raise EntityNotFoundError(f"Research session '{session_id}' was not found.")

    if status_filter and status_filter not in VALID_EXPECTED_FIELD_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status filter '{status_filter}'. Must be one of {sorted(VALID_EXPECTED_FIELD_STATUSES)}"
        )

    # 1. Verify session exists and is owned by authenticated user
    await session_repo.get_session(str(val_uuid))

    # 2. Retrieve expected fields
    fields = await expected_fields_repo.get_fields_by_session(
        session_id=str(val_uuid),
        status=status_filter,
        order="created_at.asc",
    )

    validated = [ExpectedFieldResponse.model_validate(f) for f in fields]

    return APIResponse(
        success=True,
        status_code=status.HTTP_200_OK,
        message=f"Retrieved {len(validated)} expected field(s) for session '{session_id}'",
        data=validated,
    )


@router.post(
    "/sessions/{session_id}/expected-fields",
    response_model=APIResponse[ExpectedFieldResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create Expected Field",
    description="Adds a new expected research dimension to an owned session. Validates weights (0.00-5.00) and prevents duplicates."
)
async def create_expected_field(
    session_id: str,
    payload: ExpectedFieldCreate,
    session_repo: ResearchSessionRepository = Depends(get_research_session_repository),
    expected_fields_repo: ExpectedFieldsRepository = Depends(get_expected_fields_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> APIResponse[ExpectedFieldResponse]:
    """Creates an expected research field for an owned session."""
    try:
        val_uuid = uuid.UUID(str(session_id))
    except (ValueError, AttributeError):
        raise EntityNotFoundError(f"Research session '{session_id}' was not found.")

    clean_name = payload.field_name.strip()
    if not clean_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="field_name cannot be empty or whitespace."
        )

    # 1. Verify session exists and is owned by authenticated user
    await session_repo.get_session(str(val_uuid))

    # 2. Check for duplicate field name within session
    existing_fields = await expected_fields_repo.get_fields_by_session(session_id=str(val_uuid))
    if any(f.get("field_name", "").strip().lower() == clean_name.lower() for f in existing_fields):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An expected field named '{clean_name}' already exists in this research session."
        )

    # 3. Create expected field in database
    created = await expected_fields_repo.create_expected_field(
        session_id=str(val_uuid),
        field_name=clean_name,
        field_category=(payload.field_category or "general").strip(),
        description=payload.description.strip() if payload.description else None,
        is_required=payload.is_required,
        weight=payload.weight,
        status=payload.status or "missing",
    )

    return APIResponse(
        success=True,
        status_code=status.HTTP_201_CREATED,
        message=f"Expected field '{clean_name}' created successfully.",
        data=ExpectedFieldResponse.model_validate(created),
    )


@router.patch(
    "/sessions/{session_id}/expected-fields/{field_id}",
    response_model=APIResponse[ExpectedFieldResponse],
    status_code=status.HTTP_200_OK,
    summary="Update Expected Field",
    description="Safely updates allowed properties (field_name, description, weight) of an expected field. Status and immutable fields are forbidden."
)
async def update_expected_field(
    session_id: str,
    field_id: str,
    payload: ExpectedFieldUpdate,
    session_repo: ResearchSessionRepository = Depends(get_research_session_repository),
    expected_fields_repo: ExpectedFieldsRepository = Depends(get_expected_fields_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> APIResponse[ExpectedFieldResponse]:
    """Updates allowed expected field properties (field_name, description, weight). Enforces session and field ownership."""
    try:
        val_uuid = uuid.UUID(str(session_id))
    except (ValueError, AttributeError):
        raise EntityNotFoundError(f"Research session '{session_id}' was not found.")

    try:
        val_fid = uuid.UUID(str(field_id))
    except (ValueError, AttributeError):
        raise EntityNotFoundError(f"Expected field '{field_id}' was not found.")

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No valid updatable fields provided in request body."
        )

    # Whitelist only client-editable properties and strip any system-managed keys
    allowed_keys = {"field_name", "description", "weight"}
    sanitized_data = {k: v for k, v in update_data.items() if k in allowed_keys}
    if not sanitized_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No valid updatable fields provided in request body."
        )

    # 1. Verify session exists and is owned by authenticated user
    await session_repo.get_session(str(val_uuid))

    # 2. Verify field exists and belongs to this session and user
    field = await expected_fields_repo.get_field_by_id(field_id=str(val_fid), session_id=str(val_uuid))

    # 3. Validate clean field_name if updated
    if "field_name" in sanitized_data:
        clean_name = (sanitized_data["field_name"] or "").strip()
        if not clean_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="field_name cannot be empty or whitespace."
            )
        # Check duplicate name within session if renamed
        if clean_name.lower() != field.get("field_name", "").strip().lower():
            existing_fields = await expected_fields_repo.get_fields_by_session(session_id=str(val_uuid))
            if any(f.get("field_name", "").strip().lower() == clean_name.lower() and str(f.get("id")) != str(val_fid) for f in existing_fields):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"An expected field named '{clean_name}' already exists in this research session."
                )
        sanitized_data["field_name"] = clean_name

    updated = await expected_fields_repo.update_expected_field(
        field_id=str(val_fid),
        data=sanitized_data,
        session_id=str(val_uuid),
    )

    return APIResponse(
        success=True,
        status_code=status.HTTP_200_OK,
        message=f"Expected field '{field_id}' updated successfully.",
        data=ExpectedFieldResponse.model_validate(updated),
    )


@router.delete(
    "/sessions/{session_id}/expected-fields/{field_id}",
    response_model=APIResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="Delete Expected Field",
    description="Deletes an expected field belonging to an owned research session."
)
async def delete_expected_field(
    session_id: str,
    field_id: str,
    session_repo: ResearchSessionRepository = Depends(get_research_session_repository),
    expected_fields_repo: ExpectedFieldsRepository = Depends(get_expected_fields_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> APIResponse[dict]:
    """Deletes an expected field. Enforces session and field ownership."""
    try:
        val_uuid = uuid.UUID(str(session_id))
    except (ValueError, AttributeError):
        raise EntityNotFoundError(f"Research session '{session_id}' was not found.")

    try:
        val_fid = uuid.UUID(str(field_id))
    except (ValueError, AttributeError):
        raise EntityNotFoundError(f"Expected field '{field_id}' was not found.")

    # 1. Verify session exists and is owned by authenticated user
    await session_repo.get_session(str(val_uuid))

    # 2. Delete expected field (scoped to user_id and session_id)
    await expected_fields_repo.delete_expected_field(
        field_id=str(val_fid),
        session_id=str(val_uuid),
    )

    return APIResponse(
        success=True,
        status_code=status.HTTP_200_OK,
        message=f"Expected field '{field_id}' deleted successfully.",
        data={"id": str(val_fid), "session_id": str(val_uuid), "deleted": True},
    )


@router.get(
    "/sessions/{session_id}/coverage",
    response_model=APIResponse[ResearchCoverageResponse],
    status_code=status.HTTP_200_OK,
    summary="Get Research Coverage",
    description="Calculates completeness and weighted coverage for all expected fields in an owned research session."
)
async def get_research_session_coverage(
    session_id: str,
    session_repo: ResearchSessionRepository = Depends(get_research_session_repository),
    expected_fields_repo: ExpectedFieldsRepository = Depends(get_expected_fields_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> APIResponse[ResearchCoverageResponse]:
    """Calculates completeness score (0-100) and weighted coverage metrics. Enforces user isolation."""
    try:
        val_uuid = uuid.UUID(str(session_id))
    except (ValueError, AttributeError):
        raise EntityNotFoundError(f"Research session '{session_id}' was not found.")

    # 1. Verify session ownership first
    session = await session_repo.get_session(str(val_uuid))

    # 2. Calculate coverage metrics using ExpectedFieldsRepository
    stats = await expected_fields_repo.calculate_coverage_statistics(session_id=str(val_uuid))

    # 3. Retrieve per-field breakdown
    fields = await expected_fields_repo.get_fields_by_session(
        session_id=str(val_uuid),
        order="created_at.asc",
    )
    validated_fields = [ExpectedFieldResponse.model_validate(f) for f in fields]

    coverage_score = stats.get("coverage_score", 0)

    # 4. Sync coverage_score in research_sessions table if changed
    if session.get("coverage_score") != coverage_score:
        try:
            await session_repo.update_session(
                session_id=str(val_uuid),
                data={"coverage_score": coverage_score}
            )
        except Exception:
            pass

    response_data = {
        "session_id": val_uuid,
        "total_fields": stats["total_fields"],
        "covered_fields": stats["covered_fields"],
        "partially_covered_fields": stats["partially_covered_fields"],
        "missing_fields": stats["missing_fields"],
        "coverage_score": coverage_score,
        "total_weight": stats["total_weight"],
        "covered_weight": stats["covered_weight"],
        "fields": validated_fields,
    }

    return APIResponse(
        success=True,
        status_code=status.HTTP_200_OK,
        message=f"Coverage analysis completed for session '{session_id}'. Score: {coverage_score}%.",
        data=ResearchCoverageResponse.model_validate(response_data),
    )


@router.post(
    "/sessions",
    response_model=APIResponse[dict],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Initialize Research Session",
    description="Accepts a research query, creates a session in Supabase, initiates Tavily web search, and persists normalized sources."
)
async def create_research_session(
    payload: ResearchSessionCreate,
    session_repo: ResearchSessionRepository = Depends(get_research_session_repository),
    source_repo: ResearchSourceRepository = Depends(get_research_source_repository),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> APIResponse[dict]:
    """
    Initializes a research session.
    Persists session in Supabase, executes Tavily web search when requested,
    normalizes and deduplicates sources, and persists normalized sources.
    The research session record is preserved even if search or source persistence fails.
    """
    query_text = (payload.research_query or "").strip()
    if not query_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="research_query cannot be empty or blank."
        )

    # 1. Create a research session in Supabase with initial status 'pending'
    session_id = str(uuid.uuid4())
    initial_metadata = {
        "source_strategy": payload.source_selection.value,
        "custom_urls_count": len(payload.custom_urls or []),
    }

    # If session creation fails, DatabaseError is raised and mapped to structured database error response
    session_record = await session_repo.create_session(
        session_id=session_id,
        research_query=query_text,
        title=payload.title,
        search_provider="tavily",
        status="pending",
        search_metadata=initial_metadata,
    )

    provider_statuses = {}
    collected_sources: List[NormalizedSource] = []
    search_stage_status = "not_requested"
    search_error = None

    # 2. Execute Web Search if source_selection is 'web' or 'both'
    if payload.source_selection in (SourceSelection.WEB, SourceSelection.BOTH):
        orchestrator = SearchOrchestrator()
        try:
            search_response = await orchestrator.execute_search(
                query=query_text,
                provider_selection="tavily"
            )
            collected_sources.extend(search_response.sources)
            provider_statuses = {
                k: v.model_dump() for k, v in search_response.provider_statuses.items()
            }
            search_stage_status = "completed"
        except Exception as exc:
            search_stage_status = "failed"
            search_error = SearchOrchestrator._sanitize_error_message(str(exc))
            if hasattr(exc, "provider_statuses") and isinstance(exc.provider_statuses, dict):
                provider_statuses = {k: v.model_dump() for k, v in exc.provider_statuses.items()}
            else:
                provider_statuses["tavily"] = {
                    "provider": "tavily",
                    "success": False,
                    "result_count": 0,
                    "latency_seconds": 0.0,
                    "error_message": search_error
                }

    # 3. Ingest custom URLs if provided
    if payload.source_selection in (SourceSelection.URLS, SourceSelection.BOTH) and payload.custom_urls:
        for custom_url in payload.custom_urls:
            raw_url = str(custom_url)
            c_url = canonicalize_url(raw_url)
            collected_sources.append(
                NormalizedSource(
                    url=raw_url,
                    canonical_url=c_url,
                    title="Target Custom URL",
                    snippet="User-provided investigation URL",
                    score=1.0,
                    providers=["user_url"],
                    metadata={"source_type": "user_provided"}
                )
            )

    # 4. Final deduplication and provider attribution merge
    deduped_sources = merge_and_deduplicate_sources(collected_sources)

    # 5. Persist normalized sources through ResearchSourceRepository
    persisted_sources = []
    source_persistence_error = None

    if deduped_sources:
        try:
            source_dicts = [s.model_dump() for s in deduped_sources]
            persisted_sources = await source_repo.insert_sources_deduplicated(
                session_id=session_id,
                sources=source_dicts,
            )
        except Exception as exc:
            # Session must not be lost if source persistence fails
            source_persistence_error = str(exc)

    # 6. Update session status and search metadata
    updated_session = session_record
    if search_stage_status == "failed" and not deduped_sources:
        # Search failed and no sources available: mark session failed, preserve record
        updated_session = await session_repo.update_session_status(
            session_id=session_id,
            status="failed",
            search_metadata={
                **initial_metadata,
                "search_stage": "failed",
                "search_error": search_error,
                "provider_statuses": provider_statuses,
            }
        )
        message = f"Research session registered, but web search failed: {search_error}"
    elif source_persistence_error:
        # Source persistence failed: do NOT report session as successfully completed
        updated_session = await session_repo.update_session_status(
            session_id=session_id,
            status="failed",
            search_metadata={
                **initial_metadata,
                "search_stage": search_stage_status,
                "search_error": search_error,
                "source_error": source_persistence_error,
                "provider_statuses": provider_statuses,
            }
        )
        message = f"Research session registered, but source persistence failed: {source_persistence_error}"
    elif search_stage_status == "failed" and deduped_sources:
        # Search failed, but custom URLs were provided and persisted
        updated_session = await session_repo.update_session_status(
            session_id=session_id,
            status="failed",
            search_metadata={
                **initial_metadata,
                "search_stage": "failed",
                "search_error": search_error,
                "provider_statuses": provider_statuses,
                "sources_count": len(persisted_sources),
            }
        )
        message = f"Research session registered, but web search failed: {search_error}"
    else:
        # Successful search and source persistence
        updated_session = await session_repo.update_session_status(
            session_id=session_id,
            status="completed" if (persisted_sources or search_stage_status == "completed") else "pending",
            search_metadata={
                **initial_metadata,
                "search_stage": search_stage_status,
                "search_error": search_error,
                "provider_statuses": provider_statuses,
                "sources_count": len(persisted_sources),
            }
        )
        message = f"Research session initiated. Retrieved {len(persisted_sources)} source(s) via Tavily."

    return APIResponse(
        success=True,
        status_code=status.HTTP_202_ACCEPTED,
        message=message,
        data={
            "session_id": session_id,
            "user_id": current_user.user_id,
            "query": payload.research_query,
            "source_strategy": payload.source_selection.value,
            "search_provider": "tavily",
            "custom_urls_count": len(payload.custom_urls or []),
            "status": "pending",
            "search_stage": search_stage_status,
            "search_error": search_error,
            "provider_statuses": provider_statuses,
            "sources_count": len(persisted_sources),
            "sources": persisted_sources,
            "session": updated_session or session_record,
        }
    )
