"""FastAPI-specific dependency-injection glue.

get_session() itself is framework-agnostic and lives in src/database - MCP
reuses it directly (see mcp_server/context.py). get_context() is the one
piece that's actually FastAPI-specific: it resolves get_session() and
auth.py's get_user_id() through FastAPI's own Depends() graph and hands back
a RequestContext (src/context.py's composition root). It lives here, not in
src/database, so the framework-agnostic src/ layer never imports anything
FastAPI-specific - this module (plus auth.py's Security/Depends wrappers) is
the one place that does.
"""

from fastapi import Depends

from src.context import RequestContext
from src.database import get_session, AsyncSession

from .auth import get_user_id


def get_context(db: AsyncSession = Depends(get_session), user_id = Depends(get_user_id)) -> RequestContext:
    return RequestContext(db=db, user_id=user_id)
