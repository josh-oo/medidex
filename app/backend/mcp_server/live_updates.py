"""Bridges the same Redis-backed project pub/sub the REST API uses for its SSE
endpoint (GET /projects/{project_id}/stream, fastapi_app/projects.py) into the
MCP SDK's `subscriptions/listen` mechanism, so an MCP client can listen for
updates to a `medidex://projects/{project_id}` resource instead of opening a
separate streaming connection - one project resource in, no `.../stream`
resource needed.

Wired in as this server's own `lifespan` (see create_server() in
mcp_server/__init__.py): main.py's merge() already drives
`MCPServer.session_manager.run()`, and that method enters
`self.app.lifespan(self.app)` - the lowlevel Server's lifespan, which is what
`MCPServer(lifespan=...)` sets - for the life of the process
(StreamableHTTPSessionManager.run() in the installed SDK). No changes to
main.py are needed for this to run.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import anyio

from mcp.server.subscriptions import ResourceUpdated, SubscriptionBus

from src.services.pubsub import ProjectPubSubService


async def _forward_project_updates(bus: SubscriptionBus) -> None:
    """Runs for the server's lifetime: republish every project's Redis pings
    as a ResourceUpdated event for that project's MCP resource URI.
    """
    pubsub_service = ProjectPubSubService()
    channel = await pubsub_service.subscribe_to_all_projects()
    try:
        while True:
            project_id = await pubsub_service.get_next_project_id_update(channel)
            await bus.publish(ResourceUpdated(uri=f"medidex://projects/{project_id}"))
    finally:
        await pubsub_service.unsubscribe_from_all_projects(channel)


def lifespan(bus: SubscriptionBus):
    """Builds the MCPServer(lifespan=...) callable for `bus` (the same
    SubscriptionBus instance passed to MCPServer(subscriptions=...), so the
    events this publishes actually reach `subscriptions/listen` streams).
    """

    @asynccontextmanager
    async def _lifespan(server) -> AsyncIterator[None]:
        async with anyio.create_task_group() as tg:
            tg.start_soon(_forward_project_updates, bus)
            yield
            tg.cancel_scope.cancel()

    return _lifespan
