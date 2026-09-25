"""Business logic services. Each submodule is a plain class with no FastAPI
(or MCP) awareness - src/context.py (the composition root) wires them
together, and both fastapi_app/ and mcp_server/ get the object graph through
that, not through this package's namespace. Import submodules directly
(e.g. `from src.services.vectorstore import VectorstoreService`).
"""
