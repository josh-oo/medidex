"""FastAPI-specific dependency-injection glue.

get_session() itself is framework-agnostic and lives in src/database - MCP
reuses it directly (see mcp_server/context.py). get_context() is the one
piece that's actually FastAPI-specific: it resolves get_session() and
auth.py's get_user() through FastAPI's own Depends() graph and hands back
a RequestContext (src/context.py's composition root). It lives here, not in
src/database, so the framework-agnostic src/ layer never imports anything
FastAPI-specific - this module (plus auth.py's Security/Depends wrappers) is
the one place that does.
"""

from typing import Optional

from fastapi import Depends

from src.context import RequestContext
from src.database import get_session, AsyncSession

from .auth import get_user


def get_context(db: AsyncSession = Depends(get_session), user: Optional[dict] = Depends(get_user)) -> RequestContext:
    # get_user requires the APPROVED role whenever a token is given at all (see its
    # docstring), so every route built on get_context gets that check for free now,
    # not just the ones that happened to also declare their own approval dependency.
    return RequestContext(db=db, user_id=user.get("sub") if user else None)
