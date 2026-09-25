"""Report/project access authorization - shared by the REST API and the MCP
server. Framework-agnostic: raises plain exceptions rather than HTTPException,
so non-FastAPI callers (mcp_server/) don't need to depend on FastAPI or on
fastapi_app/core.py's presentation-tier dependency function.
"""

from typing import Optional

from ..database.repositories.report import ReportRepository
from ..database.repositories.project import ProjectRepository


class ReportNotFoundError(Exception):
    """No report exists with the given id."""


class AuthenticationRequiredError(Exception):
    """The report belongs to a project, but no authenticated user was given."""


class ReportAccessDeniedError(Exception):
    """The authenticated user isn't assigned to the report's project."""


async def get_authorized_project_id(
    report_id: int,
    report_repo: ReportRepository,
    project_repo: ProjectRepository,
    user_id: Optional[str],
) -> Optional[str]:
    """Return the id of the project a report belongs to, after checking the
    caller may access it. Returns None if the report isn't associated with
    any project (nothing to check against).
    """
    report = await report_repo.get_report_by_id(report_id)
    if not report:
        raise ReportNotFoundError(f"Report {report_id} not found")

    project_id = await project_repo.get_project_id_by_report_id(report_id)
    if not project_id:
        return None

    if not user_id:
        raise AuthenticationRequiredError("Authenticated user required")

    assigned_projects = await project_repo.get_assigned_projects()
    assigned_project_ids = {project.id for project in assigned_projects}
    if project_id not in assigned_project_ids:
        raise ReportAccessDeniedError("You can only access reports in projects assigned to you")

    return project_id
