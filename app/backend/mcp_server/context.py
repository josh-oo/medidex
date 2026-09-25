"""Bridges MCP tools/resources to the same composition root the REST API uses
(src/context.py's RequestContext): the current authenticated user, a scoped
DB session, and the resulting repo/service object graph.

FastAPI resolves a `Depends(...)` graph itself, so the REST API just asks for
a RequestContext via `Depends(get_context)` (fastapi_app/deps.py). MCP
tools/resources aren't running inside a FastAPI request and can't resolve that
graph, so `request_context` below does the equivalent by hand: open a session
the same way get_session() would for a request, then hand back a RequestContext
built from it - the same object graph, without depending on fastapi_app/* (the
REST API's FastAPI presentation tier).
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from mcp.server.auth.middleware.auth_context import get_access_token

from src.context import RequestContext
from src.database import get_session
from src.services.authorization import (
    get_authorized_project_id,
    ReportNotFoundError,
    AuthenticationRequiredError,
    ReportAccessDeniedError,
)

# get_session() is an async-generator dependency built for FastAPI's Depends
# machinery; wrapping it lets tools/resources open/close a session the same
# way outside of a request, without going through FastAPI's DI system.
_session_scope = asynccontextmanager(get_session)


def current_user_id() -> str:
    access_token = get_access_token()
    if access_token is None or not access_token.subject:
        raise ValueError("Not authenticated")
    return access_token.subject


def require_admin() -> None:
    """Raise ValueError (the MCP tool/resource error convention) unless the
    caller's token carries Keycloak's ADMIN realm role - same check as the
    REST API's is_admin dependency (fastapi_app/auth.py), applied to the
    medidex-mcp client's own token (KeycloakMCPTokenVerifier already decodes
    it and keeps the raw claims on AccessToken.claims) instead of re-decoding
    it here.
    """
    access_token = get_access_token()
    if access_token is None:
        raise ValueError("Not authenticated")
    roles = (access_token.claims or {}).get("roles", [])
    if "ADMIN" not in roles:
        raise ValueError("Not allowed: admin role required")


@asynccontextmanager
async def request_context(user_id: Optional[str]) -> AsyncIterator[RequestContext]:
    async with _session_scope() as db:
        yield RequestContext(db=db, user_id=user_id)


async def require_report_access(report_id: int, ctx: RequestContext) -> None:
    """Raise ValueError (the MCP tool/resource error convention) unless the
    caller may access this report - same check as the REST API's
    check_report_access (fastapi_app/core.py), called via the shared domain
    function directly instead of through that FastAPI dependency.
    """
    try:
        await get_authorized_project_id(report_id, ctx.report_repo, ctx.project_repo, ctx.user_id)
    except (ReportNotFoundError, AuthenticationRequiredError, ReportAccessDeniedError) as exc:
        raise ValueError(str(exc)) from exc
