"""
Database Repositories Package for InfoScope AI.
Provides table-specific repositories and dependency providers for all Supabase tables.
"""

from app.database.repositories.base import (
    BaseRepository,
    validate_identifier,
    format_filter_value,
)
from app.database.repositories.sessions import (
    ResearchSessionRepository,
    get_research_session_repository,
    VALID_SESSION_STATUSES,
    VALID_SEARCH_PROVIDERS,
)
from app.database.repositories.sources import (
    ResearchSourceRepository,
    get_research_source_repository,
)
from app.database.repositories.expected_fields import (
    ExpectedFieldsRepository,
    get_expected_fields_repository,
    VALID_EXPECTED_FIELD_STATUSES,
)
from app.database.repositories.claims import (
    ClaimsRepository,
    get_claims_repository,
    VALID_CLAIM_STATUSES,
)
from app.database.repositories.issues import (
    IssuesRepository,
    get_issues_repository,
    VALID_ISSUE_TYPES,
    VALID_SEVERITIES,
    VALID_ISSUE_STATUSES,
)
from app.database.repositories.issue_evidence import (
    IssueEvidenceRepository,
    get_issue_evidence_repository,
    VALID_EVIDENCE_POLARITIES,
)
from app.database.repositories.checklist import (
    ChecklistRepository,
    get_checklist_repository,
    VALID_CHECKLIST_PRIORITIES,
    VALID_CHECKLIST_STATUSES,
)
from app.database.repositories.reports import (
    ReportsRepository,
    get_reports_repository,
    VALID_REPORT_STATUSES,
)

__all__ = [
    # Base
    "BaseRepository",
    "validate_identifier",
    "format_filter_value",
    # Core Research
    "ResearchSessionRepository",
    "get_research_session_repository",
    "VALID_SESSION_STATUSES",
    "VALID_SEARCH_PROVIDERS",
    "ResearchSourceRepository",
    "get_research_source_repository",
    # Expected Fields
    "ExpectedFieldsRepository",
    "get_expected_fields_repository",
    "VALID_EXPECTED_FIELD_STATUSES",
    # Claims
    "ClaimsRepository",
    "get_claims_repository",
    "VALID_CLAIM_STATUSES",
    # Issues
    "IssuesRepository",
    "get_issues_repository",
    "VALID_ISSUE_TYPES",
    "VALID_SEVERITIES",
    "VALID_ISSUE_STATUSES",
    # Issue Evidence
    "IssueEvidenceRepository",
    "get_issue_evidence_repository",
    "VALID_EVIDENCE_POLARITIES",
    # Checklist
    "ChecklistRepository",
    "get_checklist_repository",
    "VALID_CHECKLIST_PRIORITIES",
    "VALID_CHECKLIST_STATUSES",
    # Reports
    "ReportsRepository",
    "get_reports_repository",
    "VALID_REPORT_STATUSES",
]
