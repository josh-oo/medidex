"""The schema of the resources database, made by the backend itself when it starts: the models are the schema."""

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import SQLModel

logger = logging.getLogger(__name__)


class ResourceSchema:
    """Creates the tables of every model (models.py and those of extensions, which SQLModel all keeps in its one
    metadata) that do not exist yet; there are no migrations. In one transaction under an advisory lock, so backend
    processes that start at the same time do it one after the other."""

    # Any fixed number: the lock the starting processes wait for each other with.
    LOCK_ID = 7_250_114
    # How long to wait for postgres to accept connections (it may start together with the backend).
    CONNECT_ATTEMPTS = 60
    CONNECT_RETRY_SECONDS = 2.0

    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    async def ensure(self) -> None:
        await self._wait_for_database()
        async with self.engine.begin() as conn:
            await conn.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": self.LOCK_ID})
            await conn.run_sync(lambda sync: SQLModel.metadata.create_all(sync))
        logger.info("resources schema is ready")

    async def _wait_for_database(self) -> None:
        for attempt in range(self.CONNECT_ATTEMPTS):
            try:
                async with self.engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                return
            except OperationalError:
                if attempt == self.CONNECT_ATTEMPTS - 1:
                    raise
                logger.info("waiting for postgres...")
                await asyncio.sleep(self.CONNECT_RETRY_SECONDS)
