"""
Research Sessions API Route (Foundation).
Provides route structure for creating and querying research sessions.
Demonstrates secure user extraction via `get_current_user` dependency (no trust in body user_id).
"""

from typing import List
from fastapi import APIRouter, Depends, status
from app.schemas.response import APIResponse
from app.schemas.research import ResearchSessionCreate, ResearchSessionResponse
from app.core.security import get_current_user, AuthenticatedUser

router = APIRouter(prefix="/research", tags=["Research Sessions"])


@router.get(
    "/sessions",
    response_model=APIResponse[List[ResearchSessionResponse]],
    status_code=status.HTTP_200_OK,
    summary="List User Research Sessions",
    description="Retrieves research sessions owned by the authenticated user. User identity is derived strictly from verified Supabase JWT."
)
async def list_user_sessions(
    current_user: AuthenticatedUser = Depends(get_current_user)
) -> APIResponse[List[ResearchSessionResponse]]:
    """Placeholder endpoint returning authenticated user's sessions."""
    # In full production, this queries Supabase Postgres with current_user.user_id filter
    return APIResponse(
        success=True,
        status_code=status.HTTP_200_OK,
        message=f"Retrieved sessions for authenticated user {current_user.email or current_user.user_id}",
        data=[]
    )


@router.post(
    "/sessions",
    response_model=APIResponse[dict],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Initialize Research Session",
    description="Accepts a research query and initiates information gap analysis pipeline for the authenticated user."
)
async def create_research_session(
    payload: ResearchSessionCreate,
    current_user: AuthenticatedUser = Depends(get_current_user)
) -> APIResponse[dict]:
    """Placeholder endpoint initializing a research query."""
    return APIResponse(
        success=True,
        status_code=status.HTTP_202_ACCEPTED,
        message="Research session initiated. Engine analysis scheduled.",
        data={
            "user_id": current_user.user_id,
            "query": payload.research_query,
            "source_strategy": payload.source_selection,
            "custom_urls_count": len(payload.custom_urls or []),
            "status": "pending"
        }
    )
