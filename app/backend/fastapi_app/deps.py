"""FastAPI-specific dependency-injection glue."""

from typing import Optional

from fastapi import Depends, HTTPException

from src.context import RequestContext
from src.database import get_session, AsyncSession
from src.services.authorization import (
    AuthenticationRequiredError,
    ReportAccessDeniedError,
    ReportNotFoundError,
    has_role,
    require_report_read,
)

from .auth import get_signed_in_user, get_user
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


def get_account_context(db: AsyncSession = Depends(get_session), user: dict = Depends(get_signed_in_user)) -> RequestContext:
    """The context of the routes of the caller's own account: the caller as get_context makes it, but approved or not."""
    return RequestContext(db=db, user_id=user["sub"], is_admin=has_role(user.get("roles") or [], "ADMIN"))


async def check_report_pdf_write(report_id: int, ctx: RequestContext = Depends(get_context)) -> None:
    """403 unless the caller owns the study database of the report: of its update, or one it is linked into (a report of
    the core database). Only the owner uploads and deletes PDFs."""
    project_id = await ctx.project_repo.get_project_id_by_report_id(report_id)
    if project_id is not None:
        owns = ctx.user_id is not None and await ctx.project_repo.get_project_by_id(project_id) is not None
    else:
        owns = ctx.user_id in await ctx.database_repo.get_owners_of_report(report_id)
    if not owns:
        raise HTTPException(status_code=403, detail="Only the owner of the study database changes the PDF of this report")


async def check_report_read(report_id: int, ctx: RequestContext = Depends(get_context)) -> None:
    """The routes that read one report: 404/401/403 unless the caller may read it (require_report_read: every report of
    the core database, a report of an update only for the owner and the assignees of the update)."""
    try:
        await require_report_read(report_id, ctx.report_repo, ctx.project_repo, ctx.user_id)
    except (ReportNotFoundError, AuthenticationRequiredError, ReportAccessDeniedError) as exc:
        raise_for_report_access(exc)
