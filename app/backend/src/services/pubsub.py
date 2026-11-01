import os
from typing import Optional

import redis.asyncio as redis
from redis.asyncio.client import PubSub

from ..database import ProjectRepository

class ProjectPubSubService:
    """Redis-backed pub/sub service for project update notifications."""

    # The ids of the reports of a project that changed, on a channel of its own per project (not under channel_prefix,
    # whose pattern subscribe_to_all_projects listens to).
    REPORT_CHANNEL_PREFIX = "report-updates"

    def __init__(self, project_repo : Optional[ProjectRepository] = None, redis_url: str | None = None, channel_prefix: str = "project-updates") -> None:
        self.project_repo = project_repo
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._channel_prefix = channel_prefix
        self._redis = redis.Redis.from_url(self._redis_url, decode_responses=True)

    def _channel_name(self, project_id: str) -> str:
        return f"{self._channel_prefix}:{project_id}"

    async def publish_project_update(self, project_id: str) -> None:
        """Publish a lightweight ping update to all subscribers of a project."""
        await self._redis.publish(self._channel_name(project_id), "ping")

    def _report_channel_name(self, project_id: str) -> str:
        return f"{self.REPORT_CHANNEL_PREFIX}:{project_id}"

    async def publish_report_update(self, report_id: int, project_id: Optional[str] = None) -> None:
        """Publish that a report changed: a ping to the subscribers of its project, and its id to the subscribers
        of the reports of its project. Without `project_id` it is looked up."""
        project_id = project_id or await self.project_repo.get_project_id_by_report_id(report_id)
        if project_id:
            await self._redis.publish(self._channel_name(project_id), "ping")
            await self._redis.publish(self._report_channel_name(project_id), str(report_id))

    async def subscribe_to_project_reports(self, project_id: str) -> PubSub:
        pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
        await pubsub.subscribe(self._report_channel_name(project_id))
        return pubsub

    async def unsubscribe_from_project_reports(self, project_id: str, pubsub: PubSub) -> None:
        await pubsub.unsubscribe(self._report_channel_name(project_id))
        await pubsub.aclose()

    async def get_next_report_update(self, pubsub: PubSub) -> int:
        """The id of the next report that changed (see publish_report_update)."""
        return int(await self.get_next_project_update(pubsub))

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