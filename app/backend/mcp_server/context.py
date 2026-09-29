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
from typing import AsyncIterator, List, Optional

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver.exceptions import ResourceError, ResourceNotFoundError

from src.context import RequestContext
from src.database import get_session
from src.services.authorization import (
    get_authorized_project_id,
    require_admin as require_admin_role,
    AdminRequiredError,
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
        raise ResourceError("Not authenticated")
    return access_token.subject


def current_roles() -> List[str]:
    """The caller's realm roles, straight off the already-decoded token claims
    (KeycloakMCPTokenVerifier keeps them on AccessToken.claims) - no token
    present means no roles, same convention as an empty list from a token
    with no "roles" claim.
    """
    access_token = get_access_token()
    if access_token is None:
        return []
    return (access_token.claims or {}).get("roles", [])


def require_admin() -> None:
    """Raise ResourceError (the MCP tool/resource error convention - caught and
    surfaced with its message intact from both a tool call and a resource read,
    see mcp.server.mcpserver.exceptions) unless the caller's token carries
    Keycloak's ADMIN realm role. Delegates the actual role check to
    src/services/authorization.py's require_admin - the same rule the REST
    API's is_admin dependency (fastapi_app/auth.py) enforces. This is a
    fail-fast convenience for tools that are admin-only outright; it doesn't
    replace an authorization decision made inside a shared src/ service (see
    ProjectResourceService.create_project), which stays the actual
    enforcement no matter which head calls it.
    """
    access_token = get_access_token()
    if access_token is None:
        raise ResourceError("Not authenticated")
    try:
        require_admin_role(current_roles())
    except AdminRequiredError as exc:
        raise ResourceError(f"Not allowed: {exc}") from exc


@asynccontextmanager
async def request_context(user_id: Optional[str]) -> AsyncIterator[RequestContext]:
    async with _session_scope() as db:
        yield RequestContext(db=db, user_id=user_id)


async def require_report_access(report_id: int, ctx: RequestContext) -> None:
    """Raise ResourceError/ResourceNotFoundError (the MCP tool/resource error
    convention) unless the caller may access this report - for tools that read a
    report directly (get_report, get_report_studies) rather than through a src/
    service method that already performs this same check itself (e.g.
    LinkageService.link_existing_study_to_report, StudySimilaritySearchService.
    get_similar_studies_page - see get_authorized_project_id's other callers).
    """
    try:
        await get_authorized_project_id(report_id, ctx.report_repo, ctx.project_repo, ctx.user_id)
    except ReportNotFoundError as exc:
        raise ResourceNotFoundError(str(exc)) from exc
    except (AuthenticationRequiredError, ReportAccessDeniedError) as exc:
        raise ResourceError(str(exc)) from exc
