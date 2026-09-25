import os
from typing import Optional

import redis.asyncio as redis
from redis.asyncio.client import PubSub

from ..database import ProjectRepository

class ProjectPubSubService:
    """Redis-backed pub/sub service for project update notifications."""

    def __init__(self, project_repo : Optional[ProjectRepository] = None, redis_url: str | None = None, channel_prefix: str = "project-updates") -> None:
        # Optional: only publish_report_update() needs it (to resolve a
        # report id to its project id). A caller that only publishes/listens
        # by project id - e.g. mcp_server's cross-project update bridge,
        # which has no per-request RequestContext to build one from - can
        # omit it.
        self.project_repo = project_repo
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._channel_prefix = channel_prefix
        self._redis = redis.Redis.from_url(self._redis_url, decode_responses=True)

    def _channel_name(self, project_id: str) -> str:
        return f"{self._channel_prefix}:{project_id}"

    async def publish_project_update(self, project_id: str) -> None:
        """Publish a lightweight ping update to all subscribers of a project."""
        await self._redis.publish(self._channel_name(project_id), "ping")

    async def publish_report_update(self, report_id: str) -> None:
        """Publish a lightweight ping update to all subscribers of a project based on a report."""
        project_id = await self.project_repo.get_project_id_by_report_id(report_id)
        if project_id:
            await self._redis.publish(self._channel_name(project_id), "ping")

    async def get_next_project_update(self, pubsub: PubSub) -> str:
        while True:
            message = await pubsub.get_message(timeout=1.0)
            if not message:
                continue

            data = message.get("data")
            if data is None:
                continue

            if isinstance(data, bytes):
                data = data.decode()
            return str(data)

    async def subscribe_to_project(self, project_id: str) -> PubSub:
        channel = self._channel_name(project_id)

        pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
        await pubsub.subscribe(channel)
        return pubsub

    async def unsubscribe_from_project(self, project_id: str, pubsub: PubSub) -> None:
        channel = self._channel_name(project_id)
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()

    def _channel_pattern(self) -> str:
        return f"{self._channel_prefix}:*"

    async def subscribe_to_all_projects(self) -> PubSub:
        """Like subscribe_to_project(), but across every project's channel at
        once - for a listener that doesn't know in advance which project ids
        it cares about (mcp_server bridges this into per-project MCP resource
        subscriptions; see mcp_server/live_updates.py).
        """
        pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
        await pubsub.psubscribe(self._channel_pattern())
        return pubsub

    async def unsubscribe_from_all_projects(self, pubsub: PubSub) -> None:
        await pubsub.punsubscribe(self._channel_pattern())
        await pubsub.aclose()

    async def get_next_project_id_update(self, pubsub: PubSub) -> str:
        """Like get_next_project_update(), but for a subscribe_to_all_projects()
        stream: returns the project id parsed out of the channel name rather
        than the (contentless) ping payload, since one stream now carries
        every project's updates.
        """
        prefix = f"{self._channel_prefix}:"
        while True:
            message = await pubsub.get_message(timeout=1.0)
            if not message:
                continue

            channel = message.get("channel")
            if channel is None:
                continue

            if isinstance(channel, bytes):
                channel = channel.decode()

            if channel.startswith(prefix):
                return channel[len(prefix):]