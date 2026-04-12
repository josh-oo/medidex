import os

import redis.asyncio as redis
from redis.asyncio.client import PubSub

from ..database import ProjectRepository

class ProjectPubSubService:
    """Redis-backed pub/sub service for project update notifications."""

    def __init__(self, project_repo : ProjectRepository, redis_url: str | None = None, channel_prefix: str = "project-updates") -> None:
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