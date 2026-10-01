"""Process entrypoint: combines the two independent adapters - fastapi_app
(REST API) and mcp_server (MCP) - into the one ASGI app this container serves.

This is the only place either adapter's independence is set aside: neither
fastapi_app nor mcp_server imports the other, or knows the other exists. The
actual splicing logic (mcp_server.mount()) lives in mcp_server/server.py, not
here, so a downstream deployable composing its own extended app can reuse it
too - this file is just the OSS build's own composition, not a shared utility.
"""

from fastapi_app import create_app
from mcp_server import create_server, mount

app = create_app()
mcp_server = create_server()

mount(app, mcp_server)
