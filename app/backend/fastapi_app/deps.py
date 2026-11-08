"""FastAPI-specific dependency-injection glue."""

from typing import Optional

from fastapi import Depends

from src.context import RequestContext
from src.database import get_session, AsyncSession
from src.services.authorization import (
    AuthenticationRequiredError,
    ReportAccessDeniedError,
    ReportNotFoundError,
    has_role,
    require_report_read,
)

from .auth import get_user
from .errors import raise_for_report_access


def get_context(db: AsyncSession = Depends(get_session), user: Optional[dict] = Depends(get_user)) -> RequestContext:
    # get_user requires the APPROVED role whenever a token is given at all (see its
    # docstring), so every route built on get_context gets that check for free now,
    # not just the ones that happened to also declare their own approval dependency.
    return RequestContext(
        db=db,
        user_id=user.get("sub") if user else None,
        is_admin=bool(user) and has_role(user.get("roles") or [], "ADMIN"),
    )


async def check_report_read(report_id: int, ctx: RequestContext = Depends(get_context)) -> None:
    """The routes that read one report: 404/401/403 unless the caller may read it (require_report_read: every report of
    the core database, a report of an update only for the owner and the assignees of the update)."""
    try:
        await require_report_read(report_id, ctx.report_repo, ctx.project_repo, ctx.user_id)
    except (ReportNotFoundError, AuthenticationRequiredError, ReportAccessDeniedError) as exc:
        raise_for_report_access(exc)
