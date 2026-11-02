import os
from typing import List, Optional

import redis.asyncio as redis
from redis.asyncio.client import PubSub

from ..database import ProjectRepository
from ..utils.dto import Database, DatabaseStage, DatabaseStatus

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

class DatabaseStatusService:
    """Redis-backed status of the study databases on their way to being usable (an import, then the indexing of its
    reports, see DatabaseStatus): each change is published on a channel of its own per database, and the last one is
    kept, so that a stream that starts late begins with it. The imports in flight are kept too: their database is not
    committed before they are done, but is listed (GET /databases) with `importing`."""

    CHANNEL_PREFIX = "database-status"
    IMPORTS = "database-imports"
    # How long the last status is kept: a stream started after a failed import still learns why.
    KEEP_SECONDS = 24 * 60 * 60

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis = redis.Redis.from_url(redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)

    def _channel_name(self, database_id: int) -> str:
        return f"{self.CHANNEL_PREFIX}:{database_id}"

    async def publish(self, status: DatabaseStatus) -> None:
        data = status.model_dump_json()
        # Kept and published in one round trip: it is published for every item of an import.
        async with self._redis.pipeline(transaction=False) as pipe:
            pipe.set(self._channel_name(status.databaseId), data, ex=self.KEEP_SECONDS)
            pipe.publish(self._channel_name(status.databaseId), data)
            await pipe.execute()

    async def current(self, database_id: int) -> Optional[DatabaseStatus]:
        """The last status published for the database, if it is not too long ago."""
        data = await self._redis.get(self._channel_name(database_id))
        return DatabaseStatus.model_validate_json(data) if data else None

    async def start_import(self, database: Database) -> None:
        await self._redis.hset(self.IMPORTS, str(database.databaseId), database.model_dump_json())
        await self.publish(DatabaseStatus(databaseId=database.databaseId, stage=DatabaseStage.importing))

    async def end_import(self, database_id: int) -> None:
        """The database is no longer imported: listed as it is, and its last status (of the import) is forgotten."""
        await self._redis.hdel(self.IMPORTS, str(database_id))
        await self._redis.delete(self._channel_name(database_id))

    async def imports(self) -> List[Database]:
        """The databases being imported, as they will be once they are."""
        return [Database.model_validate_json(data) for data in (await self._redis.hgetall(self.IMPORTS)).values()]

    async def fail_interrupted_imports(self) -> None:
        """Ends the imports a stop of the backend interrupted (on its start): they are listed as what of them was
        committed (nothing, unless it stopped while their PDFs were stored)."""
        for database in await self.imports():
            await self.end_import(database.databaseId)
            await self.publish(DatabaseStatus(
                databaseId=database.databaseId,
                stage=DatabaseStage.failed,
                message="The backend stopped during the import.",
            ))

    async def subscribe(self, database_id: int) -> PubSub:
        pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
        await pubsub.subscribe(self._channel_name(database_id))
        return pubsub

    async def unsubscribe(self, database_id: int, pubsub: PubSub) -> None:
        await pubsub.unsubscribe(self._channel_name(database_id))
        await pubsub.aclose()

    async def get_next_status(self, pubsub: PubSub) -> DatabaseStatus:
        while True:
            message = await pubsub.get_message(timeout=1.0)
            if message and message.get("data") is not None:
                return DatabaseStatus.model_validate_json(message["data"])

    def progress(self, database_id: int, stage: DatabaseStage, step: Optional[str], total: int, done: int = 0) -> "DatabaseProgress":
        return DatabaseProgress(self, DatabaseStatus(databaseId=database_id, stage=stage, step=step, done=done, total=total))


class DatabaseProgress:
    """Counts the items of one step of a database (see DatabaseStatusService.progress) and publishes how far it is: at
    its start and after every item."""

    def __init__(self, service: DatabaseStatusService, status: DatabaseStatus) -> None:
        self.service = service
        self.status = status

    async def start(self) -> "DatabaseProgress":
        await self.service.publish(self.status)
        return self

    async def advance(self, count: int = 1) -> None:
        self.status.done += count
        await self.service.publish(self.status)
