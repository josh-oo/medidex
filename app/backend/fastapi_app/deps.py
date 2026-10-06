"""FastAPI-specific dependency-injection glue."""

from typing import Optional

from fastapi import Depends

from src.context import RequestContext
from src.database import get_session, AsyncSession
from src.services.authorization import has_role

from .auth import get_user


def get_context(db: AsyncSession = Depends(get_session), user: Optional[dict] = Depends(get_user)) -> RequestContext:
    # get_user requires the APPROVED role whenever a token is given at all (see its
    # docstring), so every route built on get_context gets that check for free now,
    # not just the ones that happened to also declare their own approval dependency.
    return RequestContext(
        db=db,
        user_id=user.get("sub") if user else None,
        is_admin=bool(user) and has_role(user.get("roles") or [], "ADMIN"),
    )
