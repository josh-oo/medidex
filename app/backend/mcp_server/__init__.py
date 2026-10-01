"""The MCP (Model Context Protocol) head: exposes study/report search and
retrieval as tools, built and spliced into a FastAPI app via server.py.

Re-exports server.py's public surface so callers write `from mcp_server
import create_server, mount` rather than reaching into the submodule -
mirrors fastapi_app's create_app() being the package's one entry point.
"""

from .server import create_server, mount, MCP_STREAMABLE_HTTP_PATH

__all__ = ["create_server", "mount", "MCP_STREAMABLE_HTTP_PATH"]
