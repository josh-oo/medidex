"""Shared helpers for MCP tools/resources: the current authenticated user and a
scoped DB session, factored out so both tools.py and resources.py can reuse them.
"""

from contextlib import asynccontextmanager

from mcp.server.auth.middleware.auth_context import get_access_token

from src.database import get_session

# get_session() is an async-generator dependency built for FastAPI's Depends
# machinery; wrapping it lets tools/resources open/close a session the same
# way outside of a request, without going through FastAPI's DI system.
session_scope = asynccontextmanager(get_session)


def current_user_id() -> str:
    access_token = get_access_token()
    if access_token is None or not access_token.subject:
        raise ValueError("Not authenticated")
    return access_token.subject
