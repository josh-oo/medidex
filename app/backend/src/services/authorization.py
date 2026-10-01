"""Report/project access authorization."""

from typing import List, Optional

from ..database.repositories.report import ReportRepository
from ..database.repositories.project import ProjectRepository


class ReportNotFoundError(Exception):
    """No report exists with the given id."""


class AuthenticationRequiredError(Exception):
    """The report belongs to a project, but no authenticated user was given."""


class ReportAccessDeniedError(Exception):
    """The authenticated user isn't assigned to the report's project."""


class ProjectAccessDeniedError(Exception):
    """The caller isn't assigned to this project."""


class NotApprovedError(Exception):
    """The caller's account doesn't have the APPROVED role."""


class AdminRequiredError(Exception):
    """The caller doesn't have the ADMIN role."""


def has_role(roles: List[str], role: str) -> bool:
    return role in roles


def require_approved(roles: List[str]) -> None:
    if not has_role(roles, "APPROVED"):
        raise NotApprovedError("Account not approved")


def require_admin(roles: List[str]) -> None:
    if not has_role(roles, "ADMIN"):
        raise AdminRequiredError("ADMIN role required")


class ResourceMismatchError(Exception):
    """Token isn't bound (RFC 8707 resource indicator) to the required resource."""


def require_resource_audience(claims: dict, resource_url: str) -> None:
    aud = claims.get("aud")
    aud_list = aud if isinstance(aud, list) else [aud] if aud else []
    if resource_url not in aud_list:
        raise ResourceMismatchError(f"Token not bound to resource {resource_url}")


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
