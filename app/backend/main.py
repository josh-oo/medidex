"""Process entrypoint: combines the two independent adapters - fastapi_app
(REST API) and mcp_server (MCP) - into the one ASGI app this container serves.

This is the only place either adapter's independence is set aside: neither
fastapi_app nor mcp_server imports the other, or knows the other exists.
merge() below is what actually combines them - it lives here, not inside
mcp_server, because splicing one app into another is a top-level composition
concern, not something the MCP adapter itself should need to know how to do.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from mcp.server import MCPServer

from fastapi_app import create_app
from mcp_server import create_server, MCP_STREAMABLE_HTTP_PATH


def merge(app: FastAPI, server: MCPServer, path: str = MCP_STREAMABLE_HTTP_PATH) -> None:
    """Splice the MCP server's routes/middleware directly into `app`.

    Deliberately not `app.mount(path, server.streamable_http_app())`: the SDK
    registers its RFC 9728 protected-resource-metadata route at the host's
    absolute root (/.well-known/oauth-protected-resource/...), independent of
    where the /mcp endpoint itself lives. Wrapping the whole sub-app in a path
    Mount would nest that well-known route under the mount prefix too, making it
    unreachable at the URL the server itself advertises in its 401
    WWW-Authenticate header - verified against the installed SDK version before
    picking this approach.
    """
    sub_app = server.streamable_http_app(streamable_http_path=path)

    app.router.routes.extend(sub_app.routes)
    # Appended (not inserted at index 0 via add_middleware) so existing
    # middleware - notably CORS, added in fastapi_app.create_app() - stays
    # outermost.
    app.user_middleware.extend(sub_app.user_middleware)

    existing_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def combined_lifespan(app: FastAPI):
        async with server.session_manager.run():
            async with existing_lifespan(app) as state:
                yield state

    app.router.lifespan_context = combined_lifespan


app = create_app()
mcp_server = create_server()

merge(app, mcp_server)
